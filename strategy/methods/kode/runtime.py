from __future__ import annotations

import ast
import doctest
import importlib.util
import json
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


TRANSCRIPT_DIR = Path(".artifacts") / "transcripts"
TOOL_RESULTS_DIR = Path(".artifacts") / "tool-results"
VALIDATION_LOG = Path(".artifacts") / "validation.log"
SOLUTION_FILE = Path("solution.py")
PROMPT_FILE = Path("prompt.txt")
TESTS_FILE = Path("tests_generated.py")

CODEGEN_SKILL_BODY = """# Codegen Skill

Use this skill when the user asks for Python code from a prompt, stub, docstring, or programming-contest statement.

## Workflow

1. Read `prompt.txt` to inspect the exact task.
2. Classify the task shape:
   - Function task: preserve the provided function name and signature.
   - Stdin/stdout task: write a complete script that reads input and prints output.
3. Write a minimal correct draft to `solution.py` immediately.
4. Read validation feedback after every change to `solution.py`.
5. Iterate until validation passes or the loop budget runs out.

## Expectations

- Keep the answer as a single Python file.
- Preserve docstrings when they contain useful examples.
- Prefer straightforward algorithms over cleverness.
- For contest tasks, include `if __name__ == "__main__":`.
- Do not return prose in the final answer. Return code only.

## Common Checks

- Imports are valid.
- Function names match the prompt exactly.
- Sample outputs match exactly after trimming trailing newlines.
- Edge cases from doctests and `assert` lines are satisfied.
"""


@dataclass
class KodeConfig:
    max_turns: int = 20
    bash_timeout: int = 120
    validation_timeout: int = 20
    context_limit: int = 50000
    persist_threshold: int = 30000
    preview_chars: int = 2000
    keep_recent_tool_results: int = 3
    enable_subagent: bool = True
    base_runs_dir: str | None = None


@dataclass
class SkillDocument:
    name: str
    description: str
    body: str


class SkillRegistry:
    def __init__(self, documents: list[SkillDocument] | None = None):
        self.documents = {document.name: document for document in documents or []}

    def load_full_text(self, name: str) -> str:
        document = self.documents.get(name)
        if document is None:
            known = ", ".join(sorted(self.documents)) or "(none)"
            return f"Error: Unknown skill '{name}'. Available skills: {known}"
        return f"<skill name=\"{document.name}\">\n{document.body}\n</skill>"


SKILL_REGISTRY = SkillRegistry(
    [
        SkillDocument(
            name="codegen",
            description="Generate Python solutions for function-implementation and stdin/stdout coding tasks.",
            body=CODEGEN_SKILL_BODY.strip(),
        )
    ]
)


@dataclass
class DoctestCase:
    expression: str
    expected: str
    mode: str


@dataclass
class SampleCase:
    sample_input: str
    expected_output: str


@dataclass
class TaskSpec:
    task_type: str
    original_prompt: str
    normalized_prompt: str
    function_name: str = ""
    signature_line: str = ""
    doctest_cases: list[DoctestCase] = field(default_factory=list)
    assert_statements: list[str] = field(default_factory=list)
    sample_cases: list[SampleCase] = field(default_factory=list)


@dataclass
class ValidationResult:
    passed: bool
    syntax_ok: bool
    summary: str
    tests_run: int
    code: str = ""


@dataclass
class PlanItem:
    content: str
    status: str = "pending"
    active_form: str = ""


@dataclass
class PlanningState:
    items: list[PlanItem] = field(default_factory=list)
    rounds_since_update: int = 0


class TodoManager:
    def __init__(self) -> None:
        self.state = PlanningState()

    def update(self, items: list[dict]) -> str:
        if len(items) > 12:
            raise ValueError("Keep the session plan short (max 12 items)")

        normalized: list[PlanItem] = []
        in_progress_count = 0
        for index, raw_item in enumerate(items):
            content = str(raw_item.get("content", "")).strip()
            status = str(raw_item.get("status", "pending")).lower()
            active_form = str(raw_item.get("activeForm", "")).strip()

            if not content:
                raise ValueError(f"Item {index}: content required")
            if status not in {"pending", "in_progress", "completed"}:
                raise ValueError(f"Item {index}: invalid status '{status}'")
            if status == "in_progress":
                in_progress_count += 1

            normalized.append(PlanItem(content=content, status=status, active_form=active_form))

        if in_progress_count > 1:
            raise ValueError("Only one plan item can be in_progress")

        self.state.items = normalized
        self.state.rounds_since_update = 0
        return self.render()

    def note_round_without_update(self) -> None:
        self.state.rounds_since_update += 1

    def reminder(self) -> str | None:
        if not self.state.items or self.state.rounds_since_update < 3:
            return None
        return "<reminder>Refresh your current todo plan before continuing.</reminder>"

    def render(self) -> str:
        if not self.state.items:
            return "No session plan yet."

        lines = []
        for item in self.state.items:
            marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}[item.status]
            line = f"{marker} {item.content}"
            if item.status == "in_progress" and item.active_form:
                line += f" ({item.active_form})"
            lines.append(line)
        return "\n".join(lines)


@dataclass
class CompactState:
    last_summary: str = ""
    recent_files: list[str] = field(default_factory=list)


@dataclass
class CandidateState:
    passing_code: str = ""
    runnable_code: str = ""
    extracted_code: str = ""


@dataclass
class AgentRuntime:
    workspace: Path
    spec: TaskSpec
    config: KodeConfig
    todo: TodoManager = field(default_factory=TodoManager)
    compact: CompactState = field(default_factory=CompactState)
    candidate: CandidateState = field(default_factory=CandidateState)
    validation_count: int = 0
    last_validated_hash: int | None = None

    def absolute(self, relative_path: Path | str) -> Path:
        path = (self.workspace / relative_path).resolve()
        if not path.is_relative_to(self.workspace):
            raise ValueError(f"Path escapes workspace: {relative_path}")
        return path


def normalize_prompt_text(prompt: str) -> str:
    text = prompt.replace("\r\n", "\n")
    if "\\n" in text and "\n" not in prompt:
        text = text.replace("\\n", "\n")
    return text.strip()


def parse_assert_statements(text: str) -> list[str]:
    statements: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if "assert " not in stripped:
            continue
        match = re.search(r"assert\s+.+", stripped)
        if match:
            statements.append(match.group(0).rstrip("`\"'"))
    return statements


def parse_doctest_cases(text: str) -> list[DoctestCase]:
    parser = doctest.DocTestParser()
    cases: list[DoctestCase] = []
    for example in parser.get_examples(text):
        expression = example.source.strip()
        expected = example.want.strip()
        if not expression or not expected:
            continue
        try:
            ast.literal_eval(expected)
            mode = "python"
        except Exception:
            mode = "text"
        cases.append(DoctestCase(expression=expression, expected=expected, mode=mode))
    return cases


def parse_sample_cases(text: str) -> list[SampleCase]:
    pattern = re.compile(
        r"Sample Input\s+\d+\s*\n\n(.*?)\n\nSample Output\s+\d+\s*\n\n(.*?)(?=\n\n(?:Sample Input\s+\d+|###|\Z))",
        re.DOTALL,
    )
    matches = pattern.findall(text + "\n")
    cases = []
    for sample_input, expected_output in matches:
        cases.append(
            SampleCase(
                sample_input=sample_input.rstrip("\n"),
                expected_output=expected_output.rstrip("\n"),
            )
        )
    return cases


def parse_task_spec(prompt: str) -> TaskSpec:
    normalized_prompt = normalize_prompt_text(prompt)
    function_match = re.search(
        r"^\s*(def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?:->\s*[^:]+)?\s*:)",
        normalized_prompt,
        re.MULTILINE,
    )
    doctest_cases = parse_doctest_cases(normalized_prompt)
    assert_statements = parse_assert_statements(normalized_prompt)
    sample_cases = parse_sample_cases(normalized_prompt)

    task_type = "stdin_script"
    function_name = ""
    signature_line = ""
    if function_match:
        task_type = "function_impl"
        signature_line = function_match.group(1)
        function_name = function_match.group(2)
    elif re.search(r"\bstdin\b|\bstdout\b|Sample Input|Sample Output", normalized_prompt, re.IGNORECASE):
        task_type = "stdin_script"
    else:
        task_type = "function_impl"

    return TaskSpec(
        task_type=task_type,
        original_prompt=prompt,
        normalized_prompt=normalized_prompt,
        function_name=function_name,
        signature_line=signature_line,
        doctest_cases=doctest_cases,
        assert_statements=assert_statements,
        sample_cases=sample_cases,
    )


def create_session_workspace(config: KodeConfig) -> Path:
    base_dir = config.base_runs_dir or str(Path(tempfile.gettempdir()) / "maslab_kode_runs")
    runs_dir = Path(base_dir).resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    workspace = runs_dir / f"run_{uuid.uuid4().hex}"
    workspace.mkdir(parents=True, exist_ok=False)
    (workspace / ".artifacts").mkdir(parents=True, exist_ok=True)
    return workspace


def cleanup_workspace(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def build_system_prompt(spec: TaskSpec, workspace: Path) -> str:
    task_hint = {
        "function_impl": (
            "Return a single valid Python module that defines the requested function. "
            "Preserve the function name and signature when one is provided."
        ),
        "stdin_script": (
            "Return a single valid Python program that reads from stdin and writes to stdout. "
            "Include a main entry point when appropriate."
        ),
    }[spec.task_type]

    return textwrap.dedent(
        f"""\
        You are a Python code-generation agent working in {workspace}.
        Solve the user's task by using tools inside this scratch workspace.
        {task_hint}
        Use the todo tool for multi-step work.
        Load the `codegen` skill before implementing unless you already have the exact strategy.
        Always write your current best answer to `solution.py`.
        After changing `solution.py`, inspect validation feedback and iterate until tests pass.
        Keep intermediate artifacts in this workspace only.
        Your final response must contain code only, with no explanation.
        """
    ).strip()


def build_initial_user_prompt(spec: TaskSpec) -> str:
    return textwrap.dedent(
        f"""\
        User task:

        {spec.normalized_prompt}

        Requirements:
        - Work only inside the current scratch workspace.
        - Save the candidate answer to `solution.py`.
        - Use `read_file` to inspect `prompt.txt` if needed.
        - Do not stop after reasoning; make and validate concrete code.
        """
    ).strip()


def persist_large_output(runtime: AgentRuntime, tool_use_id: str, output: str) -> str:
    if len(output) <= runtime.config.persist_threshold:
        return output

    tool_results_dir = runtime.absolute(TOOL_RESULTS_DIR)
    tool_results_dir.mkdir(parents=True, exist_ok=True)
    stored_path = tool_results_dir / f"{tool_use_id}.txt"
    if not stored_path.exists():
        stored_path.write_text(output)

    rel_path = stored_path.relative_to(runtime.workspace)
    preview = output[: runtime.config.preview_chars]
    return (
        "<persisted-output>\n"
        f"Full output saved to: {rel_path}\n"
        "Preview:\n"
        f"{preview}\n"
        "</persisted-output>"
    )


def estimate_context_size(messages: list[dict]) -> int:
    return len(json.dumps(messages, ensure_ascii=False, default=str))


def track_recent_file(runtime: AgentRuntime, path: str) -> None:
    if path in runtime.compact.recent_files:
        runtime.compact.recent_files.remove(path)
    runtime.compact.recent_files.append(path)
    if len(runtime.compact.recent_files) > 5:
        runtime.compact.recent_files[:] = runtime.compact.recent_files[-5:]


def compact_history(messages: list[dict], runtime: AgentRuntime, focus: str | None = None) -> list[dict]:
    transcript_dir = runtime.absolute(TRANSCRIPT_DIR)
    transcript_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = transcript_dir / f"transcript_{int(time.time())}.jsonl"
    with transcript_path.open("w") as handle:
        for message in messages:
            handle.write(json.dumps(message, default=str) + "\n")

    recent_messages = messages[-8:]
    summary_lines = ["Conversation compacted to preserve context."]
    if focus:
        summary_lines.append(f"Focus: {focus}")
    for message in recent_messages:
        preview = str(message.get("content", ""))[:300]
        summary_lines.append(f"{message['role']}: {preview}")
    if runtime.compact.recent_files:
        summary_lines.append("Recent files: " + ", ".join(runtime.compact.recent_files))
    summary_lines.append(f"Transcript saved to: {transcript_path.relative_to(runtime.workspace)}")
    runtime.compact.last_summary = "\n".join(summary_lines)
    return [{"role": "user", "content": runtime.compact.last_summary}]


def micro_compact(messages: list[dict], keep_recent_tool_results: int) -> list[dict]:
    tool_indexes = [index for index, message in enumerate(messages) if message.get("role") == "tool"]
    if len(tool_indexes) <= keep_recent_tool_results:
        return messages

    compacted_messages = []
    tool_seen = 0
    cutoff = len(tool_indexes) - keep_recent_tool_results
    for message in messages:
        if message.get("role") != "tool":
            compacted_messages.append(message)
            continue

        if tool_seen < cutoff:
            content = str(message.get("content", ""))
            if len(content) > 120:
                compacted_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id"),
                        "content": "[Earlier tool result compacted. Re-run the tool for full detail.]",
                    }
                )
            else:
                compacted_messages.append(message)
        else:
            compacted_messages.append(message)
        tool_seen += 1
    return compacted_messages


def safe_path(runtime: AgentRuntime, path_str: str) -> Path:
    return runtime.absolute(path_str)


def run_bash(runtime: AgentRuntime, command: str, tool_use_id: str) -> str:
    dangerous = ["rm -rf /", "sudo ", " shutdown", " reboot", "> /dev/"]
    if any(item in command for item in dangerous):
        return "Error: Dangerous command blocked"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=runtime.workspace,
            capture_output=True,
            text=True,
            timeout=runtime.config.bash_timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Error: Timeout ({runtime.config.bash_timeout}s)"
    except (FileNotFoundError, OSError) as exc:
        return f"Error: {exc}"

    output = (result.stdout + result.stderr).strip() or "(no output)"
    return persist_large_output(runtime, tool_use_id, output)


def run_read(runtime: AgentRuntime, path: str, tool_use_id: str, limit: int | None = None) -> str:
    try:
        track_recent_file(runtime, path)
        lines = safe_path(runtime, path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        output = "\n".join(lines)
        return persist_large_output(runtime, tool_use_id, output)
    except Exception as exc:
        return f"Error: {exc}"


def run_write(runtime: AgentRuntime, path: str, content: str) -> str:
    try:
        file_path = safe_path(runtime, path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        track_recent_file(runtime, path)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_edit(runtime: AgentRuntime, path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(runtime, path)
        content = file_path.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        file_path.write_text(content.replace(old_text, new_text, 1))
        track_recent_file(runtime, path)
        return f"Edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


def build_tools(enable_subagent: bool) -> list[dict]:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Run a shell command inside the current scratch workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read file contents from the scratch workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write content to a file in the scratch workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": "Replace exact text in a file once.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    "required": ["path", "old_text", "new_text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "todo",
                "description": "Rewrite the current todo plan.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string"},
                                    "status": {
                                        "type": "string",
                                        "enum": ["pending", "in_progress", "completed"],
                                    },
                                    "activeForm": {"type": "string"},
                                },
                                "required": ["content", "status"],
                            },
                        }
                    },
                    "required": ["items"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "load_skill",
                "description": "Load the full body of a named skill.",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compact",
                "description": "Compact earlier conversation into a smaller summary.",
                "parameters": {
                    "type": "object",
                    "properties": {"focus": {"type": "string"}},
                },
            },
        },
    ]

    if enable_subagent:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "task",
                    "description": "Spawn a child agent with fresh context for exploration or debugging.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["prompt"],
                    },
                },
            }
        )

    return tools


def append_validation_log(runtime: AgentRuntime, summary: str) -> None:
    log_path = runtime.absolute(VALIDATION_LOG)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as handle:
        handle.write(summary.rstrip() + "\n")


def build_validation_script(spec: TaskSpec) -> str:
    if spec.task_type == "stdin_script":
        samples = [(case.sample_input, case.expected_output) for case in spec.sample_cases]
        return textwrap.dedent(
            f"""\
            import subprocess
            import sys

            SAMPLES = {samples!r}

            if not SAMPLES:
                raise SystemExit("No sample cases available for stdin validation.")

            for index, (sample_input, expected_output) in enumerate(SAMPLES, start=1):
                result = subprocess.run(
                    [sys.executable, "solution.py"],
                    input=sample_input,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                assert result.returncode == 0, (
                    f"Sample {{index}} failed with return code {{result.returncode}}\\n"
                    f"STDOUT:\\n{{result.stdout}}\\nSTDERR:\\n{{result.stderr}}"
                )
                actual = result.stdout.strip()
                expected = expected_output.strip()
                assert actual == expected, (
                    f"Sample {{index}} mismatch\\nExpected:\\n{{expected}}\\nActual:\\n{{actual}}"
                )

            print("OK")
            """
        )

    checks: list[str] = []
    if spec.function_name:
        checks.append(
            f"assert callable(module_globals.get({spec.function_name!r})), "
            f"'Missing function: {spec.function_name}'"
        )

    for case in spec.doctest_cases:
        if case.mode == "python":
            checks.append(
                f"actual = eval({case.expression!r}, module_globals, module_globals)\n"
                f"expected = {case.expected}\n"
                f"assert actual == expected, "
                f"'Doctest failed for {case.expression}: expected {case.expected!r}, got ' + repr(actual)"
            )
        else:
            checks.append(
                f"actual = eval({case.expression!r}, module_globals, module_globals)\n"
                f"assert str(actual).strip() == {case.expected!r}, "
                f"'Doctest text mismatch for {case.expression}'"
            )

    for statement in spec.assert_statements:
        checks.append(f"exec({statement!r}, module_globals, module_globals)")

    if not checks:
        checks.append("assert module_globals, 'Solution module did not load.'")

    return (
        "import importlib.util\n"
        "from pathlib import Path\n\n"
        'solution_path = Path(__file__).with_name("solution.py")\n'
        'module_spec = importlib.util.spec_from_file_location("submission", solution_path)\n'
        "module = importlib.util.module_from_spec(module_spec)\n"
        'assert module_spec and module_spec.loader, "Unable to load solution module"\n'
        "module_spec.loader.exec_module(module)\n"
        "module_globals = module.__dict__\n\n"
        + "\n".join(checks)
        + '\n\nprint("OK")\n'
    )


def run_validation(runtime: AgentRuntime) -> ValidationResult:
    runtime.validation_count += 1
    solution_path = runtime.absolute(SOLUTION_FILE)
    if not solution_path.exists():
        return ValidationResult(
            passed=False,
            syntax_ok=False,
            summary="solution.py does not exist yet.",
            tests_run=0,
            code="",
        )

    code = solution_path.read_text()
    tests_path = runtime.absolute(TESTS_FILE)
    tests_path.write_text(build_validation_script(runtime.spec))

    try:
        py_compile.compile(str(solution_path), doraise=True)
    except py_compile.PyCompileError as exc:
        summary = f"Syntax check failed:\n{exc.msg}"
        append_validation_log(runtime, summary)
        return ValidationResult(
            passed=False,
            syntax_ok=False,
            summary=summary,
            tests_run=max(
                1,
                len(runtime.spec.sample_cases) + len(runtime.spec.doctest_cases) + len(runtime.spec.assert_statements),
            ),
            code=code,
        )

    try:
        result = subprocess.run(
            [sys.executable, str(tests_path)],
            cwd=runtime.workspace,
            capture_output=True,
            text=True,
            timeout=runtime.config.validation_timeout,
        )
    except subprocess.TimeoutExpired:
        summary = f"Validation timed out after {runtime.config.validation_timeout}s."
        append_validation_log(runtime, summary)
        return ValidationResult(
            passed=False,
            syntax_ok=True,
            summary=summary,
            tests_run=max(
                1,
                len(runtime.spec.sample_cases) + len(runtime.spec.doctest_cases) + len(runtime.spec.assert_statements),
            ),
            code=code,
        )

    output = (result.stdout + result.stderr).strip() or "(no validation output)"
    passed = result.returncode == 0
    summary = f"Validation {'passed' if passed else 'failed'}:\n{output}"
    append_validation_log(runtime, summary)
    return ValidationResult(
        passed=passed,
        syntax_ok=True,
        summary=summary,
        tests_run=max(
            1,
            len(runtime.spec.sample_cases) + len(runtime.spec.doctest_cases) + len(runtime.spec.assert_statements),
        ),
        code=code,
    )


def read_solution_code(runtime: AgentRuntime) -> str:
    solution_path = runtime.absolute(SOLUTION_FILE)
    if not solution_path.exists():
        return ""
    return solution_path.read_text()


def update_candidate(runtime: AgentRuntime, result: ValidationResult) -> None:
    if not result.code:
        return
    if result.passed:
        runtime.candidate.passing_code = result.code
    elif result.syntax_ok and not runtime.candidate.passing_code:
        runtime.candidate.runnable_code = result.code


def maybe_validate_solution(runtime: AgentRuntime) -> ValidationResult | None:
    code = read_solution_code(runtime)
    if not code:
        return None

    current_hash = hash(code)
    if runtime.last_validated_hash == current_hash:
        return None

    runtime.last_validated_hash = current_hash
    result = run_validation(runtime)
    update_candidate(runtime, result)
    return result


def extract_code_from_text(text: str) -> str:
    if not text:
        return ""

    fenced = re.findall(r"```(?:python|python3)?\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced[-1].strip()

    stripped = text.strip()
    if stripped.startswith("def ") or stripped.startswith("import ") or stripped.startswith("from "):
        return stripped
    return ""


def choose_best_candidate(runtime: AgentRuntime) -> str:
    if runtime.candidate.passing_code:
        return runtime.candidate.passing_code
    if runtime.candidate.runnable_code:
        return runtime.candidate.runnable_code
    if runtime.candidate.extracted_code:
        return runtime.candidate.extracted_code
    return read_solution_code(runtime)


def build_validation_feedback(result: ValidationResult) -> str:
    return textwrap.dedent(
        f"""\
        Validation result:
        {result.summary}

        Keep iterating on solution.py until validation passes.
        """
    ).strip()


def bootstrap_workspace(runtime: AgentRuntime) -> None:
    runtime.absolute(PROMPT_FILE).write_text(runtime.spec.normalized_prompt + "\n")
    starter = ""
    if runtime.spec.task_type == "function_impl" and runtime.spec.signature_line:
        starter = runtime.spec.signature_line + "\n    pass\n"
    runtime.absolute(SOLUTION_FILE).write_text(starter)


def execute_child_tool(
    runtime: AgentRuntime,
    tool_name: str,
    tool_args: dict,
    tool_use_id: str,
    model_call: Callable[[str, list[dict], list[dict]], dict],
) -> str:
    if not isinstance(tool_args, dict):
        return f"Error: Tool '{tool_name}' arguments must be a JSON object."

    argument_error = tool_args.get("_argument_error")
    if argument_error:
        raw_arguments = tool_args.get("_raw_arguments", "")
        return f"Error: Tool '{tool_name}' arguments could not be parsed. {argument_error}. Raw arguments: {raw_arguments}"

    try:
        if tool_name == "bash":
            return run_bash(runtime, tool_args["command"], tool_use_id)
        if tool_name == "read_file":
            return run_read(runtime, tool_args["path"], tool_use_id, tool_args.get("limit"))
        if tool_name == "write_file":
            return run_write(runtime, tool_args["path"], tool_args["content"])
        if tool_name == "edit_file":
            return run_edit(runtime, tool_args["path"], tool_args["old_text"], tool_args["new_text"])
        if tool_name == "todo":
            return runtime.todo.update(tool_args["items"])
        if tool_name == "load_skill":
            return SKILL_REGISTRY.load_full_text(tool_args["name"])
        if tool_name == "compact":
            return "Compacting conversation..."
        if tool_name == "task":
            return run_subagent(runtime, tool_args["prompt"], model_call)
        return f"Unknown tool: {tool_name}"
    except KeyError as exc:
        return f"Error: Tool '{tool_name}' is missing required argument '{exc.args[0]}'. Received arguments: {json.dumps(tool_args, ensure_ascii=False)}"
    except Exception as exc:
        return f"Error: Tool '{tool_name}' execution failed: {exc}"


def run_subagent(
    runtime: AgentRuntime,
    prompt: str,
    model_call: Callable[[str, list[dict], list[dict]], dict],
) -> str:
    tools = build_tools(enable_subagent=False)
    messages: list[dict] = [{"role": "user", "content": prompt}]
    system = (
        f"You are a coding subagent in {runtime.workspace}. "
        "Use tools to inspect the workspace or suggest a fix. "
        "Do not provide the final user-facing answer. Return a concise summary."
    )

    final_text = ""
    for _ in range(10):
        response = model_call(system, messages, tools)
        final_text = response["text"]
        messages.append(response["assistant_message"])
        tool_calls = response["tool_calls"]
        if not tool_calls:
            break

        manual_compact = False
        compact_focus = None
        for tool_call in tool_calls:
            output = execute_child_tool(
                runtime,
                tool_call["name"],
                tool_call["arguments"],
                tool_call["id"],
                model_call,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": str(output),
                }
            )
            if tool_call["name"] == "compact":
                manual_compact = True
                compact_focus = tool_call["arguments"].get("focus")
        if manual_compact:
            messages[:] = compact_history(messages, runtime, compact_focus)

    return final_text or "(no summary)"


def run_code_agent(
    user_prompt: str,
    model_call: Callable[[str, list[dict], list[dict]], dict],
    config: KodeConfig,
) -> str:
    spec = parse_task_spec(user_prompt)
    workspace = create_session_workspace(config)
    runtime = AgentRuntime(workspace=workspace, spec=spec, config=config)
    bootstrap_workspace(runtime)

    messages: list[dict] = [{"role": "user", "content": build_initial_user_prompt(spec)}]
    tools = build_tools(enable_subagent=config.enable_subagent)
    system = build_system_prompt(spec, workspace)

    try:
        for _ in range(config.max_turns):
            messages[:] = micro_compact(messages, config.keep_recent_tool_results)
            if estimate_context_size(messages) > config.context_limit:
                messages[:] = compact_history(messages, runtime)

            reminder = runtime.todo.reminder()
            if reminder:
                messages.append({"role": "user", "content": reminder})

            response = model_call(system, messages, tools)
            messages.append(response["assistant_message"])

            extracted = extract_code_from_text(response["text"])
            if extracted:
                runtime.candidate.extracted_code = extracted

            tool_calls = response["tool_calls"]
            if not tool_calls:
                break

            runtime.todo.note_round_without_update()
            changed_solution = False
            manual_compact = False
            compact_focus = None

            for tool_call in tool_calls:
                output = execute_child_tool(
                    runtime,
                    tool_call["name"],
                    tool_call["arguments"],
                    tool_call["id"],
                    model_call,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": str(output),
                    }
                )
                if tool_call["name"] in {"write_file", "edit_file"} and tool_call["arguments"].get("path") == str(SOLUTION_FILE):
                    changed_solution = True
                if tool_call["name"] == "compact":
                    manual_compact = True
                    compact_focus = tool_call["arguments"].get("focus")

            if manual_compact:
                messages[:] = compact_history(messages, runtime, compact_focus)

            validation_result = maybe_validate_solution(runtime)
            if validation_result:
                messages.append({"role": "user", "content": build_validation_feedback(validation_result)})
                if validation_result.passed:
                    return validation_result.code
            elif changed_solution:
                messages.append(
                    {
                        "role": "user",
                        "content": "solution.py changed but could not be validated. Check the file and continue.",
                    }
                )

        return choose_best_candidate(runtime)
    finally:
        cleanup_workspace(workspace)
