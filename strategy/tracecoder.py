"""Adapter from the official TraceCoder workflow to this project's benchmarks."""

from __future__ import annotations

from types import SimpleNamespace

from loguru import logger

from strategy.TraceCoder.config import setup_arg_parser
from strategy.TraceCoder.problem_processor import process_problem
from strategy.TraceCoder.src.postprocessing import extract_python_code
from strategy.TraceCoder.src.traceRunner import execute_code_and_capture_prints_last
from utils.vivicoder_runner import evaluate_sample_io
from utils.config_log import config, tracer
from utils.evocodebench import evaluate_print_trace as evaluate_evocodebench_print_trace
from utils.local_runner import parse_response
from utils.model_invoke import invoke_model


SUPPORTED_DATASETS = {"humaneval", "mhpp", "livecodebench", "evocodebench"}
_SYSTEM_PROMPT = (
    "You are a helpful assistant specialized in code generation and debugging."
)


def _model_generator(prompt: str, status: str, _model_name: str):
    """Match TraceCoder's generator contract using the configured project model."""
    response = invoke_model(_SYSTEM_PROMPT, prompt)
    if status in {"code3_generate", "code5_generate"}:
        response = extract_python_code(response)
    return response, 0, 0


def _feedback_test_count(question: dict) -> int:
    if isinstance(question.get("evocodebench"), dict):
        return max(1, len(question["evocodebench"].get("feedback_tests", [])))
    return max(1, len(question.get("sample_io", [])))


def _make_correctness_checker(question: dict, state: dict):
    def check_correctness(_problem_data: dict, completion: str, _timeout: int) -> dict:
        passed, feedback, failed = evaluate_sample_io(question, completion)
        failed = list(failed or [])
        total_count = _feedback_test_count(question)
        if passed:
            passed_count = total_count
        elif failed:
            passed_count = max(0, total_count - len(failed))
        else:
            passed_count = 0

        state["failed"] = failed
        state["feedback"] = feedback
        return {
            "task_id": question.get("question_id"),
            "passed": bool(passed),
            "result": feedback or (
                "All feedback tests passed." if passed else "Feedback test failed."
            ),
            "passed_count": passed_count,
            "failed_count": total_count - passed_count,
            "total_count": total_count,
        }

    return check_correctness


def _run_trace(question: dict, instrumented_code: str, timeout: int) -> str:
    dataset_name = config.get("dataset", {}).get("name", "humaneval").lower()
    if dataset_name == "evocodebench":
        return _run_evocodebench_trace(question, instrumented_code)
    return _run_public_sample_traces(
        question,
        instrumented_code,
        question.get("sample_io", []),
        timeout,
    )


def _run_evocodebench_trace(question: dict, instrumented_code: str) -> str:
    # Preserve TraceCoder's official print() instrumentation. The private
    # evaluator executes it against feedback_tests and returns marked prints.
    evo = question["evocodebench"]
    _, feedback = evaluate_evocodebench_print_trace(
        question,
        instrumented_code,
        timeout=int(evo.get("test_timeout", 120)),
        max_feedback_chars=int(evo.get("max_feedback_chars", 12000)),
    )
    return feedback


def _run_public_sample_traces(
    question: dict,
    instrumented_code: str,
    samples: list,
    timeout: int,
) -> str:
    """Run public samples with TraceCoder's official trace runner.

    Assertions can be appended exactly as TraceCoder appends a dataset's test
    program. AtCoder is the sole format adaptation: each public stdin sample
    receives its own in-memory stdin before the unchanged official runner is
    invoked.
    """
    if not samples:
        return "No public feedback sample is available for trace execution."

    dataset_name = config.get("dataset", {}).get("name", "humaneval").lower()
    is_stdin = dataset_name == "livecodebench" and question.get("platform") == "atcoder"
    code = instrumented_code
    if "from typing import *" not in code:
        code = "from typing import *\n" + code

    if not is_stdin:
        if dataset_name == "livecodebench":
            code += "\n\nsolution = Solution()"
        code += "\n\n" + "\n".join(str(sample) for sample in samples)
        result = execute_code_and_capture_prints_last(
            code,
            timeout_seconds=timeout,
        )
        return result.get("display_output", "No instrumentation output captured.")

    reports = []
    for index, sample in enumerate(samples, 1):
        stdin_setup = (
            "import io as _tracecoder_io\n"
            "import sys as _tracecoder_sys\n"
            f"_tracecoder_sys.stdin = _tracecoder_io.StringIO({sample.get('input', '')!r})\n"
        )
        result = execute_code_and_capture_prints_last(
            stdin_setup + code,
            timeout_seconds=timeout,
        )
        output = result.get("display_output", "No instrumentation output captured.")
        reports.append(f"TraceCoder stdin sample {index}:\n{output}")
    return "\n\n".join(reports)


def _official_defaults() -> dict:
    """Read algorithm defaults from TraceCoder's own argument parser."""
    parser = setup_arg_parser()
    return {
        "timeout": parser.get_default("timeout"),
        "max_debug_attempts": parser.get_default("max_debug_attempts"),
        "max_no_improvement_streak": parser.get_default(
            "max_no_improvement_streak"
        ),
        "no_instrumentation": parser.get_default("no_instrumentation"),
        "no_two_step_repair": parser.get_default("no_two_step_repair"),
    }


@tracer
def TraceCoder(question: dict):
    dataset_name = config.get("dataset", {}).get("name", "humaneval").lower()
    if dataset_name not in SUPPORTED_DATASETS:
        raise ValueError(
            f"TraceCoder supports {sorted(SUPPORTED_DATASETS)}, got {dataset_name!r}."
        )

    defaults = _official_defaults()
    timeout = int(defaults["timeout"])
    state = {"failed": [], "feedback": ""}
    checker = _make_correctness_checker(question, state)
    args = SimpleNamespace(
        model=config.get("model", {}).get("model", ""),
        dataset=dataset_name,
        timeout=timeout,
        max_debug_attempts=int(defaults["max_debug_attempts"]),
        max_no_improvement_streak=int(defaults["max_no_improvement_streak"]),
        no_instrumentation=bool(defaults["no_instrumentation"]),
        no_two_step_repair=bool(defaults["no_two_step_repair"]),
        generator=_model_generator,
        trace_executor=lambda problem, code: _run_trace(
            question, code, timeout
        ),
    )
    problem_data = {
        "task_id": question.get("question_id"),
        "complete_prompt": question.get("prompt", ""),
        # Deliberately empty: only the adapter evaluator may access feedback
        # tests. In particular, EvoCodeBench's complete tests never enter the
        # TraceCoder problem payload.
        "test": "",
    }

    try:
        result = process_problem(
            problem_data,
            question.get("question_id", "unknown"),
            args,
            checker,
        )
        final_code = parse_response(result.get("final_code", ""))
        return f"```python\n{final_code}\n```"
    except Exception as exc:
        logger.exception(
            f"TraceCoder failed for {question.get('question_id')}: "
            f"{type(exc).__name__}: {exc}"
        )
        return "```python\n\n```"
