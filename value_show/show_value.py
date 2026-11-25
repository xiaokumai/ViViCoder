from __future__ import annotations

import requests
from langchain_core.prompts import PromptTemplate

from utils.config_log import tracer, config
from utils.evocodebench import evaluate_debug as evaluate_evocodebench_debug
from utils.language import (
    get_language,
    language_display,
    language_fence,
    sample_stdin,
    sample_stdout,
    uses_standard_input,
)
from utils.local_runner import parse_response
from utils.model_invoke import invoke_model
from value_show.prompt import (
    BUG_INPUT,
    CPP_BUG_PROMPT,
    JAVA_BUG_PROMPT,
    PYTHON_BUG_PROMPT,
)


@tracer
def show_value(question: dict, prompt: str, code: str, test_log: str):
    language = get_language(question)
    systems = {
        "python": PYTHON_BUG_PROMPT,
        "cpp": CPP_BUG_PROMPT,
        "java": JAVA_BUG_PROMPT,
    }
    user_input = PromptTemplate.from_template(BUG_INPUT).format(
        prompt=prompt,
        code=code,
        test_log=test_log,
        lang=language_display(language),
        fence=language_fence(language),
    )
    return parse_response(invoke_model(systems[language], user_input))


def insert_ic_config(source: str) -> str:
    insert_after = "from icecream import ic"
    block = '''
import re

def custom_output(text):
    remainder = text.split(":", 1)[1] if ":" in text else text
    match = re.search(r"\\d+", remainder)
    if match:
        remainder = remainder.replace(match.group(), "", 1).strip()
    print(remainder)

ic.configureOutput(includeContext=True, outputFunction=custom_output)
'''
    result = []
    for line in source.splitlines():
        result.append(line)
        if line.strip() == insert_after:
            result.append(block)
    return "\n".join(result)


def truncate_test_log(test_log: str, max_length: int = 1500) -> str:
    if len(test_log) <= max_length:
        return test_log
    truncated = test_log[:max_length]
    last_newline = truncated.rfind("\n")
    if last_newline != -1:
        truncated = truncated[:last_newline]
    return truncated + "\n...[truncated]...\n"


def remove_ic_import(source: str) -> str:
    return "\n".join(
        line
        for line in source.splitlines()
        if line.strip() != "from icecream import ic"
    )


def _prepare_python_trace(code: str) -> str:
    code = remove_ic_import(code)
    code = "from icecream import ic\n" + code
    code = insert_ic_config(code)
    if "from typing import *" not in code:
        code = "from typing import *\n" + code
    return code


def _run_code(code: str, language: str, stdin: str = "") -> dict:
    payload = {
        "code": code,
        "stdin": stdin,
        "language": language,
        "run_timeout": 50 if language != "python" else 20,
        "compile_timeout": 50 if language != "python" else 20,
    }
    return requests.post("http://localhost:8081/run_code", json=payload).json()


def _execution_stream(result: dict, stream: str) -> str:
    run_result = result.get("run_result") or {}
    compile_result = result.get("compile_result") or {}
    value = run_result.get(stream, "")
    if value:
        return str(value)
    if compile_result.get("stderr"):
        return f"Compilation diagnostics:\n{compile_result['stderr']}"
    status = run_result.get("status") or result.get("status")
    return f"Execution status: {status}" if status else "No trace output was produced."


def _ordinary_stdout(code: str, language: str, sample: dict) -> str:
    result = _run_code(code, language, sample_stdin(sample))
    return str((result.get("run_result") or {}).get("stdout", "")).strip()


def ic_assertion_io(question: dict, code: str, failed: list) -> str:
    """Run Python assertion-style public failures with IceCream instrumentation."""
    dataset_name = str(question.get("dataset_name") or config.get("dataset", {}).get("name", "humaneval"))
    code = _prepare_python_trace(code)
    if dataset_name == "livecodebench" and question.get("platform") != "atcoder":
        code += "\n\nsolution = Solution()\n"

    logs = []
    for num, sample in enumerate(failed, 1):
        result = _run_code(f"{code}\n\n{sample}\n", "python")
        trace = _execution_stream(result, "stdout")
        logs.append(
            f"{num}. {sample}\n"
            + truncate_test_log(
                "How key variables and expressions change during execution:\n"
                + trace
                + "\n"
            )
        )
    return "".join(logs)


def ic_stdin_io(question: dict, code: str, ic_code: str, failed: list) -> str:
    """Run standard-input traces for Python, C++, and Java without polluting stdout."""
    language = get_language(question)
    if language == "python":
        ic_code = _prepare_python_trace(ic_code)

    logs = []
    trace_stream = "stdout" if language == "python" else "stderr"
    for num, sample in enumerate(failed, 1):
        result = _run_code(ic_code, language, sample_stdin(sample))
        trace = _execution_stream(result, trace_stream)
        output = _ordinary_stdout(code, language, sample)
        logs.append(
            f"{num}.\nInput:\n{sample_stdin(sample)}\n"
            f"Expected Output:\n{sample_stdout(sample)}\n"
            f"Your Output:\n{output}\n"
            + truncate_test_log(
                "How key variables and expressions change during execution:\n"
                + trace
                + "\n"
            )
        )
    return "".join(logs)


def evaluate_evo(question: dict, completion: str) -> str:
    evo = question["evocodebench"]
    _, feedback = evaluate_evocodebench_debug(
        question,
        completion,
        timeout=int(evo.get("test_timeout", 120)),
        max_feedback_chars=int(evo.get("max_feedback_chars", 12000)),
    )
    return feedback


def run_ic(question: dict, code: str, ic_code: str, failed: list) -> str:
    dataset_name = str(question.get("dataset_name") or config.get("dataset", {}).get("name", "humaneval"))
    if dataset_name == "evocodebench":
        return evaluate_evo(question, ic_code)
    if uses_standard_input(question):
        return ic_stdin_io(question, code, ic_code, failed)
    if get_language(question) != "python":
        raise ValueError("C++ and Java trace debugging is supported for standard-input tasks")
    return ic_assertion_io(question, ic_code, failed)
