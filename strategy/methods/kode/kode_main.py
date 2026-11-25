import json
import random

import openai

from ..mas_base import MAS
from .runtime import KodeConfig, run_code_agent


class Kode_Main(MAS):
    def __init__(self, general_config, method_config_name=None):
        method_config_name = "config_main" if method_config_name is None else method_config_name
        super().__init__(general_config, method_config_name)
        self.kode_config = KodeConfig(**self.method_config)

    def inference(self, sample):
        query = sample["query"]
        response = run_code_agent(
            user_prompt=query,
            model_call=self._call_agent_model,
            config=self.kode_config,
        )
        return {"response": response}

    def _call_agent_model(self, system_prompt, messages, tools):
        model_dict = random.choice(self.model_api_config[self.model_name]["model_list"])
        actual_model_name = model_dict["model_name"]
        request_dict = {
            "model": actual_model_name,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": self.model_max_tokens,
            "timeout": self.model_timeout,
            "top_p": 0.95,
        }
        if system_prompt:
            request_dict["messages"] = [{"role": "system", "content": system_prompt}] + messages
        if "o1" not in actual_model_name:
            request_dict["temperature"] = self.model_temperature

        llm = openai.OpenAI(
            base_url=model_dict["model_url"],
            api_key=model_dict["api_key"],
        )
        try:
            completion = llm.chat.completions.create(**request_dict)
        finally:
            llm.close()

        self._update_token_stats(actual_model_name, completion.usage)
        message = completion.choices[0].message
        content = message.content or ""
        assistant_message = {"role": "assistant", "content": content}

        tool_calls = []
        if getattr(message, "tool_calls", None):
            serialized_calls = []
            for tool_call in message.tool_calls:
                arguments = tool_call.function.arguments or "{}"
                argument_error = None
                try:
                    parsed_arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    parsed_arguments = {}
                    argument_error = f"Invalid JSON tool arguments: {exc.msg}"
                serialized_calls.append(
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": arguments,
                        },
                    }
                )
                tool_calls.append(
                    {
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": parsed_arguments,
                    }
                )
                if argument_error:
                    tool_calls[-1]["_argument_error"] = argument_error
                    tool_calls[-1]["_raw_arguments"] = arguments
            if not content:
                assistant_message["content"] = None
            assistant_message["tool_calls"] = serialized_calls

        return {
            "text": content,
            "tool_calls": tool_calls,
            "assistant_message": assistant_message,
        }

    def _update_token_stats(self, model_name, usage):
        if model_name not in self.token_stats:
            self.token_stats[model_name] = {
                "num_llm_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }

        self.token_stats[model_name]["num_llm_calls"] += 1
        self.token_stats[model_name]["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
        self.token_stats[model_name]["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
