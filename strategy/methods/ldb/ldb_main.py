import ast
import multiprocessing
import queue
import re
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple

from ..mas_base import MAS
from utils.evocodebench import evaluate as evaluate_evocodebench
from utils.evocodebench import extract_function_body

try:
    from strategy.LLMDebugger.programming.tracing import (
        get_code_traces_block,
        get_code_traces_function,
        get_code_traces_line,
    )
except Exception:
    get_code_traces_block = None
    get_code_traces_function = None
    get_code_traces_line = None


IMPORT_HEADER = (
    "from typing import *\n"
    "import math\n"
    "from heapq import *\n"
    "import itertools\n"
    "import re\n"
    "import typing\n"
    "import heapq\n"
    "_str=str\n"
)


def _exec_worker(code: str, assertion: str, result_queue):
    namespace = {}
    try:
        exec(f"{IMPORT_HEADER}\n{code}\n{assertion}", namespace)
        result_queue.put((True, ""))
    except BaseException as exc:
        result_queue.put((False, f"{type(exc).__name__}: {exc}"))


def _eval_worker(code: str, expression: str, result_queue):
    namespace = {}
    try:
        exec(f"{IMPORT_HEADER}\n{code}", namespace)
        result_queue.put((True, repr(eval(expression, namespace))))
    except BaseException as exc:
        result_queue.put((False, f"{type(exc).__name__}: {exc}"))


class LDB_Main(MAS):
    def __init__(self, general_config, method_config_name=None):
        method_config_name = "config_main" if method_config_name is None else method_config_name
        super().__init__(general_config, method_config_name)
        self.max_iters = int(self.method_config.get("max_iters", 5))
        self.trace_level = self.method_config.get("trace_level", "block")
        self.execution_timeout = int(self.method_config.get("execution_timeout", 5))
        self.max_trace_blocks = int(self.method_config.get("max_trace_blocks", 10))

    def inference(self, sample):
        query = sample["query"]
        if sample.get("evocodebench"):
            return self._inference_evocodebench(query, sample)

        raw_tests = sample.get("sample_io", [])
        stdio_tests = self._normalize_stdio_tests(raw_tests)
        if self._is_stdio_task(sample, stdio_tests):
            return self._inference_stdio(query, sample, stdio_tests)

        tests = self._normalize_tests(raw_tests)
        entry_point = sample.get("entry_point") or self._extract_entry_point(query, tests)

        seed = sample.get("seed") or self._generate_initial_solution(query, tests)
        code = self._normalize_code(seed, query, entry_point)

        if not tests or not entry_point:
            return {"response": code}

        for _ in range(self.max_iters):
            passed, failed_tests = self._execute_tests(code, tests)
            if passed:
                break

            selected_test = failed_tests[0]
            trace_feedback = self._build_trace_feedback(code, selected_test, entry_point)
            debug_analysis = self._debug_with_trace(query, code, selected_test, trace_feedback)
            fixed_code = self._generate_fix(query, code, selected_test, trace_feedback, debug_analysis)
            fixed_code = self._normalize_code(fixed_code, query, entry_point)

            if fixed_code.strip():
                code = fixed_code

        return {"response": code}

    def _inference_evocodebench(self, query: str, sample: dict):
        namespace = sample["evocodebench"]["namespace"]
        seed = sample.get("seed") or self.call_llm(
            system_prompt="You are an expert Python repository maintenance assistant.",
            prompt=(
                "Complete the EvoCodeBench function described below. Return the complete "
                "target function (or just its body) in one Markdown python code block. "
                "The candidate will be inserted into the real subject repository and tested.\n\n"
                f"{query}"
            ),
            temperature=0,
        )
        code = self._parse_code(seed).strip()

        for _ in range(self.max_iters):
            evo = sample["evocodebench"]
            passed, feedback = evaluate_evocodebench(
                sample,
                code,
                timeout=int(evo.get("test_timeout", 120)),
                max_feedback_chars=int(evo.get("max_feedback_chars", 12000)),
            )
            if passed:
                break

            body = extract_function_body(code, namespace)
            fixed = self.call_llm(
                messages=[
                    {
                        "role": "system",
                        "content": "You debug Python functions against repository-level pytest feedback.",
                    },
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": f"```python\n{body}\n```"},
                    {
                        "role": "user",
                        "content": (
                            "The candidate was inserted into the real EvoCodeBench repository "
                            "and failed. Diagnose the failure from the execution output, then "
                            "return the complete corrected target function or function body in "
                            "one Python code block.\n\n"
                            f"{feedback}"
                        ),
                    },
                ],
                temperature=0,
            )
            fixed = self._parse_code(fixed).strip()
            if fixed:
                code = fixed

        return {"response": extract_function_body(code, namespace)}

    def _inference_stdio(self, query: str, sample: dict, tests: List[dict]):
        seed = sample.get("seed") or self._generate_initial_stdio_solution(query, tests)
        code = self._parse_code(seed).strip()

        if not tests:
            return {"response": code}

        for _ in range(self.max_iters):
            passed, failed_tests = self._execute_stdio_tests(code, tests)
            if passed:
                break

            selected_test = failed_tests[0]
            debug_analysis = self._debug_stdio(query, code, selected_test)
            fixed_code = self._generate_stdio_fix(query, code, selected_test, debug_analysis)
            fixed_code = self._parse_code(fixed_code).strip()

            if fixed_code:
                code = fixed_code

        return {"response": code}

    def _generate_initial_solution(self, query: str, tests: List[str]) -> str:
        assertion = tests[0] if tests else "No unit test is provided."
        prompt = (
            "Complete the following task in Python. "
            "Repeat all imports and the full function header. "
            "Respond with code only inside a Markdown python code block.\n\n"
            f"Here is a unit test for reference:\n{assertion}\n\n"
            f"{query}"
        )
        return self.call_llm(
            system_prompt="You are an expert programming assistant.",
            prompt=prompt,
            temperature=0,
        )

    def _generate_initial_stdio_solution(self, query: str, tests: List[dict]) -> str:
        sample_tests = self._format_stdio_tests(tests)
        prompt = (
            "Solve the following programming problem in Python. "
            "Return a complete Python program that reads from standard input and "
            "writes to standard output. Do not use Markdown outside the code block.\n\n"
            f"{query}\n\n"
            f"Sample tests:\n{sample_tests}"
        )
        return self.call_llm(
            system_prompt="You are an expert competitive programming assistant.",
            prompt=prompt,
            temperature=0,
        )

    def _debug_with_trace(
        self,
        query: str,
        code: str,
        failed_test: str,
        trace_feedback: str,
    ) -> str:
        messages = [
            {"role": "system", "content": "You are an expert programming assistant."},
            {
                "role": "user",
                "content": (
                    "Complete the following task in Python. "
                    "Please respond with code only inside a Markdown code block.\n"
                    f"{query}"
                ),
            },
            {"role": "assistant", "content": f"```python\n{code}\n```"},
            {
                "role": "user",
                "content": (
                    "The code above fails the given unit test:\n"
                    f"{failed_test}\n\n"
                    "Help me debug this. Here is the code execution trace with "
                    "intermediate variable values. Explain each block and identify "
                    "which block is incorrect. Return concise JSON lines with keys "
                    "`block`, `correct`, and `explanation`.\n\n"
                    f"{trace_feedback}"
                ),
            },
        ]
        return self.call_llm(messages=messages, temperature=0)

    def _generate_fix(
        self,
        query: str,
        code: str,
        failed_test: str,
        trace_feedback: str,
        debug_analysis: str,
    ) -> str:
        messages = [
            {"role": "system", "content": "You are an expert programming assistant."},
            {
                "role": "user",
                "content": (
                    "Complete the following task in Python. "
                    "Please respond with code only inside a Markdown code block.\n"
                    f"{query}"
                ),
            },
            {"role": "assistant", "content": f"```python\n{code}\n```"},
            {
                "role": "user",
                "content": (
                    "The code fails this unit test:\n"
                    f"{failed_test}\n\n"
                    f"{trace_feedback}\n\n"
                    "Debug analysis:\n"
                    f"{debug_analysis}\n\n"
                    "Please fix the Python code. Return the complete corrected code only."
                ),
            },
        ]
        return self.call_llm(messages=messages, temperature=0)

    def _debug_stdio(self, query: str, code: str, failed_test: str) -> str:
        messages = [
            {"role": "system", "content": "You are an expert competitive programming assistant."},
            {
                "role": "user",
                "content": (
                    "Solve the following programming problem in Python. "
                    "Return a complete Python program that reads from stdin and writes to stdout.\n"
                    f"{query}"
                ),
            },
            {"role": "assistant", "content": f"```python\n{code}\n```"},
            {
                "role": "user",
                "content": (
                    "The program above fails this stdin/stdout sample test:\n"
                    f"{failed_test}\n\n"
                    "Analyze why the program is incorrect. Focus on input parsing, algorithm, "
                    "edge cases, and exact output formatting."
                ),
            },
        ]
        return self.call_llm(messages=messages, temperature=0)

    def _generate_stdio_fix(
        self,
        query: str,
        code: str,
        failed_test: str,
        debug_analysis: str,
    ) -> str:
        messages = [
            {"role": "system", "content": "You are an expert competitive programming assistant."},
            {
                "role": "user",
                "content": (
                    "Solve the following programming problem in Python. "
                    "Return a complete Python program that reads from stdin and writes to stdout.\n"
                    f"{query}"
                ),
            },
            {"role": "assistant", "content": f"```python\n{code}\n```"},
            {
                "role": "user",
                "content": (
                    "The program fails this sample test:\n"
                    f"{failed_test}\n\n"
                    "Debug analysis:\n"
                    f"{debug_analysis}\n\n"
                    "Please fix the Python program. Return the complete corrected code only."
                ),
            },
        ]
        return self.call_llm(messages=messages, temperature=0)

    def _execute_tests(self, code: str, tests: List[str]) -> Tuple[bool, List[str]]:
        failed_tests = []
        for assertion in tests:
            success, error = self._run_assertion(code, assertion)
            if success:
                continue

            expression = self._assert_expression(assertion)
            _, output = self._evaluate_expression(code, expression) if expression else (False, error)
            failed_tests.append(f"{assertion} # Real Execution Output: {output}")

        return len(failed_tests) == 0, failed_tests

    def _execute_stdio_tests(self, code: str, tests: List[dict]) -> Tuple[bool, List[str]]:
        failed_tests = []
        for test in tests:
            passed, actual_output, stderr = self._run_stdio_case(
                code,
                test["input"],
            )
            expected_output = test["output"].strip()
            if passed and actual_output.strip() == expected_output:
                continue

            failed_tests.append(
                "Input:\n"
                f"{test['input']}\n"
                "Expected Output:\n"
                f"{expected_output}\n"
                "Actual Output:\n"
                f"{actual_output.strip()}\n"
                "Stderr:\n"
                f"{stderr.strip()}"
            )

        return len(failed_tests) == 0, failed_tests

    def _run_stdio_case(self, code: str, stdin: str) -> Tuple[bool, str, str]:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as file:
            file.write(f"{IMPORT_HEADER}\n{code}\n")
            file_path = file.name

        try:
            result = subprocess.run(
                [sys.executable, file_path],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=self.execution_timeout,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "TIMEOUT"
        finally:
            try:
                import os

                os.unlink(file_path)
            except OSError:
                pass

    def _run_assertion(self, code: str, assertion: str) -> Tuple[bool, str]:
        result_queue = multiprocessing.Queue()
        process = multiprocessing.Process(target=_exec_worker, args=(code, assertion, result_queue))
        process.start()
        process.join(self.execution_timeout)
        if process.is_alive():
            process.terminate()
            process.join()
            return False, "TIMEOUT"
        return self._read_process_result(result_queue)

    def _evaluate_expression(self, code: str, expression: str) -> Tuple[bool, str]:
        result_queue = multiprocessing.Queue()
        process = multiprocessing.Process(target=_eval_worker, args=(code, expression, result_queue))
        process.start()
        process.join(self.execution_timeout)
        if process.is_alive():
            process.terminate()
            process.join()
            return False, "TIMEOUT"
        return self._read_process_result(result_queue)

    def _read_process_result(self, result_queue) -> Tuple[bool, str]:
        try:
            return result_queue.get_nowait()
        except queue.Empty:
            return False, "No execution result returned."

    def _build_trace_feedback(self, code: str, failed_test: str, entry_point: str) -> str:
        trace_function = {
            "line": get_code_traces_line,
            "function": get_code_traces_function,
        }.get(self.trace_level, get_code_traces_block)

        expression = self._assert_expression(failed_test.split("# Real Execution Output:")[0].strip())
        if trace_function is None or not expression:
            return f"Feedback: `{failed_test}`"

        try:
            trace_blocks = trace_function(IMPORT_HEADER + "\n" + code, expression, entry_point)
        except Exception as exc:
            return f"Feedback: `{failed_test}`\nTrace collection failed: {exc}"

        if isinstance(trace_blocks, str):
            return f"Feedback: `{failed_test}`\nTrace collection result: {trace_blocks}"
        if not trace_blocks:
            return f"Feedback: `{failed_test}`\nNo trace blocks were collected."

        selected_blocks = trace_blocks
        if len(selected_blocks) > self.max_trace_blocks:
            half = max(1, self.max_trace_blocks // 2)
            selected_blocks = selected_blocks[:half] + selected_blocks[-half:]

        rendered_blocks = []
        for index, block in enumerate(selected_blocks):
            rendered_blocks.append(f"[BLOCK-{index}]\n" + "\n".join(block))
        return "\n\n".join(rendered_blocks)

    def _normalize_tests(self, tests) -> List[str]:
        if not tests:
            return []
        normalized = []
        for test in tests:
            if isinstance(test, str):
                stripped = test.strip()
                if stripped.startswith("assert "):
                    normalized.append(stripped)
        return normalized

    def _normalize_stdio_tests(self, tests) -> List[dict]:
        if not tests:
            return []

        normalized = []
        for test in tests:
            if not isinstance(test, dict):
                continue
            if "input" not in test or "output" not in test:
                continue
            normalized.append(
                {
                    "input": self._normalize_stdio_value(test["input"]),
                    "output": self._normalize_stdio_value(test["output"]),
                }
            )
        return normalized

    def _normalize_stdio_value(self, value) -> str:
        if isinstance(value, list):
            return "\n".join(str(item) for item in value)
        return str(value)

    def _is_stdio_task(self, sample: dict, stdio_tests: List[dict]) -> bool:
        if not stdio_tests:
            return False
        if sample.get("platform") == "atcoder":
            return True

        prompt = sample.get("query", "")
        return bool(re.search(r"\bstandard input\b|\bstdin\b|\bstandard output\b|\bstdout\b", prompt, re.IGNORECASE))

    def _format_stdio_tests(self, tests: List[dict]) -> str:
        formatted = []
        for index, test in enumerate(tests, start=1):
            formatted.append(
                f"Sample {index}\n"
                f"Input:\n{test['input']}\n"
                f"Output:\n{test['output']}"
            )
        return "\n\n".join(formatted)

    def _normalize_code(self, response: str, query: str, entry_point: Optional[str]) -> str:
        code = self._parse_code(response).strip()
        code = code.replace(IMPORT_HEADER, "").strip()

        if entry_point and self._defines_entry_point(code, entry_point):
            return code

        if entry_point and self._defines_entry_point(query, entry_point):
            return self._merge_prompt_and_body(query, code)

        return code

    def _parse_code(self, response: str) -> str:
        if response is None:
            return ""
        if "<think>" in response and "</think>" in response:
            response = response.split("</think>", 1)[1]

        fenced = re.findall(r"```(?:python|Python|py)?\s*(.*?)```", response, re.DOTALL)
        if fenced:
            return fenced[-1].strip()
        return response.strip()

    def _merge_prompt_and_body(self, query: str, code: str) -> str:
        if not code:
            return query
        if re.search(r"^\s*def\s+\w+\s*\(", code, re.MULTILINE):
            return code

        body = code
        if not all((not line.strip()) or line.startswith((" ", "\t")) for line in body.splitlines()):
            body = "\n".join("    " + line if line.strip() else line for line in body.splitlines())
        return query.rstrip() + "\n" + body

    def _defines_entry_point(self, code: str, entry_point: str) -> bool:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False
        return any(isinstance(node, ast.FunctionDef) and node.name == entry_point for node in tree.body)

    def _extract_entry_point(self, query: str, tests: List[str]) -> Optional[str]:
        try:
            tree = ast.parse(query)
            function_names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
            if function_names:
                return function_names[-1]
        except SyntaxError:
            pass

        for test in tests:
            match = re.search(r"assert\s+([A-Za-z_]\w*)\s*\(", test)
            if match:
                return match.group(1)
        return None

    def _assert_expression(self, assertion: str) -> Optional[str]:
        try:
            node = ast.parse(assertion).body[0]
        except SyntaxError:
            return None

        if not isinstance(node, ast.Assert):
            return None

        expression = node.test.left if isinstance(node.test, ast.Compare) else node.test
        return ast.unparse(expression).strip()
