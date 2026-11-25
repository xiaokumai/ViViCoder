import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

from ..mas_base import MAS
from utils.evocodebench import (
    isolate_agent_command,
    prepare_agent_workspace,
    private_evaluator_endpoint,
    validation_script,
)


class Codex_Main(MAS):
    def __init__(self, general_config, method_config_name=None):
        method_config_name = "config_main" if method_config_name is None else method_config_name
        super().__init__(general_config, method_config_name)
        self.conda_env = self.method_config.get("conda_env", "codex")
        self.python_executable = self.method_config.get("python_executable", "")
        self.workspace_root = self.method_config.get("workspace_root", "")
        self.run_timeout = int(self.method_config.get("run_timeout", 900))
        self.result_filename = self.method_config.get("result_filename", "solution.py")
        self.max_prompt_chars = int(self.method_config.get("max_prompt_chars", 60000))
        self.max_total_tokens = int(self.method_config.get("max_total_tokens", 50000))
        self.model_provider = self.method_config.get("model_provider", "proxy")
        self.wire_api = self.method_config.get("wire_api", "responses")

    def inference(self, sample):
        workspace = self._make_workspace(sample)
        sample = prepare_agent_workspace(workspace, sample)
        payload_path = workspace / "payload.json"
        output_path = workspace / "result.json"

        with private_evaluator_endpoint(workspace, sample) as endpoint:
            payload = self._build_payload(sample, workspace, endpoint)
            payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            command = isolate_agent_command(
                self._build_command(payload_path, output_path),
                workspace,
                sample,
            )
            try:
                result = subprocess.run(
                    command,
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=self.run_timeout,
                )
                if not output_path.exists():
                    self._write_subprocess_failure(output_path, result)
            except subprocess.TimeoutExpired as exc:
                self._write_timeout_failure(output_path, exc)

        result = self._read_result(output_path, workspace)
        return {
            "response": result.get("response", ""),
            "workspace": str(workspace),
            "usage": result.get("usage", self._empty_usage()),
            "error": result.get("error"),
            "token_budget_exceeded": result.get("token_budget_exceeded", False),
        }

    def _make_workspace(self, sample: Dict) -> Path:
        question_id = str(sample.get("question_id") or sample.get("task_id") or "task")
        safe_id = "".join(char if char.isalnum() or char in "._-" else "_" for char in question_id)[:80]
        prefix = f"codex_{safe_id}_"
        if self.workspace_root:
            root = Path(self.workspace_root)
            root.mkdir(parents=True, exist_ok=True)
            return Path(tempfile.mkdtemp(prefix=prefix, dir=root))
        return Path(tempfile.mkdtemp(prefix=prefix))

    def _build_payload(self, sample: Dict, workspace: Path, endpoint=None) -> Dict:
        question = dict(sample)
        prompt = question.get("query") or question.get("prompt", "")
        if len(prompt) > self.max_prompt_chars:
            prompt = prompt[: self.max_prompt_chars] + "\n\n[Prompt truncated by Codex baseline adapter.]"
        question["query"] = prompt
        question["prompt"] = prompt

        model_dict = self.model_api_config[self.model_name]["model_list"][0]
        actual_model = model_dict["model_name"].removeprefix("openai/")

        return {
            "workspace": str(workspace),
            # Codex persists a SQLite state database under CODEX_HOME.  Keep
            # that state inside the task workspace so parallel benchmark tasks
            # neither contend for a shared database nor require a writable
            # user home directory.
            "codex_home": str(workspace / ".codex"),
            "question": question,
            "codex": {
                "model": actual_model,
                "api_key": model_dict["api_key"],
                "base_url": model_dict["model_url"],
                "model_provider": self.model_provider,
                "wire_api": self.wire_api,
            },
            "result_filename": self.result_filename,
            "max_total_tokens": self.max_total_tokens,
            "evocodebench_validation_script": (
                validation_script(self.result_filename, endpoint)
                if question.get("evocodebench")
                else ""
            ),
        }

    def _build_command(self, payload_path: Path, output_path: Path) -> List[str]:
        runner_path = Path(__file__).with_name("runner.py")
        if self.python_executable:
            return [self.python_executable, str(runner_path), str(payload_path), str(output_path)]

        conda_executable = shutil.which("conda")
        if conda_executable:
            return [
                conda_executable,
                "run",
                "-n",
                self.conda_env,
                "python",
                str(runner_path),
                str(payload_path),
                str(output_path),
            ]

        return [
            "bash",
            "-lc",
            f"source $(conda info --base)/etc/profile.d/conda.sh && conda activate {self.conda_env} && python {runner_path} {payload_path} {output_path}",
        ]

    def _read_result(self, output_path: Path, workspace: Path) -> Dict:
        if output_path.exists():
            try:
                result = json.loads(output_path.read_text(encoding="utf-8"))
                result.setdefault("usage", self._empty_usage())
                return result
            except json.JSONDecodeError:
                pass

        result_file = workspace / self.result_filename
        if result_file.exists():
            return {"response": result_file.read_text(encoding="utf-8"), "usage": self._empty_usage()}
        return {"response": "", "usage": self._empty_usage()}

    def _empty_usage(self) -> Dict:
        return {
            "api_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

    def _write_subprocess_failure(self, output_path: Path, result: subprocess.CompletedProcess):
        payload = {
            "response": "",
            "usage": self._empty_usage(),
            "error": (
                "Codex subprocess exited without writing result.json."
                if result.returncode == 0
                else f"Codex subprocess failed with exit code {result.returncode}."
            ),
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_timeout_failure(self, output_path: Path, exc: subprocess.TimeoutExpired):
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        payload = {
            "response": "",
            "usage": self._empty_usage(),
            "error": f"Codex subprocess timed out after {self.run_timeout}s.",
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
