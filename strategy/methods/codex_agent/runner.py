import json
import re
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

from openai_codex import Codex, CodexConfig, Sandbox
from openai_codex._run import _final_assistant_response_from_items
from openai_codex.generated.v2_all import (
    ItemCompletedNotification,
    ThreadTokenUsageUpdatedNotification,
)


def main():
    payload_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    workspace = Path(payload["workspace"])
    workspace.mkdir(parents=True, exist_ok=True)
    codex_home = Path(payload.get("codex_home", workspace / ".codex"))
    codex_home.mkdir(parents=True, exist_ok=True)
    question = payload["question"]
    result_filename = payload.get("result_filename", "solution.py")
    max_total_tokens = int(payload.get("max_total_tokens", 50000))

    _write_workspace_inputs(
        workspace,
        question,
        result_filename,
        payload.get("evocodebench_validation_script", ""),
    )
    _seed_function_solution(workspace / result_filename, question)

    codex_config = payload["codex"]
    config = CodexConfig(
        cwd=str(workspace),
        env={
            "OPENAI_API_KEY": codex_config["api_key"],
            "CODEX_HOME": str(codex_home),
        },
        config_overrides=(
            f'model="{codex_config["model"]}"',
            f'model_provider="{codex_config["model_provider"]}"',
            f'model_providers.{codex_config["model_provider"]}.name="OpenAI compatible proxy"',
            f'model_providers.{codex_config["model_provider"]}.base_url="{codex_config["base_url"]}"',
            f'model_providers.{codex_config["model_provider"]}.env_key="OPENAI_API_KEY"',
            f'model_providers.{codex_config["model_provider"]}.wire_api="{codex_config["wire_api"]}"',
        ),
    )

    with Codex(config=config) as codex:
        thread = codex.thread_start(sandbox=Sandbox.workspace_write)
        result, token_budget_exceeded = _run_with_token_budget(
            thread,
            _build_instruction(question, result_filename),
            max_total_tokens,
        )

    response = _read_result(workspace / result_filename, getattr(result, "final_response", ""))
    usage = _extract_usage(result)
    output_path.write_text(
        json.dumps(
            {
                "response": response,
                "workspace": str(workspace),
                "thread_id": getattr(thread, "id", ""),
                "final_response": getattr(result, "final_response", ""),
                "usage": usage,
                "token_budget_exceeded": token_budget_exceeded,
                "max_total_tokens": max_total_tokens,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_workspace_inputs(
    workspace: Path,
    question: dict,
    result_filename: str,
    evocodebench_validation_script: str = "",
):
    (workspace / "task.json").write_text(json.dumps(question, ensure_ascii=False, indent=2), encoding="utf-8")
    (workspace / "README_TASK.md").write_text(_render_task_markdown(question, result_filename), encoding="utf-8")
    (workspace / "sample_tests.json").write_text(
        json.dumps(question.get("sample_io", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    script = evocodebench_validation_script or _validation_script(result_filename)
    (workspace / "validate_solution.py").write_text(script, encoding="utf-8")


def _seed_function_solution(path: Path, question: dict):
    """Provide a syntactically valid fallback when a token budget stops early."""
    if question.get("evocodebench"):
        return
    sample_io = question.get("sample_io", [])
    is_stdio = bool(sample_io and isinstance(sample_io[0], dict) and "input" in sample_io[0])
    if is_stdio:
        return

    prompt = question.get("query") or question.get("prompt") or ""
    candidate = prompt.rstrip() + "\n    pass\n"
    try:
        compile(candidate, str(path), "exec")
    except SyntaxError:
        return
    path.write_text(candidate, encoding="utf-8")


def _render_task_markdown(question: dict, result_filename: str) -> str:
    return (
        "# Coding Task\n\n"
        f"Question ID: `{question.get('question_id') or question.get('task_id') or ''}`\n\n"
        "## Prompt\n\n"
        f"{question.get('query') or question.get('prompt') or ''}\n\n"
        "## Sample IO\n\n"
        "```json\n"
        f"{json.dumps(question.get('sample_io', []), ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        f"Write the final answer to `{result_filename}`.\n"
    )


def _build_instruction(question: dict, result_filename: str) -> str:
    sample_io = question.get("sample_io", [])
    is_stdio = bool(sample_io and isinstance(sample_io[0], dict) and "input" in sample_io[0])

    evo_instructions = ""
    if question.get("evocodebench"):
        evo_instructions = (
            "A source-only copy of the actual subject repository is available in `repository/`; "
            "official test files are intentionally not present. Inspect source and nearby "
            "functions as needed. The submission file "
            f"`{result_filename}` must contain only the target function body (no function "
            "signature, Markdown, or explanation). Run `python validate_solution.py` to send "
            "that body to the private feedback evaluator. Use its "
            "pytest output to repair the answer, and always keep the final answer in the "
            f"top-level `{result_filename}` file.\n"
        )

    return (
        "You are solving one benchmark programming task in an isolated workspace.\n"
        "You may freely create, edit, run, and delete files in this workspace only.\n"
        "Read `README_TASK.md`, `task.json`, and `sample_tests.json` first.\n\n"
        f"{_dataset_hint(question, is_stdio)}\n{evo_instructions}\n"
        f"First write your best complete submission to `{result_filename}`.\n"
        "You may then improve it with tests, but keep that file valid throughout.\n"
        "The file must contain only the code to submit, with no Markdown fences or explanation.\n"
        "If sample tests are available, run `python validate_solution.py` and fix failures before finishing.\n"
        "When done, stop after saving the final code file."
    )


def _dataset_hint(question: dict, is_stdio: bool) -> str:
    if question.get("evocodebench"):
        return (
            "This is an EvoCodeBench repository-level function completion task. "
            "Correctness is determined by the subject repository's real pytest tests."
        )

    if is_stdio:
        return (
            "This is a stdin/stdout programming task, such as LiveCodeBench AtCoder. "
            "Produce a complete Python program that reads from standard input and prints exactly the required output."
        )

    prompt = question.get("query") or question.get("prompt") or ""
    if "Please complete" in prompt and "Completed code:" in prompt:
        return (
            "This is an EvoCodeBench-style code completion task. "
            "Produce the completed Python code requested by the prompt. Preserve necessary function signatures."
        )

    if question.get("platform") and question.get("platform") != "atcoder":
        return (
            "This is a LiveCodeBench function/class task. "
            "Produce complete Python code compatible with the prompt and sample assertions."
        )

    return (
        "This is a Python function-completion benchmark such as HumanEval or MHPP. "
        "Produce complete Python code including imports and the target function definition."
    )


def _validation_script(result_filename: str) -> str:
    return f'''import json
import subprocess
import sys
from pathlib import Path

solution = Path("{result_filename}")
tests = json.loads(Path("sample_tests.json").read_text(encoding="utf-8"))

if not solution.exists():
    raise SystemExit(f"Missing {{solution}}")

code = solution.read_text(encoding="utf-8")

if not tests:
    compile(code, str(solution), "exec")
    print("No sample tests. Syntax check passed.")
    raise SystemExit(0)

if isinstance(tests[0], dict) and "input" in tests[0]:
    for i, test in enumerate(tests, 1):
        result = subprocess.run(
            [sys.executable, str(solution)],
            input=str(test.get("input", "")),
            text=True,
            capture_output=True,
            timeout=20,
        )
        actual = result.stdout.strip()
        expected = str(test.get("output", "")).strip()
        if result.returncode != 0 or actual != expected:
            print(f"Sample {{i}} failed")
            print("stdin:")
            print(test.get("input", ""))
            print("expected:")
            print(expected)
            print("actual:")
            print(actual)
            print("stderr:")
            print(result.stderr)
            raise SystemExit(1)
    print("All stdin/stdout sample tests passed.")
else:
    namespace = {{}}
    exec(code, namespace)
    if "Solution" in namespace:
        namespace["solution"] = namespace["Solution"]()
    for assertion in tests:
        exec(assertion, namespace)
    print("All assertion sample tests passed.")
'''


def _read_result(path: Path, final_response: str) -> str:
    if path.exists():
        code = _normalize_code_text(path.read_text(encoding="utf-8"), path)
        path.write_text(code, encoding="utf-8")
        return code.strip()

    code = _extract_code_block(final_response)
    if code:
        code = _normalize_code_text(code, path)
        path.write_text(code, encoding="utf-8")
        return code

    candidates = sorted(path.parent.glob("*.py"), key=lambda candidate: candidate.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if candidate.name != "validate_solution.py":
            code = _normalize_code_text(candidate.read_text(encoding="utf-8"), candidate)
            candidate.write_text(code, encoding="utf-8")
            return code.strip()
    return ""


def _normalize_code_text(code: str, path: Path) -> str:
    if _is_valid_python(code, path):
        return code
    if "\\n" not in code:
        return code

    decoded = code.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    if _is_valid_python(decoded, path):
        return decoded
    return code


def _is_valid_python(code: str, path: Path) -> bool:
    try:
        compile(code, str(path), "exec")
    except SyntaxError:
        return False
    return True


def _extract_code_block(text: str) -> str:
    if not text:
        return ""
    matches = re.findall(r"```(?:python|Python|py)?\s*(.*?)```", text, re.DOTALL)
    if matches:
        return matches[-1].strip()
    return ""


def _run_with_token_budget(thread, instruction: str, max_total_tokens: int):
    """Run a Codex turn and interrupt its agent loop at the token budget."""
    turn = thread.turn(instruction)
    usage = None
    items = []
    token_budget_exceeded = False
    stream = turn.stream()
    try:
        for event in stream:
            payload = event.payload
            if isinstance(payload, ItemCompletedNotification):
                items.append(payload.item)
            elif isinstance(payload, ThreadTokenUsageUpdatedNotification):
                usage = payload.token_usage
                total = usage.total
                consumed = int(getattr(total, "input_tokens", 0) or 0) + int(
                    getattr(total, "output_tokens", 0) or 0
                )
                if max_total_tokens > 0 and consumed >= max_total_tokens and not token_budget_exceeded:
                    token_budget_exceeded = True
                    # Do not call TurnHandle.interrupt() from inside its own
                    # synchronous notification iterator: this SDK version can
                    # tear down the client before the runner writes result.json.
                    # Closing the stream and then the Codex context terminates
                    # the agent process, while preserving solution.py.
                    break
    finally:
        stream.close()

    return (
        SimpleNamespace(
            usage=usage,
            items=items,
            final_response=_final_assistant_response_from_items(items) or "",
        ),
        token_budget_exceeded,
    )


def _extract_usage(result) -> dict:
    turn_usage = _extract_turn_usage(result)
    if turn_usage:
        return turn_usage

    items = getattr(result, "items", []) or []
    usage = {
        "api_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }

    for item in items:
        item_dict = _to_dict(item)
        item_usage = _find_usage(item_dict)
        if not item_usage:
            continue
        usage["api_calls"] += 1
        usage["prompt_tokens"] += int(item_usage.get("prompt_tokens", 0) or item_usage.get("input_tokens", 0) or 0)
        usage["completion_tokens"] += int(
            item_usage.get("completion_tokens", 0) or item_usage.get("output_tokens", 0) or 0
        )

    return usage


def _extract_turn_usage(result) -> dict:
    usage = getattr(result, "usage", None)
    if usage is None:
        return {}

    total = getattr(usage, "total", None)
    if total is None:
        return {}

    prompt_tokens = getattr(total, "input_tokens", 0) or 0
    completion_tokens = getattr(total, "output_tokens", 0) or 0
    api_calls = 1 if prompt_tokens or completion_tokens else 0
    return {
        "api_calls": api_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


def _to_dict(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return vars(value)
    return {}


def _find_usage(value):
    if isinstance(value, dict):
        for key in ("usage", "token_usage"):
            candidate = value.get(key)
            if isinstance(candidate, dict):
                return candidate
        for nested in value.values():
            found = _find_usage(nested)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_usage(item)
            if found:
                return found
    return None


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("result.json")
        output_path.write_text(
            json.dumps(
                {
                    "response": "",
                    "usage": {"api_calls": 0, "prompt_tokens": 0, "completion_tokens": 0},
                    "error": repr(exc),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        raise
