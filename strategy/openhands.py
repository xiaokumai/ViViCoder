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
model_timeout = 60

# An OpenHands task is an agent loop, not one completion request.  Serialize it
# by default so the outer benchmark worker count cannot overwhelm the model
# proxy with multiple independent agent loops.
openhands_max_concurrency = int(config.get("agent_limits", {}).get("openhands", 1))
if openhands_max_concurrency < 1:
    raise ValueError("agent_limits.openhands must be at least 1")
_openhands_semaphore = BoundedSemaphore(openhands_max_concurrency)

model_url = os.environ["OPENAI_BASE_URL"]
api_key = os.environ["OPENAI_API_KEY"]

general_config = {
    "model_name": model_name,
    "model_temperature": model_temperature,
    "model_max_tokens": model_max_tokens,
    "model_timeout": model_timeout,
    "model_api_config": {
        model_name: {
            "model_list": [{"model_name": model_name, "model_url": model_url, "api_key": api_key}],
            "max_workers_per_model": 1,
        }
    },
}


@tracer
def openhands(question: dict):
    sample = dict(question)
    sample["query"] = question["prompt"]

    try:
        with _openhands_semaphore:
            method = get_method_class("openhands")(general_config)
            response = method.inference(sample)
        if response.get("error"):
            raise RuntimeError(response["error"])
        if not response.get("response", "").strip():
            raise RuntimeError("OpenHands finished without writing a submission file.")
        if response.get("token_budget_exceeded"):
            logger.warning(
                "OpenHands token budget reached for {}; returning the saved solution.",
                question.get("question_id"),
            )
        usage = response.get("usage", {})
        code = response["response"]
        if question.get("evocodebench"):
            code = extract_function_body(code, question["question_id"])
        return code, {
            "api_calls": usage.get("api_calls", 0),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        }
    except Exception:
        logger.exception("OpenHands agent failed for {}", question.get("question_id", "<unknown>"))
        return '',{
            "api_calls":0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
