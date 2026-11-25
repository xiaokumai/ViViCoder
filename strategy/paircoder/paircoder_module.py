import argparse
import asyncio
import ast
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

RUNTIME_DEPS: Optional[dict[str, Any]] = None


def _load_runtime_dependencies() -> dict[str, Any]:
    global RUNTIME_DEPS
    if RUNTIME_DEPS is not None:
        return RUNTIME_DEPS
    try:
        from .gen.driver import analyze_code_from_string, fix_code_errors, generate_initial_solve
        from .gen.methods_flow import pair_programming
        from .gen.navigator import (
            analyze_code_errors,
            choose_best_solution_by_LLM,
            generate_possible_solutions,
            generate_reflection,
        )
        from .gen.utils import render, set_configurations
        from .llm.ai_handler import AiHandler
        from .log import setup_logger
        from .settings.config_loader import get_settings
    except ImportError:
        from gen.driver import analyze_code_from_string, fix_code_errors, generate_initial_solve
        from gen.methods_flow import pair_programming
        from gen.navigator import (
            analyze_code_errors,
            choose_best_solution_by_LLM,
            generate_possible_solutions,
            generate_reflection,
        )
        from gen.utils import render, set_configurations
        from llm.ai_handler import AiHandler
        from log import setup_logger
        from settings.config_loader import get_settings
    RUNTIME_DEPS = {
        "AiHandler": AiHandler,
        "analyze_code_errors": analyze_code_errors,
        "analyze_code_from_string": analyze_code_from_string,
        "choose_best_solution_by_LLM": choose_best_solution_by_LLM,
        "fix_code_errors": fix_code_errors,
        "generate_initial_solve": generate_initial_solve,
        "generate_possible_solutions": generate_possible_solutions,
        "generate_reflection": generate_reflection,
        "get_settings": get_settings,
        "pair_programming": pair_programming,
        "render": render,
        "set_configurations": set_configurations,
        "setup_logger": setup_logger,
    }
    return RUNTIME_DEPS


@dataclass
class CodeRequirement:
    description: str
    public_inputs: list[str] = field(default_factory=list)
    public_outputs: list[str] = field(default_factory=list)
    io_format: str = "normal"
    name: str = "custom_requirement"


def _strip_code_block(text: str) -> str:
    return text.strip() if isinstance(text, str) else ""


def _serialize_call_args(call_node: ast.Call) -> str:
    if call_node.keywords:
        raise ValueError("assert-based sample_io with keyword arguments is not supported")
    arg_sources = [ast.unparse(arg) for arg in call_node.args]
    if len(arg_sources) == 0:
        return "()"
    if len(arg_sources) == 1:
        return f"({arg_sources[0]},)"
    return f"({', '.join(arg_sources)})"


def _parse_assert_sample(sample: str) -> tuple[str, str]:
    try:
        module = ast.parse(sample.strip())
    except SyntaxError as exc:
        raise ValueError(f"Invalid assert sample: {sample}") from exc
    if len(module.body) != 1 or not isinstance(module.body[0], ast.Assert):
        raise ValueError("Each string sample_io item must be a single assert statement")

    test_node = module.body[0].test
    call_node = None
    expected_node = None

    if isinstance(test_node, ast.Compare) and len(test_node.ops) == 1 and len(test_node.comparators) == 1:
        left_node = test_node.left
        right_node = test_node.comparators[0]
        op_node = test_node.ops[0]
        if isinstance(left_node, ast.Call) and isinstance(op_node, (ast.Eq, ast.Is)):
            call_node = left_node
            expected_node = right_node
        elif isinstance(right_node, ast.Call) and isinstance(op_node, (ast.Eq, ast.Is)):
            call_node = right_node
            expected_node = left_node
    elif isinstance(test_node, ast.Call):
        call_node = test_node
        expected_node = ast.Constant(value=True)
    elif isinstance(test_node, ast.UnaryOp) and isinstance(test_node.op, ast.Not) and isinstance(test_node.operand, ast.Call):
        call_node = test_node.operand
        expected_node = ast.Constant(value=False)

    if call_node is None or expected_node is None:
        raise ValueError("Unsupported assert sample_io format")

    return _serialize_call_args(call_node), ast.unparse(expected_node)


def normalize_sample_io(sample_io: Optional[list[Any]]) -> tuple[list[str], list[str], Optional[str], list[str]]:
    if not sample_io:
        return [], [], None, []
    if all(isinstance(item, str) for item in sample_io):
        public_inputs = []
        public_outputs = []
        display_examples = []
        for item in sample_io:
            test_input, test_output = _parse_assert_sample(item)
            public_inputs.append(test_input)
            public_outputs.append(test_output)
            display_examples.append(item.strip())
        return public_inputs, public_outputs, "normal", display_examples
    if all(isinstance(item, dict) for item in sample_io):
        public_inputs = []
        public_outputs = []
        display_examples = []
        for item in sample_io:
            if "input" not in item or "output" not in item:
                raise ValueError("Each dict sample_io item must contain 'input' and 'output'")
            sample_input = _strip_code_block(item["input"])
            sample_output = _strip_code_block(item["output"])
            public_inputs.append(sample_input)
            public_outputs.append(sample_output)
            display_examples.append(f"Input:\n{sample_input}\nOutput:\n{sample_output}")
        return public_inputs, public_outputs, "contest", display_examples
    raise ValueError("sample_io must be a list of assert strings or a list of input/output dicts")


def append_public_examples(description: str, display_examples: list[str], sample_kind: Optional[str]) -> str:
    description = description.strip()
    if not display_examples:
        return description
    if sample_kind == "normal":
        example_lines = ["", "Public test cases:"]
        for index, example in enumerate(display_examples):
            example_lines.append(f"Example {index}:")
            example_lines.append(example)
        return "\n".join([description, *example_lines]).strip()
    example_lines = ["", "Public test cases:"]
    for index, example in enumerate(display_examples):
        example_lines.append(f"Example {index}:")
        example_lines.append(example)
    return "\n".join([description, *example_lines]).strip()


def normalize_problem_dict(problem_data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(problem_data, dict):
        raise ValueError("problem_data must be a dict")
    prompt = problem_data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("problem_data['prompt'] must be a non-empty string")

    public_inputs, public_outputs, inferred_io_format, display_examples = normalize_sample_io(problem_data.get("sample_io"))
    is_evocodebench = isinstance(problem_data.get("evocodebench"), dict)
    io_format = (
        "repository"
        if is_evocodebench
        else problem_data.get("io_format") or inferred_io_format or "normal"
    )
    name = (
        problem_data.get("task_id")
        or problem_data.get("question_id")
        or problem_data.get("name")
        or "custom_requirement"
    )
    description = append_public_examples(prompt, display_examples, io_format)
    normalized_problem = {
        "name": name,
        "description": description,
        "io_format": io_format,
        "public_tests": {
            "input": public_inputs,
            "output": public_outputs,
        },
    }
    for key in (
        "question_id",
        "task_id",
        "num_samples",
        "prompt",
        "sample_io",
        "evocodebench",
        "completion_path",
        "feedback_tests",
    ):
        if key in problem_data:
            normalized_problem[key] = problem_data[key]
    return normalized_problem


class PairCoderGenerator:
    def __init__(self, log_path: Optional[str] = None):
        self._deps = _load_runtime_dependencies()
        self.prompt = {}
        settings = self._deps["get_settings"]()
        for setting_name in settings:
            if "prompt" in setting_name.lower():
                self.prompt[setting_name.lower()] = settings[setting_name]
        self.ai_handler = self._deps["AiHandler"]()
        self.log_path = log_path
        if log_path:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            self._deps["setup_logger"](logger_path=log_path)

    async def send_inference(self, problem, prompt: str = "prompt_direct_generate_code"):
        (
            system_prompt,
            user_prompt,
            model,
            temperature,
            frequency_penalty,
            sample_count,
            top_p,
        ) = self._deps["render"](self, problem, prompt)
        return await self.ai_handler.chat_completion(
            model=model,
            system=system_prompt,
            user=user_prompt,
            temperature=temperature,
            frequency_penalty=frequency_penalty,
            n=sample_count,
            top_p=top_p,
        )

    def build_problem(
        self,
        requirement: str,
        public_inputs: Optional[list[str]] = None,
        public_outputs: Optional[list[str]] = None,
        io_format: str = "normal",
        name: str = "custom_requirement",
    ) -> dict[str, Any]:
        public_inputs = public_inputs or []
        public_outputs = public_outputs or []
        if len(public_inputs) != len(public_outputs):
            raise ValueError("public_inputs and public_outputs must have the same length")
        return {
            "name": name,
            "description": requirement.strip(),
            "io_format": io_format,
            "public_tests": {
                "input": public_inputs,
                "output": public_outputs,
            },
        }

    def build_problem_from_dict(self, problem_data: dict[str, Any]) -> dict[str, Any]:
        return normalize_problem_dict(problem_data)

    async def _run_without_tests(self, problem: dict[str, Any], iteration: int) -> dict[str, Any]:
        problem = self._deps["set_configurations"](problem, iteration)
        problem = await self._deps["generate_reflection"](self, problem)
        problem = await self._deps["generate_possible_solutions"](self, problem)
        problem = await self._deps["choose_best_solution_by_LLM"](self, problem)
        problem = await self._deps["generate_initial_solve"](self, problem)

        settings = self._deps["get_settings"]()
        if settings.get("initial_code_generation.static_analysis", True):
            max_attempts = settings.get("initial_code_generation.max_attempts", 5)
            for _ in range(max_attempts):
                success, error_str = self._deps["analyze_code_from_string"](problem["code_recent_solution"])
                if success:
                    break
                problem["error_str"] = error_str
                problem["error_type"] = "runtime"
                problem = await self._deps["analyze_code_errors"](self, problem, prompt_type="static")
                problem = await self._deps["fix_code_errors"](self, problem, prompt_type="static")
        return problem

    async def _generate_problem(self, problem: dict[str, Any], iteration: int = 0) -> dict[str, Any]:
        if problem.get("evocodebench"):
            return await self._run_with_repository_tests(problem, iteration)
        if problem["public_tests"]["input"]:
            return await self._deps["pair_programming"](self, problem, iteration)
        return await self._run_without_tests(problem, iteration)

    async def _run_with_repository_tests(
        self,
        problem: dict[str, Any],
        iteration: int,
    ) -> dict[str, Any]:
        """Run PairCoder's repair loop against EvoCodeBench project pytest tests."""
        from utils.evocodebench import evaluate as evaluate_evocodebench

        problem = self._deps["set_configurations"](problem, iteration)
        problem = await self._deps["generate_reflection"](self, problem)
        problem = await self._deps["generate_possible_solutions"](self, problem)
        problem = await self._deps["choose_best_solution_by_LLM"](self, problem)
        problem = await self._deps["generate_initial_solve"](self, problem)

        settings = self._deps["get_settings"]()
        max_attempts = int(settings.get("solve.max_coding_count", 10))
        evo = problem["evocodebench"]
        problem["repository_test_history"] = []
        problem["coding_count"] = 1

        while problem["coding_count"] <= max_attempts:
            passed, feedback = evaluate_evocodebench(
                problem,
                problem["code_recent_solution"],
                timeout=int(evo.get("test_timeout", 120)),
                max_feedback_chars=int(evo.get("max_feedback_chars", 12000)),
            )
            problem["repository_test_history"].append(
                {
                    "attempt": problem["coding_count"],
                    "passed": passed,
                    "feedback": feedback,
                }
            )
            if passed:
                break
            if problem["coding_count"] >= max_attempts:
                break

            problem["error_str"] = feedback
            problem["error_type"] = self._repository_error_type(feedback)
            problem = await self._deps["analyze_code_errors"](
                self,
                problem,
                prompt_type="runtime",
            )
            problem = await self._deps["fix_code_errors"](
                self,
                problem,
                prompt_type="runtime",
            )
            problem["coding_count"] += 1

        return problem

    @staticmethod
    def _repository_error_type(feedback: str) -> str:
        lowered = feedback.lower()
        if "timeout" in lowered or "timed out" in lowered:
            return "timeout"
        runtime_markers = (
            "syntax check failed",
            "execution error",
            "traceback",
            "modulenotfounderror",
            "importerror",
            "collection error",
        )
        if any(marker in lowered for marker in runtime_markers):
            return "runtime"
        return "logic"

    async def generate_with_details(
        self,
        requirement: Optional[str] = None,
        public_inputs: Optional[list[str]] = None,
        public_outputs: Optional[list[str]] = None,
        io_format: str = "normal",
        name: str = "custom_requirement",
        iteration: int = 0,
        problem_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if isinstance(requirement, dict):
            problem_data = requirement
            requirement = None
        self.ai_handler.reset_stats()
        if problem_data is not None:
            problem = self.build_problem_from_dict(problem_data)
        else:
            if requirement is None:
                raise ValueError("requirement is required when problem_data is not provided")
            problem = self.build_problem(
                requirement=requirement,
                public_inputs=public_inputs,
                public_outputs=public_outputs,
                io_format=io_format,
                name=name,
            )
        problem = await self._generate_problem(problem, iteration=iteration)
        return {
            "code": problem["code_recent_solution"],
            "problem": problem,
            "used_public_tests": bool(problem["public_tests"]["input"]),
            "used_repository_tests": bool(problem.get("evocodebench")),
            "usage": self.ai_handler.get_stats(),
        }

    def generate(
        self,
        requirement: Optional[str] = None,
        public_inputs: Optional[list[str]] = None,
        public_outputs: Optional[list[str]] = None,
        io_format: str = "normal",
        name: str = "custom_requirement",
        iteration: int = 0,
        problem_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if isinstance(requirement, dict):
            problem_data = requirement
            requirement = None
        result = asyncio.run(
            self.generate_with_details(
                requirement=requirement,
                public_inputs=public_inputs,
                public_outputs=public_outputs,
                io_format=io_format,
                name=name,
                iteration=iteration,
                problem_data=problem_data,
            )
        )
        return result


def _load_json_list(raw_value: Optional[str], field_name: str) -> list[str]:
    if raw_value is None:
        return []
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be a JSON array of strings") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a JSON array of strings")
    return value


def main():
    parser = argparse.ArgumentParser(description="Generate Python code from a requirement using PairCoder.")
    parser.add_argument("--requirement", required=False, type=str)
    parser.add_argument("--public-inputs", type=str, default=None)
    parser.add_argument("--public-outputs", type=str, default=None)
    parser.add_argument("--io-format", type=str, default="normal", choices=["normal", "contest"])
    parser.add_argument("--name", type=str, default="custom_requirement")
    parser.add_argument("--problem-json", type=str, default=None)
    parser.add_argument("--log-path", type=str, default=None)
    args = parser.parse_args()

    generator = PairCoderGenerator(log_path=args.log_path)
    try:
        if args.problem_json is not None:
            result = generator.generate(problem_data=json.loads(args.problem_json))
        else:
            if not args.requirement:
                raise ValueError("--requirement is required when --problem-json is not provided")
            public_inputs = _load_json_list(args.public_inputs, "public_inputs")
            public_outputs = _load_json_list(args.public_outputs, "public_outputs")
            result = generator.generate(
                requirement=args.requirement,
                public_inputs=public_inputs,
                public_outputs=public_outputs,
                io_format=args.io_format,
                name=args.name,
            )
    except Exception as exc:
        logging.error("Failed to generate code: %s", exc)
        raise
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
