"""FlowGen software-development workflows adapted to the MAS interface.

The upstream implementation in ``strategy/FlowGen-LLM`` stores every activity
in a JSON log and calls a legacy, hard-coded OpenAI client.  This adapter keeps
the same roles and activity ordering, while routing all model calls through
``MAS.call_llm`` and keeping workflow state in memory.
"""

from __future__ import annotations

import json
import re
from typing import Any

from strategy.methods.mas_base.mas_base import MAS


SUPPORTED_DATASETS = frozenset(
    {
        "humaneval",
        "humaneval-et",
        "humanevalplus",
        "mbpp",
        "mbpp-et",
        "mhpp",
        "livecodebench",
        "evocodebench",
    }
)
SUPPORTED_WORKFLOWS = frozenset({"rawgpt", "waterfall", "testdriven", "scrum"})


class FlowGen_Main(MAS):
    """Run one of FlowGen's official development-process workflows."""

    def __init__(self, general_config: dict[str, Any]):
        super().__init__(general_config)
        flowgen_config = general_config.get("flowgen", {})
        workflow = str(flowgen_config.get("workflow", "waterfall")).lower().strip()
        workflow = {
            "raw": "rawgpt",
            "raw_gpt": "rawgpt",
            "tdd": "testdriven",
            "test-driven": "testdriven",
        }.get(workflow, workflow)
        if workflow not in SUPPORTED_WORKFLOWS:
            choices = ", ".join(sorted(SUPPORTED_WORKFLOWS))
            raise ValueError(f"Unsupported FlowGen workflow {workflow!r}; choose one of: {choices}")
        self.workflow = workflow

    def inference(self, sample: dict[str, Any]) -> dict[str, Any]:
        query = sample.get("query") or sample.get("prompt")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("FlowGen requires a non-empty sample['query'] or sample['prompt']")

        dataset = str(
            sample.get("dataset")
            or sample.get("dataset_name")
            or "humaneval"
        ).lower().strip()
        if dataset not in SUPPORTED_DATASETS:
            choices = ", ".join(sorted(SUPPORTED_DATASETS))
            raise ValueError(f"Unsupported FlowGen dataset {dataset!r}; supported datasets: {choices}")

        task = self._task_description(sample, query, dataset)
        runner = getattr(self, f"_run_{self.workflow}")
        response = self._extract_code(runner(task))
        if not response:
            raise ValueError("FlowGen finished without producing code")
        return {
            "response": response,
            "workflow": self.workflow,
            "dataset": dataset,
        }

    def _activity(
        self,
        *,
        role: str,
        instruction: str,
        question: str,
        context: str = "",
        example: str = "",
    ) -> str:
        """Build the JSON-shaped prompt used by the official FlowGen templates."""

        prompt = {
            "Role": role,
            "Instruction": instruction,
            "Example": example,
            "Context": context,
            "Question": question,
        }
        return self.call_llm(prompt=json.dumps(prompt, ensure_ascii=False))

    @staticmethod
    def _sample_io_text(sample_io: Any) -> str:
        if not sample_io:
            return "No public sample cases were provided."
        if isinstance(sample_io, str):
            return sample_io

        rendered = []
        for item in sample_io:
            if isinstance(item, str):
                rendered.append(item)
            elif isinstance(item, dict):
                expected = item.get("output", item.get("expected_output", ""))
                if isinstance(expected, list) and len(expected) == 1:
                    expected = expected[0]
                rendered.append(
                    f"Input:\n{item.get('input', '')}\nExpected output:\n{expected}"
                )
            else:
                rendered.append(str(item))
        return "\n\n".join(rendered)

    def _task_description(
        self, sample: dict[str, Any], query: str, dataset: str
    ) -> str:
        sample_io = self._sample_io_text(sample.get("sample_io"))

        if dataset == "livecodebench":
            if str(sample.get("platform", "")).lower() == "atcoder":
                contract = (
                    "Return a complete Python program that reads from standard input and "
                    "writes only the required answer to standard output."
                )
            else:
                contract = (
                    "Return the complete Python callable or Solution class requested by "
                    "the problem, preserving its exact public entry point."
                )
        elif dataset == "evocodebench":
            namespace = sample.get("question_id", sample.get("task_id", "the target function"))
            contract = (
                f"Complete only {namespace}. Preserve its signature and surrounding-project "
                "API assumptions. Do not create tests, edit unrelated functions, or emit a "
                "patch; return Python implementation code."
            )
        else:
            contract = (
                "Return a complete Python implementation that preserves the requested "
                "function signature. Do not include tests, demonstrations, or prose."
            )

        return (
            f"# Benchmark\n{dataset}\n\n"
            f"# Output contract\n{contract}\n\n"
            f"# Public sample cases\n{sample_io}\n\n"
            f"# Requirement\n{query}"
        )

    def _review(
        self,
        document: str,
        *,
        subject: str,
        reviewers: str,
        task: str,
    ) -> str:
        return self._activity(
            role="I want you to act as different software-development roles.",
            instruction=(
                f"Review the {subject} against the requirement. Act as {reviewers}. "
                "Identify concrete correctness, edge-case, interface, and efficiency issues."
            ),
            context=f"# Requirement\n{task}\n\n# {subject.title()}\n{document}",
            question="Return concise, actionable review suggestions.",
        )

    def _revise_document(
        self,
        draft: str,
        review: str,
        *,
        role: str,
        subject: str,
        task: str,
    ) -> str:
        return self._activity(
            role=role,
            instruction=(
                f"Revise the draft {subject} using all valid review suggestions. "
                "Keep it focused on the supplied requirement."
            ),
            context=f"# Review\n{review}\n\n# Draft {subject}\n{draft}",
            question=f"Produce the final {subject} for:\n{task}",
        )

    def _write_code(self, task: str, context: str) -> str:
        return self._activity(
            role=(
                "You are a professional software engineer. Write correct, efficient, "
                "readable Python and provide no explanation."
            ),
            instruction=(
                "Implement the requirement according to the supplied development artifacts. "
                "Follow the output contract exactly and return only code."
            ),
            context=context,
            question=f"Complete this requirement:\n{task}",
        )

    def _revise_code(self, task: str, code: str, feedback: str) -> str:
        revised = self._activity(
            role=(
                "You are a professional software engineer responsible for the final "
                "correct implementation."
            ),
            instruction=(
                "Fix every valid issue in the review. Preserve the required signature and "
                "I/O contract. Return only the complete revised Python code."
            ),
            context=f"# Original code\n{code}\n\n# Review\n{feedback}",
            question=f"Complete this requirement:\n{task}",
        )
        return self._extract_code(revised) or self._extract_code(code)

    def _design_tests(self, task: str, context: str = "") -> str:
        return self._activity(
            role="You are a quality assurance engineer.",
            instruction=(
                "Design concise public-facing test scenarios from the requirement and given "
                "samples. Cover edge cases and interface rules. Do not invent hidden tests "
                "or execute code."
            ),
            context=context,
            question=f"Describe test cases for:\n{task}",
        )

    def _run_rawgpt(self, task: str) -> str:
        return self._write_code(task, "")

    def _run_waterfall(self, task: str) -> str:
        # Requirement Analysis (official waterfall stages 1-4).
        prd_draft = self._activity(
            role="You are a professional product manager.",
            instruction=(
                "Analyze the requirement and write a high-level product requirement document. "
                "Do not provide implementation code."
            ),
            question=task,
        )
        prd_review = self._review(
            prd_draft,
            subject="product requirement document",
            reviewers="an architect and a tester",
            task=task,
        )
        final_prd = self._revise_document(
            prd_draft,
            prd_review,
            role="You are a professional product manager.",
            subject="product requirement document",
            task=task,
        )

        # Program Design (official waterfall stages 5-7).
        design_draft = self._activity(
            role="You are a professional software architect.",
            instruction=(
                "Write a high-level design that guides implementation without writing code."
            ),
            context=f"# Product requirement document\n{final_prd}",
            question=f"Design a solution for:\n{task}",
        )
        design_review = self._review(
            design_draft,
            subject="design",
            reviewers="a developer and a tester",
            task=task,
        )
        final_design = self._revise_document(
            design_draft,
            design_review,
            role="You are a professional software architect.",
            subject="design",
            task=task,
        )

        # Development and code review (official waterfall stages 8-10).
        code = self._extract_code(
            self._write_code(
                task,
                f"# Product requirement document\n{final_prd}\n\n# Design\n{final_design}",
            )
        )
        code_review = self._review(
            code,
            subject="code",
            reviewers="an architect and a tester",
            task=task,
        )
        code = self._revise_code(task, code, code_review)

        # Testing and bug fixing (official waterfall stages 11-15).  The
        # upstream code executes an LLM-authored test script directly; here the
        # same roles perform a review using only public task information.
        test_draft = self._design_tests(
            task,
            f"# Product requirement document\n{final_prd}\n\n# Design\n{final_design}",
        )
        test_review = self._review(
            test_draft,
            subject="test cases",
            reviewers="an architect and a developer",
            task=task,
        )
        final_tests = self._revise_document(
            test_draft,
            test_review,
            role="You are a quality assurance engineer.",
            subject="test cases",
            task=task,
        )
        self_test = self._review(
            code,
            subject="code",
            reviewers="a developer performing self-test against the proposed test cases",
            task=f"{task}\n\n# Proposed test cases\n{final_tests}",
        )
        return self._revise_code(task, code, self_test)

    def _run_testdriven(self, task: str) -> str:
        analysis_draft = self._activity(
            role="You are a professional requirements analyst.",
            instruction="Analyze the requirement at a high level without implementation code.",
            question=task,
        )
        analysis_review = self._review(
            analysis_draft,
            subject="requirement analysis",
            reviewers="an architect and a tester",
            task=task,
        )
        analysis = self._revise_document(
            analysis_draft,
            analysis_review,
            role="You are a professional product owner.",
            subject="requirement analysis",
            task=task,
        )

        design_draft = self._activity(
            role="You are a professional software architect.",
            instruction="Create a high-level implementation design without writing code.",
            context=f"# Requirement analysis\n{analysis}",
            question=task,
        )
        design_review = self._review(
            design_draft,
            subject="design",
            reviewers="a developer and a tester",
            task=task,
        )
        design = self._revise_document(
            design_draft,
            design_review,
            role="You are a professional software architect.",
            subject="design",
            task=task,
        )

        tests_draft = self._design_tests(task, f"# Requirement analysis\n{analysis}")
        tests_review = self._review(
            tests_draft,
            subject="test cases",
            reviewers="an architect and a developer",
            task=task,
        )
        tests = self._revise_document(
            tests_draft,
            tests_review,
            role="You are a quality assurance engineer.",
            subject="test cases",
            task=task,
        )

        code = self._extract_code(
            self._write_code(
                task,
                f"# Design\n{design}\n\n# Test cases\n{tests}",
            )
        )
        review = self._review(
            code,
            subject="code",
            reviewers="an architect and a tester",
            task=f"{task}\n\n# Test cases\n{tests}",
        )
        code = self._revise_code(task, code, review)
        self_test = self._review(
            code,
            subject="code",
            reviewers="a developer checking every proposed test case",
            task=f"{task}\n\n# Test cases\n{tests}",
        )
        return self._revise_code(task, code, self_test)

    def _run_scrum(self, task: str) -> str:
        discussion = []
        for role in ("product owner", "architect", "developer", "tester"):
            discussion.append(
                f"[{role}] "
                + self._activity(
                    role=f"You are the {role} in a Scrum team.",
                    instruction=(
                        "Contribute one concise planning proposal from your professional "
                        "perspective."
                    ),
                    context="\n".join(discussion),
                    question=task,
                )
            )

        sprint_plan = self._activity(
            role="You are a professional Scrum master.",
            instruction=(
                "Synthesize the team discussion into concrete product, architecture, "
                "development, and testing tasks."
            ),
            context="\n\n".join(discussion),
            question=f"Plan one sprint for:\n{task}",
        )
        design = self._activity(
            role="You are the software architect in the Scrum team.",
            instruction="Produce a concise implementation design for this sprint.",
            context=f"# Sprint plan\n{sprint_plan}",
            question=task,
        )
        design_review = self._review(
            design,
            subject="sprint design",
            reviewers="a developer and a tester",
            task=task,
        )
        design = self._revise_document(
            design,
            design_review,
            role="You are the software architect in the Scrum team.",
            subject="sprint design",
            task=task,
        )
        code = self._extract_code(
            self._write_code(task, f"# Sprint plan\n{sprint_plan}\n\n# Design\n{design}")
        )
        review = self._review(
            code,
            subject="code",
            reviewers="the Scrum architect and tester",
            task=task,
        )
        code = self._revise_code(task, code, review)
        tests = self._design_tests(task, f"# Sprint plan\n{sprint_plan}\n\n# Code\n{code}")
        sprint_review = self._review(
            code,
            subject="code",
            reviewers="the product owner, architect, developer, and tester",
            task=f"{task}\n\n# Proposed tests\n{tests}",
        )
        return self._revise_code(task, code, sprint_review)

    @staticmethod
    def _extract_code(response: Any) -> str:
        if not isinstance(response, str):
            return ""
        response = response.strip()
        if not response:
            return ""

        if "<think>" in response and "</think>" in response:
            response = response.split("</think>", 1)[1].strip()

        try:
            payload = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            payload = None
        if isinstance(payload, dict):
            for key in ("revised_code", "code", "FinalCode", "final_code"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    response = value.strip()
                    break

        blocks = re.findall(
            r"```(?:python|python3|py)?\s*\n?(.*?)```",
            response,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if blocks:
            response = blocks[-1].strip()

        lines = response.splitlines()
        if lines and lines[0].strip().lower() in {"python", "python3", "py"}:
            response = "\n".join(lines[1:]).strip()
        return response


FlowGen = FlowGen_Main
