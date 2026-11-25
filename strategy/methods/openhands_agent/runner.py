import json
import subprocess
import sys
from pathlib import Path

from openhands.sdk import Agent, Conversation, LLM, Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool


def main():
    payload_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    workspace = Path(payload["workspace"])
    workspace.mkdir(parents=True, exist_ok=True)
    question = payload["question"]
    result_filename = payload.get("result_filename", "solution.py")
    terminal_type = payload.get("terminal_type", "subprocess")
    max_total_tokens = int(payload.get("max_total_tokens", 50000))

    _write_workspace_inputs(
        workspace,
        question,
        result_filename,
        payload.get("evocodebench_validation_script", ""),
    )
    _seed_function_solution(workspace / result_filename, question)

    llm_config = payload["llm"]
    llm = LLM(
        model=llm_config["model"],
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
    )
    agent = Agent(
        llm=llm,
        tools=[
            # The SDK prefers tmux when it is installed.  A benchmark task is
            # already isolated in its own process and workspace, so the lighter
            # subprocess backend is sufficient and works in containers where
            # access to a tmux socket is denied.
            Tool(name=TerminalTool.name, params={"terminal_type": terminal_type}),
            Tool(name=FileEditorTool.name),
            Tool(name=TaskTrackerTool.name),
        ],
    )
    budget_state = {"exceeded": False}
    conversation_ref = {}

    def enforce_token_budget(_event):
        usage = getattr(getattr(llm, "metrics", None), "accumulated_token_usage", None)
        consumed = int(getattr(usage, "prompt_tokens", 0) or 0) + int(
            getattr(usage, "completion_tokens", 0) or 0
        )
        if max_total_tokens > 0 and consumed >= max_total_tokens and not budget_state["exceeded"]:
            budget_state["exceeded"] = True
            # In a synchronous run this pauses after the current response,
            # preventing the next agent step while preserving solution.py.
            conversation_ref["conversation"].interrupt()

    conversation = Conversation(
        agent=agent,
        workspace=str(workspace),
        callbacks=[enforce_token_budget],
    )
    conversation_ref["conversation"] = conversation
    conversation.send_message(_build_instruction(question, result_filename))
    conversation.run()

    response = _read_result(workspace / result_filename)
    usage = _extract_usage(llm)
    output_path.write_text(
        json.dumps(
            {
                "response": response,
                "workspace": str(workspace),
                "usage": usage,
                "token_budget_exceeded": budget_state["exceeded"],
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


def _read_result(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    candidates = sorted(path.parent.glob("*.py"), key=lambda candidate: candidate.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if candidate.name != "validate_solution.py":
            return candidate.read_text(encoding="utf-8").strip()
    return ""


def _extract_usage(llm: LLM) -> dict:
    metrics = getattr(llm, "metrics", None)
    if metrics is None:
        return {"api_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_cost": 0.0}

    token_usage = getattr(metrics, "accumulated_token_usage", None)
    prompt_tokens = getattr(token_usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(token_usage, "completion_tokens", 0) or 0
    api_calls = len(getattr(metrics, "token_usages", []) or [])
    if api_calls == 0:
        api_calls = len(getattr(metrics, "response_latencies", []) or [])
    if api_calls == 0 and (prompt_tokens or completion_tokens):
        api_calls = 1

    return {
        "api_calls": api_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_cost": getattr(metrics, "accumulated_cost", 0.0) or 0.0,
    }


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("result.json")
        output_path.write_text(
            json.dumps({"response": "", "error": repr(exc)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise
