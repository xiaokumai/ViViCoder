import re

from typing import Dict, List, Optional

from ..mas_base import MAS
from .prompt_main import Phase_configs, Role_configs, background_prompt


class ChatDev_Main(MAS):
    def __init__(self, general_config, method_config_name=None):
        method_config_name = "config_main" if method_config_name is None else method_config_name
        super().__init__(general_config, method_config_name)

        self.default_language = self.method_config["default_language"]
        self.enable_demand_analysis = self.method_config["enable_demand_analysis"]
        self.enable_language_choose = self.method_config["enable_language_choose"]
        self.review_cycles = self.method_config["review_cycles"]

        self.role_configs = Role_configs
        self.phase_configs = Phase_configs
        self.background_prompt = background_prompt
        self.history = []

    def inference(self, sample):
        query = sample["query"]
        local_task_type = self._classify_task(query)
        output_mode = self._default_output_mode(local_task_type)
        normalized_requirement = self._normalize_query(query, local_task_type)

        if self.enable_demand_analysis:
            analysis = self.demand_analysis(query, local_task_type)
            task_type = analysis["task_type"]
            output_mode = analysis["output_mode"]
            normalized_requirement = analysis["normalized_requirement"]
            constraints = analysis["constraints"]
        else:
            task_type = local_task_type
            constraints = []

        language = self.default_language
        if self.enable_language_choose:
            language = self.language_choose(query, normalized_requirement)

        code = self.coding(query, task_type, output_mode, normalized_requirement, language)
        final_code = self.code_review(query, task_type, normalized_requirement, language, code)

        return {
            "response": final_code,
            "task_type": task_type,
            "language": language,
            "normalized_requirement": normalized_requirement,
            "constraints": constraints,
        }

    def demand_analysis(self, query: str, task_type: str) -> Dict[str, object]:
        system_message = self._format_role_message("Chief Product Officer", query)
        phase_prompt = "\n".join(self.phase_configs["DemandAnalysis"]["phase_prompt"]).format(
            task=query,
            task_type=task_type,
        )
        messages = self.construct_messages(system_message, [], phase_prompt)
        response = self.call_llm(messages=messages)
        self.history.append({"role": "Chief Product Officer", "content": response})
        return self._parse_analysis_response(response, query, task_type)

    def language_choose(self, query: str, normalized_requirement: str) -> str:
        system_message = self._format_role_message("Chief Technology Officer", query)
        phase_prompt = "\n".join(self.phase_configs["LanguageChoose"]["phase_prompt"]).format(
            task=query,
            normalized_requirement=normalized_requirement,
            suggested_language=self.default_language,
        )
        messages = self.construct_messages(system_message, [], phase_prompt)
        response = self.call_llm(messages=messages)
        self.history.append({"role": "Chief Technology Officer", "content": response})
        match = re.search(r"<INFO>\s*(.+)", response)
        if not match:
            return self.default_language
        language = self._clean_language(match.group(1))
        return language or self.default_language

    def coding(
        self,
        query: str,
        task_type: str,
        output_mode: str,
        normalized_requirement: str,
        language: str,
    ) -> str:
        system_message = self._format_role_message("Programmer", query)
        phase_prompt = "\n".join(self.phase_configs["Coding"]["phase_prompt"]).format(
            task_type=task_type,
            output_mode=output_mode,
            language=language,
            normalized_requirement=normalized_requirement,
            task=query,
            task_specific_guidance=self._task_specific_guidance(task_type),
        )
        messages = self.construct_messages(system_message, [], phase_prompt)
        response = self.call_llm(messages=messages)
        self.history.append({"role": "Programmer", "content": response})
        return self._extract_final_code(response, task_type, query, language)

    def code_review(
        self,
        query: str,
        task_type: str,
        normalized_requirement: str,
        language: str,
        code: str,
    ) -> str:
        current_code = code
        language_tag = self._language_to_tag(language)

        for _ in range(self.review_cycles):
            reviewer_message = self._format_role_message("Code Reviewer", query)
            review_prompt = "\n".join(self.phase_configs["CodeReviewComment"]["phase_prompt"]).format(
                task_type=task_type,
                language=language,
                normalized_requirement=normalized_requirement,
                code=current_code,
                language_tag=language_tag,
            )
            review_messages = self.construct_messages(reviewer_message, [], review_prompt)
            review_response = self.call_llm(messages=review_messages)
            self.history.append({"role": "Code Reviewer", "content": review_response})

            if "<info> finished" in review_response.lower():
                break

            programmer_message = self._format_role_message("Programmer", query)
            revise_prompt = "\n".join(self.phase_configs["CodeReviewModification"]["phase_prompt"]).format(
                task_type=task_type,
                language=language,
                normalized_requirement=normalized_requirement,
                comments=review_response.strip(),
                code=current_code,
                language_tag=language_tag,
            )
            revise_messages = self.construct_messages(programmer_message, [], revise_prompt)
            revise_response = self.call_llm(messages=revise_messages)
            self.history.append({"role": "Programmer", "content": revise_response})
            revised_code = self._extract_final_code(revise_response, task_type, query, language)
            if revised_code:
                current_code = revised_code

        return current_code

    def construct_messages(self, prepend_prompt: str, history: List[Dict], append_prompt: str):
        messages = []
        if prepend_prompt is not None:
            messages.append({"role": "system", "content": prepend_prompt})
        if history:
            messages.extend(history)
        if append_prompt is not None:
            messages.append({"role": "user", "content": append_prompt})
        return messages

    def _format_role_message(self, role: str, task: str) -> str:
        return "\n".join(self.role_configs[role]).format(
            chatdev_prompt=self.background_prompt,
            task=task,
        )

    def _classify_task(self, query: str) -> str:
        lower_query = query.lower()
        if self._looks_like_competitive_programming(lower_query):
            return "COMPETITIVE_PROGRAMMING"
        if self._extract_function_name(query) is not None:
            return "FUNCTION_COMPLETION"
        return "GENERAL_CODEGEN"

    def _looks_like_competitive_programming(self, lower_query: str) -> bool:
        strong_signals = [
            "standard input",
            "standard output",
            "stdin",
            "stdout",
            "multiple test cases",
            "time limit",
            "memory limit",
        ]
        weak_signals = [
            "input:",
            "output:",
            "constraints",
        ]
        if any(signal in lower_query for signal in strong_signals):
            return True
        return sum(signal in lower_query for signal in weak_signals) >= 2

    def _default_output_mode(self, task_type: str) -> str:
        if task_type == "COMPETITIVE_PROGRAMMING":
            return "PROGRAM_CODE"
        return "FUNCTION_CODE" if task_type == "FUNCTION_COMPLETION" else "PROGRAM_CODE"

    def _normalize_query(self, query: str, task_type: str) -> str:
        if task_type == "FUNCTION_COMPLETION":
            return (
                "Implement the requested function exactly as specified. "
                "Preserve the function signature and semantics from the prompt. "
                "Do not add example usage, tests, or unrelated printing.\n\n"
                f"Original task:\n{query}"
            )
        if task_type == "COMPETITIVE_PROGRAMMING":
            return (
                "Solve the programming problem with a complete submission-ready program. "
                "Read from standard input, write to standard output, and cover edge cases.\n\n"
                f"Original task:\n{query}"
            )
        return (
            "Write a minimal, self-contained implementation that satisfies the user's coding request. "
            "Prefer a single file unless the task explicitly requires otherwise.\n\n"
            f"Original task:\n{query}"
        )

    def _task_specific_guidance(self, task_type: str) -> str:
        if task_type == "FUNCTION_COMPLETION":
            return (
                "Preserve the required function signature. "
                "Return only implementation code with any necessary imports and helper functions."
            )
        if task_type == "COMPETITIVE_PROGRAMMING":
            return (
                "Return a full program that can be submitted directly. "
                "Use standard input/output and avoid extra explanations or prompts."
            )
        return (
            "Return a complete single-file implementation with necessary imports only. "
            "Avoid explanations outside the code block."
        )

    def _parse_analysis_response(self, response: str, query: str, fallback_task_type: str) -> Dict[str, object]:
        task_type = self._extract_labeled_value(response, "TASK_TYPE") or fallback_task_type
        task_type = task_type.upper()
        if task_type not in {"FUNCTION_COMPLETION", "COMPETITIVE_PROGRAMMING", "GENERAL_CODEGEN"}:
            task_type = fallback_task_type

        output_mode = self._extract_labeled_value(response, "OUTPUT_MODE") or self._default_output_mode(task_type)
        output_mode = output_mode.upper()
        if output_mode not in {"FUNCTION_CODE", "PROGRAM_CODE"}:
            output_mode = self._default_output_mode(task_type)

        normalized_requirement = self._extract_block(response, "NORMALIZED_REQUIREMENT", "CONSTRAINTS")
        if not normalized_requirement:
            normalized_requirement = self._normalize_query(query, task_type)

        constraints_block = self._extract_block(response, "CONSTRAINTS")
        constraints = []
        if constraints_block:
            for line in constraints_block.splitlines():
                line = line.strip()
                if not line:
                    continue
                constraints.append(line.lstrip("- ").strip())

        return {
            "task_type": task_type,
            "output_mode": output_mode,
            "normalized_requirement": normalized_requirement.strip(),
            "constraints": constraints,
        }

    def _extract_labeled_value(self, text: str, label: str) -> Optional[str]:
        match = re.search(rf"^{label}:\s*(.+)$", text, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def _extract_block(self, text: str, start_label: str, end_label: Optional[str] = None) -> str:
        if end_label is None:
            pattern = rf"{start_label}:\s*(.*)"
        else:
            pattern = rf"{start_label}:\s*(.*?)(?:\n{end_label}:|\Z)"
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            return ""
        return match.group(1).strip()

    def _extract_function_name(self, query: str) -> Optional[str]:
        match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", query)
        if match:
            return match.group(1)
        return None

    def _extract_final_code(self, response: str, task_type: str, query: str, language: str) -> str:
        blocks = []
        for match in re.finditer(r"```([\w.+-]*)\n(.*?)```", response, re.DOTALL):
            blocks.append({"tag": match.group(1).strip().lower(), "code": match.group(2).strip()})

        if not blocks:
            return response.strip()

        target_function = self._extract_function_name(query)
        language_tag = self._language_to_tag(language)

        def score_block(block: Dict[str, str]) -> int:
            code = block["code"]
            score = 0
            if block["tag"] == language_tag:
                score += 3
            if task_type == "FUNCTION_COMPLETION" and target_function and f"def {target_function}(" in code:
                score += 5
            if task_type == "COMPETITIVE_PROGRAMMING":
                if "__name__ == \"__main__\"" in code or "__name__ == '__main__'" in code:
                    score += 4
                if "input(" in code:
                    score += 2
            score += min(len(code) // 200, 3)
            return score

        best_block = max(blocks, key=score_block)
        return best_block["code"]

    def _language_to_tag(self, language: str) -> str:
        return language.strip().lower().replace(" ", "")

    def _clean_language(self, language: str) -> str:
        return language.strip().strip("`").strip().rstrip(".:,;")
