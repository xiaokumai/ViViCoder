"""Entry point for the FlowGen baseline."""

from __future__ import annotations

import os
from threading import BoundedSemaphore

from loguru import logger

from strategy.methods import get_method_class
from utils.config_log import config, tracer
from utils.evocodebench import extract_function_body


model_config = config.get("model", {})
model_name = model_config["model"]
model_temperature = model_config["temperature"]
model_max_tokens = model_config.get("max_tokens", 4096)
model_timeout = model_config.get("timeout", 60)

model_url = os.environ["OPENAI_BASE_URL"]
api_key = os.environ["OPENAI_API_KEY"]

flowgen_max_concurrency = int(config.get("agent_limits", {}).get("flowgen", 1))
if flowgen_max_concurrency < 1:
    raise ValueError("agent_limits.flowgen must be at least 1")
_flowgen_semaphore = BoundedSemaphore(flowgen_max_concurrency)

general_config = {
    "model_name": model_name,
    "model_temperature": model_temperature,
    "model_max_tokens": model_max_tokens,
    "model_timeout": model_timeout,
    "model_api_config": {
        model_name: {
            "model_list": [
                {"model_name": model_name, "model_url": model_url, "api_key": api_key}
            ],
            "max_workers_per_model": flowgen_max_concurrency,
        }
    },
    "flowgen": config.get("flowgen", {}),
}


@tracer
def flowgen(question: dict):
    """Generate one completion with the configured FlowGen workflow."""

    sample = dict(question)
    sample["query"] = question["prompt"]
    sample["dataset"] = config.get("dataset", {}).get("name", "humaneval")

    try:
        with _flowgen_semaphore:
            method = get_method_class("flowgen")(general_config)
            response = method.inference(sample)

        code = response["response"]
        if sample["dataset"].lower().strip() == "evocodebench":
            code = extract_function_body(code, question.get("question_id", ""))

        usage = method.get_token_stats().get(model_name, {})
        return code, {
            "api_calls": usage.get("num_llm_calls", 0),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        }
    except Exception:
        logger.exception("FlowGen failed for {}", question.get("question_id", "<unknown>"))
        return "", {
            "api_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
