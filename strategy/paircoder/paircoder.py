import ast

from loguru import logger

from strategy.paircoder import PairCoderGenerator
from utils.config_log import tracer


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If):
        return False

    test = node.test
    if (
        not isinstance(test, ast.Compare)
        or len(test.ops) != 1
        or not isinstance(test.ops[0], ast.Eq)
        or len(test.comparators) != 1
    ):
        return False

    left = test.left
    right = test.comparators[0]
    return (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and isinstance(right, ast.Constant)
        and right.value == "__main__"
    ) or (
        isinstance(right, ast.Name)
        and right.id == "__name__"
        and isinstance(left, ast.Constant)
        and left.value == "__main__"
    )


def remove_main_block(code_str: str) -> str:
    """Remove top-level ``if __name__ == "__main__"`` blocks from Python code."""
    if not isinstance(code_str, str) or not code_str.strip():
        return code_str

    try:
        tree = ast.parse(code_str)
    except SyntaxError:
        logger.warning("Unable to parse PairCoder output while removing its main guard")
        return code_str

    removed_lines = set()
    for node in tree.body:
        if _is_main_guard(node):
            removed_lines.update(range(node.lineno, node.end_lineno + 1))

    if not removed_lines:
        return code_str

    lines = code_str.splitlines(keepends=True)
    cleaned = "".join(
        line
        for line_number, line in enumerate(lines, start=1)
        if line_number not in removed_lines
    )
    return cleaned.rstrip()


def _uses_assertion_function_io(question: dict, result: dict) -> bool:
    problem = result.get("problem")
    if isinstance(problem, dict) and problem.get("io_format"):
        return problem["io_format"] == "normal"

    sample_io = question.get("sample_io")
    return (
        isinstance(sample_io, list)
        and bool(sample_io)
        and all(isinstance(sample, str) for sample in sample_io)
    )


@tracer
def paircoder(question: dict):
    try:
        generator = PairCoderGenerator()
        question["prompt"] = (
            question["prompt"] + "Package your code in ```python ... ```."
        )
        res = generator.generate(question)
        code = res["code"]
        if _uses_assertion_function_io(question, res):
            code = remove_main_block(code)
        return code, res["usage"]
    except Exception:
        logger.exception(
            "PairCoder generation failed for task {}",
            question.get("task_id") or question.get("question_id") or "<unknown>",
        )
        return "", {
            "api_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
