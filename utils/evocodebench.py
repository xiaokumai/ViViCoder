"""Local execution support for the repository-level EvoCodeBench benchmark."""

from __future__ import annotations

import ast
import fcntl
import hashlib
import json
import os
import re
import secrets
import signal
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, Tuple


DEFAULT_ROOT = Path("/data/masterpiece/project/Evo/EvoCodeBench")
_ICECREAM_TRACE_MARKER = "__EVOCODEBENCH_IC_TRACE__|"
_PRINT_TRACE_MARKER = "__EVOCODEBENCH_PRINT_TRACE__|"
_RECOVERY_DIRECTORY_NAME = ".vivicoder_evaluator_recovery"
_RECOVERY_VERSION = 1
_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_PRIVATE_TASKS: Dict[str, dict] = {}
_PRIVATE_TASKS_GUARD = threading.Lock()


def load_metadata(metadata_file: Path) -> Dict[str, dict]:
    """Load JSONL metadata records keyed by namespace."""
    records = {}
    with Path(metadata_file).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            records[record["namespace"]] = record
    return records


def enrich_dataset(
    dataset: Iterable[dict],
    benchmark_root: Path = DEFAULT_ROOT,
    feedback_metadata_file: Path | None = None,
    source_code_root: Path | None = None,
) -> list[dict]:
    """Attach only the precomputed, feedback-visible runtime metadata."""
    benchmark_root = Path(benchmark_root).expanduser().resolve()
    if feedback_metadata_file is None:
        raise ValueError(
            "EvoCodeBench requires a precomputed feedback_metadata_file; the runtime "
            "loader must never read the official full test list."
        )
    feedback_metadata_file = Path(feedback_metadata_file).expanduser().resolve()
    source_code_root = Path(
        source_code_root or benchmark_root / "Source_Code"
    ).expanduser().resolve()
    metadata = load_metadata(feedback_metadata_file)

    # A previous evaluator can have been killed after replacing a benchmark
    # target but before its Python ``finally`` block ran. Recover those durable
    # transactions before any strategy sees or executes the repositories, and
    # reject unrelated dirty targets that would invalidate line-based metadata.
    recover_evaluator_transactions(
        metadata,
        benchmark_root=benchmark_root,
        source_code_root=source_code_root,
    )

    enriched = []
    missing = []
    for original in dataset:
        question = dict(original)
        namespace = question.get("question_id") or question.get("namespace")
        record = metadata.get(namespace)
        if record is None:
            missing.append(str(namespace))
            continue

        feedback_tests = record.get("feedback_tests")
        if not isinstance(feedback_tests, list) or not feedback_tests:
            raise ValueError(
                f"Missing feedback_tests in sanitized metadata for {namespace!r}."
            )
        if "tests" in record:
            raise ValueError(
                f"Sanitized metadata for {namespace!r} contains forbidden full tests."
            )
        project = record["completion_path"].split("/", 1)[0]
        private_record = dict(record)
        private_record.update(
            {
                "benchmark_root": str(benchmark_root),
                "source_code_root": str(source_code_root),
                "project": project,
                "feedback_tests": feedback_tests,
            }
        )
        with _PRIVATE_TASKS_GUARD:
            _PRIVATE_TASKS[namespace] = private_record

        # This is the complete repository metadata visible to strategies.  It
        # intentionally contains no source root, benchmark data path, body
        # positions, or held-out test selectors.
        public_evo = {
            "namespace": namespace,
            "project": project,
            "completion_path": record["completion_path"],
            "feedback_tests": feedback_tests,
        }
        question["evocodebench"] = public_evo
        question["completion_path"] = record["completion_path"]
        question["feedback_tests"] = feedback_tests
        question.pop("tests", None)
        enriched.append(question)

    if missing:
        preview = ", ".join(missing[:5])
        raise KeyError(
            f"Missing sanitized EvoCodeBench metadata for {len(missing)} task(s): {preview}"
        )
    return enriched


def build_feedback_partition(metadata: Dict[str, dict]) -> Dict[str, list[str]]:
    """Choose a globally consistent minimum feedback-selector set.

    A selector is either feedback-visible for every task that references it or
    held out everywhere.  The integer program minimizes total task/selector
    feedback exposures while requiring every task to have at least one.
    EvoCodeBench-2403's optimum is 272 tasks with one selector and three tasks
    with two selectors.
    """
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import lil_matrix
    except ImportError as exc:
        raise RuntimeError(
            "SciPy with scipy.optimize.milp is required to build the global "
            "EvoCodeBench feedback-test partition."
        ) from exc

    records = list(metadata.values())
    selectors = sorted({test for record in records for test in record.get("tests", [])})
    if any(not record.get("tests") for record in records):
        empty = [record["namespace"] for record in records if not record.get("tests")]
        raise ValueError(f"EvoCodeBench tasks without tests cannot receive feedback: {empty[:5]}")

    selector_index = {selector: index for index, selector in enumerate(selectors)}
    incidence = lil_matrix((len(records), len(selectors)), dtype=float)
    for row_index, record in enumerate(records):
        for selector in record["tests"]:
            incidence[row_index, selector_index[selector]] = 1
    incidence = incidence.tocsr()
    exposure_cost = np.asarray(incidence.sum(axis=0)).ravel()
    result = milp(
        c=exposure_cost,
        integrality=np.ones(len(selectors)),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(incidence, 1, np.inf),
        options={"time_limit": 30},
    )
    if not result.success or result.x is None:
        raise RuntimeError(f"Unable to partition EvoCodeBench feedback tests: {result.message}")

    selected = {
        selector for selector, value in zip(selectors, result.x) if value > 0.5
    }
    partition = {
        record["namespace"]: list(
            dict.fromkeys(
                selector for selector in record["tests"] if selector in selected
            )
        )
        for record in records
    }
    counts = [len(tests) for tests in partition.values()]
    if any(count < 1 for count in counts):
        raise RuntimeError("The feedback partition left at least one task without a test.")

    # Guard the agreed EvoCodeBench-2403 split.  A future dataset version must
    # be reviewed instead of silently exposing a different number of tests.
    if len(records) == 275:
        distribution = {count: counts.count(count) for count in set(counts)}
        if distribution != {1: 272, 2: 3}:
            raise RuntimeError(
                "Unexpected EvoCodeBench-2403 feedback distribution: "
                f"{distribution}; expected {{1: 272, 2: 3}}."
            )
    return partition


def is_evocodebench_question(question: dict) -> bool:
    return isinstance(question.get("evocodebench"), dict)


def _private_task(question_or_namespace: dict | str) -> dict:
    if isinstance(question_or_namespace, dict):
        evo = question_or_namespace.get("evocodebench", {})
        namespace = evo.get("namespace") or question_or_namespace.get("question_id")
    else:
        namespace = question_or_namespace
    with _PRIVATE_TASKS_GUARD:
        task = _PRIVATE_TASKS.get(str(namespace))
    if task is None:
        raise RuntimeError(
            f"Private EvoCodeBench metadata is not registered for {namespace!r}. "
            "Load the benchmark before invoking a feedback strategy."
        )
    return task


def extract_function_body(completion: str, namespace: str) -> str:
    """Convert a model response/full function into EvoCodeBench body code."""
    code = _strip_markdown(completion or "").strip("\n")
    if not code.strip():
        return ""

    parseable = textwrap.dedent(code)
    try:
        tree = ast.parse(parseable)
    except (SyntaxError, ValueError):
        # A raw indented function body is valid for EvoCodeBench even though it
        # is not a standalone Python module.
        return textwrap.dedent(code).strip("\n")

    function_name = namespace.rsplit(".", 1)[-1]
    target = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ),
        None,
    )
    if target is None:
        return textwrap.dedent(code).strip("\n")

    body_nodes = list(target.body)
    if body_nodes and _is_docstring(body_nodes[0]):
        body_nodes = body_nodes[1:]
    if not body_nodes:
        return "pass"

    lines = parseable.splitlines()
    start = body_nodes[0].lineno - 1
    end = body_nodes[-1].end_lineno
    body = textwrap.dedent("\n".join(lines[start:end]))

    # EvoCodeBench's official post-processor moves imports emitted before the
    # function into its body, because only the body range is injected.
    imports = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(textwrap.dedent("\n".join(lines[node.lineno - 1 : node.end_lineno])))
    if imports:
        body = "\n".join(imports + [body])
    return textwrap.dedent(body).strip("\n")


def evaluate(
    question: dict,
    completion: str,
    *,
    timeout: int = 120,
    max_feedback_chars: int = 12000,
    project_root: Path | None = None,
    use_lock: bool = True,
) -> Tuple[bool, str]:
    """Inject one candidate, run official task tests, and restore the repo."""
    public_evo = question.get("evocodebench")
    if not isinstance(public_evo, dict):
        raise ValueError(
            "EvoCodeBench metadata is missing. Load the task through load_benchmark()."
        )
    evo = _private_task(question)

    namespace = public_evo.get("namespace") or question.get("question_id")
    body = extract_function_body(completion, namespace)
    if not body.strip():
        return False, "EvoCodeBench evaluation failed: the generated function body is empty."
    if body.strip() == "pass":
        return False, "EvoCodeBench evaluation failed: the generated function body only contains `pass`."

    if project_root is None:
        source_root = Path(evo["source_code_root"])
        project_root = source_root / evo["project"]
    else:
        project_root = Path(project_root)
    project_root = project_root.expanduser().resolve()
    relative_path = evo["completion_path"].split("/", 1)[1]
    target_path = project_root / relative_path
    if not target_path.is_file():
        return False, f"EvoCodeBench source file does not exist: {target_path}"

    lock_context = _project_lock(project_root) if use_lock else _null_context()
    with lock_context:
        try:
            with _source_transaction(
                target_path,
                project_root=project_root,
                benchmark_root=Path(evo["benchmark_root"]),
            ) as (source, original_mode):
                patched = _inject_body(source, body, evo)
                _atomic_write(target_path, patched.encode("utf-8"), original_mode)

                compiled, compile_log = _compile(
                    target_path, project_root, timeout=min(timeout, 30)
                )
                if not compiled:
                    return False, _truncate(
                        "EvoCodeBench syntax check failed:\n" + compile_log,
                        max_feedback_chars,
                    )

                feedback_tests = evo["feedback_tests"]
                for test in feedback_tests:
                    passed, output = _run_pytest(project_root, test, timeout)
                    if not passed:
                        return False, _truncate(
                            f"EvoCodeBench test failed:\nProject: {evo['project']}\n"
                            f"Test: {test}\n{output}",
                            max_feedback_chars,
                        )
                return True, (
                    f"All EvoCodeBench tests passed for {namespace} "
                    f"({len(feedback_tests)} feedback test target(s))."
                )
        except Exception as exc:
            return False, _truncate(
                f"EvoCodeBench execution error: {type(exc).__name__}: {exc}",
                max_feedback_chars,
            )


def evaluate_debug(
    question: dict,
    completion: str,
    *,
    timeout: int = 120,
    max_feedback_chars: int = 12000,
    project_root: Path | None = None,
    use_lock: bool = True,
) -> Tuple[bool, str]:
    """Run an icecream-instrumented candidate and return only variable traces.

    The raw pytest stream is never returned because it may contain hidden test
    source or arbitrary candidate output. Only lines emitted through the
    evaluator-installed icecream output function cross the feedback boundary.
    """
    public_evo = question.get("evocodebench")
    if not isinstance(public_evo, dict):
        raise ValueError(
            "EvoCodeBench metadata is missing. Load the task through load_benchmark()."
        )
    evo = _private_task(question)
    namespace = public_evo.get("namespace") or question.get("question_id")
    body = extract_function_body(completion, namespace)
    if not body.strip():
        return False, "EvoCodeBench debug evaluation failed: instrumented code is empty."
    body = _instrument_icecream(body)

    if project_root is None:
        project_root = Path(evo["source_code_root"]) / evo["project"]
    else:
        project_root = Path(project_root)
    project_root = project_root.expanduser().resolve()
    if not _can_import_icecream(project_root):
        return False, (
            "EvoCodeBench debug evaluation cannot start because `icecream` is "
            f"not installed in {project_root / 'myenv'}."
        )

    relative_path = evo["completion_path"].split("/", 1)[1]
    target_path = project_root / relative_path
    if not target_path.is_file():
        return False, f"EvoCodeBench source file does not exist: {target_path}"

    lock_context = _project_lock(project_root) if use_lock else _null_context()
    with lock_context:
        try:
            with _source_transaction(
                target_path,
                project_root=project_root,
                benchmark_root=Path(evo["benchmark_root"]),
            ) as (source, original_mode):
                patched = _inject_body(source, body, evo)
                _atomic_write(target_path, patched.encode("utf-8"), original_mode)

                compiled, compile_log = _compile(
                    target_path, project_root, timeout=min(timeout, 30)
                )
                if not compiled:
                    return False, _truncate(
                        "EvoCodeBench instrumented syntax check failed:\n" + compile_log,
                        max_feedback_chars,
                    )

                collected_traces = []
                for test in evo["feedback_tests"]:
                    passed, status, traces = _run_pytest_debug(
                        project_root, test, timeout
                    )
                    if traces:
                        collected_traces.extend(traces)
                    if not passed:
                        trace_text = (
                            "\n".join(collected_traces)
                            if collected_traces
                            else "No icecream trace was emitted before the failure."
                        )
                        return False, _truncate(
                            f"EvoCodeBench feedback test failed.\nTest: {test}\n{status}\n\n"
                            f"How key variables and expressions changed during execution:\n"
                            f"{trace_text}",
                            max_feedback_chars,
                        )

                trace_text = (
                    "\n".join(collected_traces)
                    if collected_traces
                    else "No icecream trace was emitted."
                )
                return True, _truncate(
                    "EvoCodeBench feedback test passed with instrumented code.\n\n"
                    "How key variables and expressions changed during execution:\n"
                    + trace_text,
                    max_feedback_chars,
                )
        except Exception as exc:
            return False, _truncate(
                f"EvoCodeBench debug execution error: {type(exc).__name__}: {exc}",
                max_feedback_chars,
            )


def evaluate_print_trace(
    question: dict,
    completion: str,
    *,
    timeout: int = 120,
    max_feedback_chars: int = 12000,
    project_root: Path | None = None,
    use_lock: bool = True,
) -> Tuple[bool, str]:
    """Run TraceCoder's original print-instrumented code on feedback tests.

    TraceCoder continues to generate ordinary ``print(...)`` statements. The
    evaluator scopes those calls to a marker-emitting print function and only
    returns marked trace lines, never the raw pytest stream.
    """
    public_evo = question.get("evocodebench")
    if not isinstance(public_evo, dict):
        raise ValueError(
            "EvoCodeBench metadata is missing. Load the task through load_benchmark()."
        )
    evo = _private_task(question)
    namespace = public_evo.get("namespace") or question.get("question_id")
    body = extract_function_body(completion, namespace)
    if not body.strip():
        return False, "EvoCodeBench print-trace evaluation failed: code is empty."
    body = _instrument_print_trace(body)

    if project_root is None:
        project_root = Path(evo["source_code_root"]) / evo["project"]
    else:
        project_root = Path(project_root)
    project_root = project_root.expanduser().resolve()

    relative_path = evo["completion_path"].split("/", 1)[1]
    target_path = project_root / relative_path
    if not target_path.is_file():
        return False, f"EvoCodeBench source file does not exist: {target_path}"

    lock_context = _project_lock(project_root) if use_lock else _null_context()
    with lock_context:
        try:
            with _source_transaction(
                target_path,
                project_root=project_root,
                benchmark_root=Path(evo["benchmark_root"]),
            ) as (source, original_mode):
                patched = _inject_body(source, body, evo)
                _atomic_write(target_path, patched.encode("utf-8"), original_mode)

                compiled, compile_log = _compile(
                    target_path, project_root, timeout=min(timeout, 30)
                )
                if not compiled:
                    return False, _truncate(
                        "EvoCodeBench print-instrumented syntax check failed:\n"
                        + compile_log,
                        max_feedback_chars,
                    )

                collected_traces = []
                for test in evo["feedback_tests"]:
                    passed, status, traces = _run_pytest_print_trace(
                        project_root, test, timeout
                    )
                    collected_traces.extend(traces)
                    if not passed:
                        trace_text = (
                            "\n".join(collected_traces)
                            if collected_traces
                            else "No print trace was emitted before the failure."
                        )
                        return False, _truncate(
                            f"EvoCodeBench feedback test failed.\nTest: {test}\n{status}\n\n"
                            f"Captured TraceCoder print output:\n{trace_text}",
                            max_feedback_chars,
                        )

                trace_text = (
                    "\n".join(collected_traces)
                    if collected_traces
                    else "No print trace was emitted."
                )
                return True, _truncate(
                    "EvoCodeBench feedback test passed with TraceCoder instrumentation.\n\n"
                    "Captured TraceCoder print output:\n" + trace_text,
                    max_feedback_chars,
                )
        except Exception as exc:
            return False, _truncate(
                f"EvoCodeBench print-trace execution error: "
                f"{type(exc).__name__}: {exc}",
                max_feedback_chars,
            )


def prepare_agent_workspace(workspace: Path, question: dict) -> dict:
    """Copy subject source without any official test tree into the workspace."""
    if not is_evocodebench_question(question):
        return question

    workspace = Path(workspace)
    copied_question = dict(question)
    evo = dict(question["evocodebench"])
    private = _private_task(question)
    source_project = Path(private["source_code_root"]) / private["project"]
    destination = workspace / "repository"
    destination.mkdir(parents=True, exist_ok=True)

    rsync = shutil.which("rsync")
    if rsync:
        command = [
            rsync,
            "-a",
            "--delete",
            "--exclude=.git/",
            "--exclude=myenv/",
            "--exclude=.pytest_cache/",
            "--exclude=__pycache__/",
            "--exclude=tests/",
            "--exclude=test/",
            str(source_project) + "/",
            str(destination) + "/",
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Unable to copy EvoCodeBench repository: {result.stderr.strip()}")
    else:
        shutil.copytree(
            source_project,
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".git",
                "myenv",
                ".pytest_cache",
                "__pycache__",
                "tests",
                "test",
            ),
        )

    evo["agent_project_root"] = str(destination)
    copied_question["evocodebench"] = evo
    return copied_question


class PrivateEvaluatorServer:
    """Capability-scoped file-queue evaluator outside an agent process."""

    def __init__(self, workspace: Path, question: dict):
        self.workspace = Path(workspace).resolve()
        self.question = question
        self.namespace = question["evocodebench"]["namespace"]
        self.token = secrets.token_urlsafe(32)
        self.queue_path = self.workspace / ".evo-feedback"
        self._thread = None
        self._stop = threading.Event()

    def start(self) -> dict:
        _private_task(self.question)
        if self.queue_path.exists():
            shutil.rmtree(self.queue_path)
        self.queue_path.mkdir(mode=0o700)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        evo = self.question["evocodebench"]
        return {
            "queue_path": str(self.queue_path),
            "token": self.token,
            "namespace": self.namespace,
            "response_timeout": int(evo.get("test_timeout", 120)) + 45,
        }

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self.queue_path.exists():
            shutil.rmtree(self.queue_path)

    def _serve(self) -> None:
        while not self._stop.is_set():
            requests = sorted(self.queue_path.glob(f"{self.token}.*.request.json"))
            if not requests:
                time.sleep(0.05)
                continue
            for request_path in requests:
                processing_path = request_path.with_suffix(".processing")
                try:
                    request_path.replace(processing_path)
                except OSError:
                    continue
                response = self._handle_request(processing_path)
                request_id = request_path.name.split(".")[-3]
                response_path = self.queue_path / f"{self.token}.{request_id}.response.json"
                temporary = response_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(response, ensure_ascii=False),
                    encoding="utf-8",
                )
                temporary.replace(response_path)
                processing_path.unlink(missing_ok=True)

    def _handle_request(self, request_path: Path) -> dict:
        try:
            if request_path.stat().st_size > 5_000_000:
                raise ValueError("Evaluator request exceeds 5 MB.")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            if request.get("token") != self.token:
                raise PermissionError("Invalid evaluator capability token.")
            if request.get("namespace") != self.namespace:
                raise PermissionError("The evaluator capability is bound to another task.")
            completion = request.get("completion")
            if not isinstance(completion, str):
                raise ValueError("The evaluator request must contain a string completion.")
            evo = self.question["evocodebench"]
            passed, feedback = evaluate(
                self.question,
                completion,
                timeout=int(evo.get("test_timeout", 120)),
                max_feedback_chars=int(evo.get("max_feedback_chars", 12000)),
            )
            return {"passed": passed, "feedback": feedback}
        except Exception as exc:
            return {
                "passed": False,
                "feedback": f"Private evaluator error: {type(exc).__name__}: {exc}",
            }


@contextmanager
def private_evaluator_endpoint(workspace: Path, question: dict):
    if not is_evocodebench_question(question):
        yield None
        return
    server = PrivateEvaluatorServer(workspace, question)
    endpoint = server.start()
    try:
        yield endpoint
    finally:
        server.close()


def validation_script(result_filename: str, endpoint: dict) -> str:
    """Build a capability-only client; no test metadata enters the workspace."""
    endpoint_json = json.dumps(endpoint, ensure_ascii=False)
    return f'''import json
import os
import time
import uuid
from pathlib import Path

endpoint = json.loads({endpoint_json!r})
solution = Path({result_filename!r})
if not solution.exists():
    raise SystemExit(f"Missing {{solution}}")
request = {{
    "token": endpoint["token"],
    "namespace": endpoint["namespace"],
    "completion": solution.read_text(encoding="utf-8"),
}}
request_id = uuid.uuid4().hex
queue = Path(endpoint["queue_path"])
request_path = queue / f"{{endpoint['token']}}.{{request_id}}.request.json"
temporary = request_path.with_suffix(".tmp")
temporary.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
os.replace(temporary, request_path)
response_path = queue / f"{{endpoint['token']}}.{{request_id}}.response.json"
deadline = time.monotonic() + endpoint["response_timeout"]
while not response_path.exists():
    if time.monotonic() >= deadline:
        raise SystemExit("Private evaluator timed out without returning feedback.")
    time.sleep(0.05)
response = json.loads(response_path.read_text(encoding="utf-8"))
response_path.unlink(missing_ok=True)
print(response["feedback"])
raise SystemExit(0 if response["passed"] else 1)
'''


def isolate_agent_command(command: list[str], workspace: Path, question: dict) -> list[str]:
    """Hide the installed benchmark tree from Codex/OpenHands file tools."""
    if not is_evocodebench_question(question):
        return command
    unshare = shutil.which("unshare")
    if not unshare:
        raise RuntimeError(
            "Strict EvoCodeBench test isolation requires the Linux `unshare` command."
        )
    private = _private_task(question)
    helper = Path(__file__).with_name("isolated_exec.py")
    return [
        unshare,
        "--user",
        "--map-root-user",
        "--mount",
        "--pid",
        "--fork",
        "--mount-proc",
        sys.executable,
        str(helper),
        private["benchmark_root"],
        str(Path(workspace).resolve()),
        *command,
    ]


def _strip_markdown(text: str) -> str:
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    blocks = re.findall(r"```(?:python|Python|python3|Python3|py)?\s*(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else text


def _is_docstring(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _inject_body(source: str, body: str, metadata: dict) -> str:
    lines = source.splitlines(keepends=True)
    start = int(metadata["body_position"][0]) - 1
    end = int(metadata["body_position"][1])
    if start < 0 or end < start or end > len(lines):
        raise ValueError(
            f"Invalid body_position {metadata['body_position']} for a {len(lines)}-line file"
        )
    indented = textwrap.indent(textwrap.dedent(body).strip("\n"), " " * int(metadata["indent"]))
    replacement = ("\n" + indented + "\n").splitlines(keepends=True)
    return "".join(lines[:start] + replacement + lines[end:])


def _instrument_icecream(body: str) -> str:
    """Install a trace-only icecream output channel inside the target body."""
    body_lines = [
        line
        for line in textwrap.dedent(body).splitlines()
        if line.strip() != "from icecream import ic"
    ]
    setup = [
        "from icecream import ic",
        "def _evocodebench_ic_output(_evocodebench_ic_text):",
        "    print("
        + repr(_ICECREAM_TRACE_MARKER)
        + " + str(_evocodebench_ic_text).replace('\\n', '\\\\n'))",
        "ic.configureOutput(",
        "    includeContext=True,",
        "    outputFunction=_evocodebench_ic_output,",
        ")",
    ]
    return "\n".join(setup + body_lines)


def _instrument_print_trace(body: str) -> str:
    """Capture ordinary TraceCoder print calls through a marked channel."""
    setup = [
        "import builtins as _evocodebench_trace_builtins",
        "def _evocodebench_trace_print(*_evocodebench_values, **_evocodebench_kwargs):",
        "    _evocodebench_sep = _evocodebench_kwargs.get('sep', ' ')",
        "    _evocodebench_text = _evocodebench_sep.join(",
        "        str(_evocodebench_value) for _evocodebench_value in _evocodebench_values",
        "    )",
        "    _evocodebench_trace_builtins.print(",
        "        " + repr(_PRINT_TRACE_MARKER) + " + _evocodebench_text.replace('\\n', '\\\\n'),",
        "        flush=True,",
        "    )",
        "print = _evocodebench_trace_print",
    ]
    return "\n".join(setup + textwrap.dedent(body).splitlines())


def _python_executable(project_root: Path) -> Path:
    executable = project_root / "myenv" / "bin" / "python"
    if not executable.is_file():
        raise FileNotFoundError(f"Missing EvoCodeBench virtual environment: {executable}")
    return executable


def _execution_env(project_root: Path) -> dict:
    env = os.environ.copy()
    env_bin = project_root / "myenv" / "bin"
    env["PATH"] = os.pathsep.join([str(env_bin), env.get("PATH", "")])
    import_paths = [str(project_root), str(project_root / "src")]
    if env.get("PYTHONPATH"):
        import_paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(import_paths)

    evo_root = Path(project_root).resolve().parent.parent
    # For copied agent workspaces, recover the original benchmark cache path
    # from the symlinked virtual environment when possible.
    resolved_env = (project_root / "myenv").resolve()
    if resolved_env.parent.name:
        candidate = resolved_env.parent.parent.parent
        if (candidate / ".cache").is_dir():
            evo_root = candidate
    env.setdefault("HF_HOME", str(evo_root / ".cache" / "huggingface"))
    env.setdefault("LLAMA_INDEX_CACHE_DIR", str(evo_root / ".cache" / "huggingface" / "hub"))
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("TRANSFORMERS_OFFLINE", "1")
    env.setdefault("HF_TOKEN", "evocodebench-offline")
    env.setdefault("TIKTOKEN_CACHE_DIR", str(evo_root / ".cache" / "tiktoken"))
    for variable in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(variable, None)
        env.pop(variable.lower(), None)
    env["NO_PROXY"] = "*"
    if project_root.name == "XAgent":
        env.setdefault("MYSQL_DB_URL", f"sqlite:///{project_root / '.evocodebench.sqlite3'}")
    return env


def _compile(target_path: Path, project_root: Path, timeout: int) -> Tuple[bool, str]:
    try:
        result = subprocess.run(
            [str(_python_executable(project_root)), "-m", "py_compile", str(target_path)],
            cwd=project_root,
            env=_execution_env(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return False, f"Compilation timed out after {timeout}s.\n{_timeout_output(exc)}"
    except OSError as exc:
        return False, f"Unable to start syntax check: {exc}"
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def _can_import_icecream(project_root: Path) -> bool:
    try:
        result = subprocess.run(
            [str(_python_executable(project_root)), "-c", "from icecream import ic"],
            cwd=project_root,
            env=_execution_env(project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _run_pytest(project_root: Path, test: str, timeout: int) -> Tuple[bool, str]:
    try:
        returncode, _, timed_out = _run_process_group(
            [
                str(_python_executable(project_root)),
                "-m",
                "pytest",
                "-q",
                "--tb=no",
                "--show-capture=no",
                "--disable-warnings",
                "-p",
                "no:cacheprovider",
                test,
            ],
            cwd=project_root,
            env=_execution_env(project_root),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Feedback test timed out after {timeout}s."
    except OSError as exc:
        return False, f"Unable to start pytest: {exc}"
    if timed_out:
        return False, f"Feedback test timed out after {timeout}s."
    if returncode == 0:
        return True, "Feedback test passed."
    # Never return raw pytest output. Candidate code executes in the evaluator
    # and could otherwise use stdout or exception messages as an exfiltration
    # channel for files that are intentionally invisible to the strategy.
    return False, f"Feedback test failed (pytest exit code {returncode})."


def _run_pytest_debug(
    project_root: Path,
    test: str,
    timeout: int,
) -> Tuple[bool, str, list[str]]:
    try:
        returncode, output, timed_out = _run_process_group(
            [
                str(_python_executable(project_root)),
                "-m",
                "pytest",
                "-q",
                "-s",
                "--tb=no",
                "--disable-warnings",
                "-p",
                "no:cacheprovider",
                test,
            ],
            cwd=project_root,
            env=_execution_env(project_root),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Instrumented feedback test timed out after {timeout}s.", []
    except OSError as exc:
        return False, f"Unable to start instrumented pytest: {exc}", []

    traces = []
    for line in output.splitlines():
        marker_position = line.find(_ICECREAM_TRACE_MARKER)
        if marker_position >= 0:
            traces.append(line[marker_position + len(_ICECREAM_TRACE_MARKER) :])
    if timed_out:
        return False, f"Instrumented feedback test timed out after {timeout}s.", traces
    if returncode == 0:
        return True, "Instrumented feedback test passed.", traces
    return (
        False,
        f"Instrumented feedback test failed (pytest exit code {returncode}).",
        traces,
    )


def _run_pytest_print_trace(
    project_root: Path,
    test: str,
    timeout: int,
) -> Tuple[bool, str, list[str]]:
    try:
        returncode, output, timed_out = _run_process_group(
            [
                str(_python_executable(project_root)),
                "-m",
                "pytest",
                "-q",
                "-s",
                "--tb=no",
                "--disable-warnings",
                "-p",
                "no:cacheprovider",
                test,
            ],
            cwd=project_root,
            env=_execution_env(project_root),
            timeout=timeout,
        )
    except OSError as exc:
        return False, f"Unable to start TraceCoder pytest: {exc}", []

    traces = []
    for line in output.splitlines():
        marker_position = line.find(_PRINT_TRACE_MARKER)
        if marker_position >= 0:
            traces.append(line[marker_position + len(_PRINT_TRACE_MARKER) :])
    if timed_out:
        return False, f"TraceCoder feedback test timed out after {timeout}s.", traces
    if returncode == 0:
        return True, "TraceCoder feedback test passed.", traces
    return (
        False,
        f"TraceCoder feedback test failed (pytest exit code {returncode}).",
        traces,
    )


def _run_process_group(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
) -> Tuple[int, str, bool]:
    """Run a command in an isolated process group and reap all descendants.

    Some repositories (notably litdata) create multiprocessing/DataLoader
    workers during collection or test execution. Killing only the pytest
    process on timeout leaves those workers behind, so every evaluator command
    gets its own session/process group. The final SIGKILL also handles children
    that outlive a pytest process which exits normally.
    """
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    output = ""
    try:
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _signal_process_group(process.pid, signal.SIGTERM)
            try:
                output, _ = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                _signal_process_group(process.pid, signal.SIGKILL)
                output, _ = process.communicate()
    except BaseException:
        _signal_process_group(process.pid, signal.SIGKILL)
        try:
            process.wait(timeout=2)
        except (subprocess.TimeoutExpired, ChildProcessError):
            pass
        raise
    finally:
        # The pytest leader may already have exited while one of its workers is
        # still alive. killpg continues to address that inherited process group.
        _signal_process_group(process.pid, signal.SIGKILL)
    return process.returncode, output or "", timed_out


def _signal_process_group(process_group_id: int, sig: signal.Signals) -> None:
    try:
        os.killpg(process_group_id, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _timeout_output(exc: subprocess.TimeoutExpired) -> str:
    output = exc.stdout or ""
    if isinstance(output, bytes):
        output = output.decode(errors="replace")
    return output.strip()


def recover_evaluator_transactions(
    metadata: Dict[str, dict],
    *,
    benchmark_root: Path,
    source_code_root: Path,
) -> list[Path]:
    """Recover interrupted evaluator writes and validate benchmark targets.

    Recovery is performed while holding the same cross-process project lock as
    normal evaluation. This makes it safe to start another ``sp_run.py`` while
    an existing run is using a different task in the same benchmark project.
    """
    benchmark_root = Path(benchmark_root).expanduser().resolve()
    source_code_root = Path(source_code_root).expanduser().resolve()
    projects: Dict[Path, Dict[Path, str]] = {}

    for record in metadata.values():
        completion_path = str(record["completion_path"])
        try:
            project_name, relative_path = completion_path.split("/", 1)
        except ValueError as exc:
            raise ValueError(
                f"Invalid EvoCodeBench completion_path: {completion_path!r}"
            ) from exc
        project_root = (source_code_root / project_name).resolve()
        target_path = (project_root / relative_path).resolve()
        try:
            target_path.relative_to(project_root)
        except ValueError as exc:
            raise ValueError(
                f"EvoCodeBench target escapes its project: {completion_path!r}"
            ) from exc
        projects.setdefault(project_root, {})[target_path] = relative_path

    recovered = []
    for project_root, targets in projects.items():
        with _project_lock(project_root):
            for target_path in targets:
                if _recover_target_transaction(
                    target_path,
                    project_root=project_root,
                    benchmark_root=benchmark_root,
                ):
                    recovered.append(target_path)
            _validate_project_targets_clean(project_root, targets.values())
    return recovered


@contextmanager
def _source_transaction(
    target_path: Path,
    *,
    project_root: Path,
    benchmark_root: Path,
):
    """Persist the pristine source before temporarily replacing a target.

    The caller must hold ``_project_lock(project_root)``. The on-disk manifest
    deliberately precedes the candidate write, so even ``SIGKILL`` leaves
    enough information for the next benchmark load to restore the target.
    """
    target_path = Path(target_path).resolve()
    project_root = Path(project_root).resolve()
    benchmark_root = Path(benchmark_root).expanduser().resolve()
    _ensure_target_belongs_to_project(target_path, project_root)
    _recover_target_transaction(
        target_path,
        project_root=project_root,
        benchmark_root=benchmark_root,
    )

    original = target_path.read_bytes()
    original_mode = target_path.stat().st_mode
    source = original.decode("utf-8")
    if _ICECREAM_TRACE_MARKER in source or _PRINT_TRACE_MARKER in source:
        raise RuntimeError(
            "EvoCodeBench target already contains evaluator instrumentation but "
            "has no durable recovery record. Restore the file from its repository "
            f"snapshot before continuing: {target_path}"
        )

    manifest_path, backup_path = _transaction_paths(benchmark_root, target_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _atomic_write(backup_path, original, 0o600)
    manifest = {
        "version": _RECOVERY_VERSION,
        "pid": os.getpid(),
        "created_at": time.time(),
        "project_root": str(project_root),
        "target_path": str(target_path),
        "original_mode": original_mode,
        "original_sha256": hashlib.sha256(original).hexdigest(),
    }
    _atomic_write(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
        0o600,
    )

    try:
        yield source, original_mode
    finally:
        # Remove the recovery record only after the original bytes are back in
        # place. If restoration itself is interrupted, the next load retries it.
        _atomic_write(target_path, original, original_mode)
        _remove_transaction_files(manifest_path, backup_path)


def _recover_target_transaction(
    target_path: Path,
    *,
    project_root: Path,
    benchmark_root: Path,
) -> bool:
    target_path = Path(target_path).resolve()
    project_root = Path(project_root).resolve()
    _ensure_target_belongs_to_project(target_path, project_root)
    manifest_path, backup_path = _transaction_paths(benchmark_root, target_path)
    if not manifest_path.is_file():
        return False
    if not backup_path.is_file():
        raise RuntimeError(
            f"EvoCodeBench recovery manifest has no source backup: {manifest_path}"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Unable to read EvoCodeBench recovery manifest {manifest_path}: {exc}"
        ) from exc
    if manifest.get("version") != _RECOVERY_VERSION:
        raise RuntimeError(
            f"Unsupported EvoCodeBench recovery version in {manifest_path}: "
            f"{manifest.get('version')!r}"
        )
    if Path(manifest.get("project_root", "")).resolve() != project_root:
        raise RuntimeError(
            f"EvoCodeBench recovery project mismatch in {manifest_path}."
        )
    if Path(manifest.get("target_path", "")).resolve() != target_path:
        raise RuntimeError(
            f"EvoCodeBench recovery target mismatch in {manifest_path}."
        )

    original = backup_path.read_bytes()
    expected_digest = manifest.get("original_sha256")
    if hashlib.sha256(original).hexdigest() != expected_digest:
        raise RuntimeError(
            f"EvoCodeBench recovery backup checksum mismatch: {backup_path}"
        )
    try:
        original_mode = int(manifest["original_mode"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Invalid source mode in EvoCodeBench recovery manifest {manifest_path}."
        ) from exc

    _atomic_write(target_path, original, original_mode)
    _remove_transaction_files(manifest_path, backup_path)
    return True


def _transaction_paths(benchmark_root: Path, target_path: Path) -> Tuple[Path, Path]:
    recovery_root = (
        Path(benchmark_root).expanduser().resolve() / _RECOVERY_DIRECTORY_NAME
    )
    digest = hashlib.sha256(str(Path(target_path).resolve()).encode("utf-8")).hexdigest()
    return recovery_root / f"{digest}.json", recovery_root / f"{digest}.source"


def _remove_transaction_files(manifest_path: Path, backup_path: Path) -> None:
    # The manifest is removed first: an orphan backup is harmless, whereas a
    # manifest whose backup was removed could no longer repair the target.
    manifest_path.unlink(missing_ok=True)
    backup_path.unlink(missing_ok=True)


def _ensure_target_belongs_to_project(target_path: Path, project_root: Path) -> None:
    try:
        target_path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(
            f"EvoCodeBench target {target_path} escapes project {project_root}."
        ) from exc


def _validate_project_targets_clean(
    project_root: Path,
    relative_paths: Iterable[str],
) -> None:
    if not (project_root / ".git").exists():
        return
    command = [
        "git",
        "status",
        "--short",
        "--untracked-files=no",
        "--",
        *sorted(set(relative_paths)),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            f"Unable to validate EvoCodeBench project {project_root}: {exc}"
        ) from exc
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"Unable to validate EvoCodeBench project {project_root}: {details}"
        )
    dirty = result.stdout.strip()
    if dirty:
        raise RuntimeError(
            "EvoCodeBench target files differ from their repository snapshots. "
            "Restore them before starting generation; otherwise line-based "
            f"injection is unsafe.\n[{project_root.name}]\n{dirty}"
        )


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _project_lock(project_root: Path):
    key = str(project_root.resolve())
    with _LOCKS_GUARD:
        thread_lock = _LOCKS.setdefault(key, threading.Lock())
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    lock_path = Path(tempfile.gettempdir()) / f"vivicoder_evocodebench_{digest}.lock"
    with thread_lock:
        with lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _null_context():
    yield


def _truncate(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + f"\n... [feedback truncated; {len(text) - limit} chars omitted]"
