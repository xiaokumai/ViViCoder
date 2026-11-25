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

# `run.py` evaluates tasks in a ThreadPoolExecutor.  Unlike regular strategies,
# each Codex invocation starts a separate agent process which may issue several
# model requests (and retry them internally).  Limit those agent processes here
# rather than relying on MAS.max_workers_per_model, which Codex_Main does not
# use.
codex_max_concurrency = int(config.get("agent_limits", {}).get("codex", 1))
if codex_max_concurrency < 1:
    raise ValueError("agent_limits.codex must be at least 1")
_codex_semaphore = BoundedSemaphore(codex_max_concurrency)

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
def codex(question: dict):
    sample = dict(question)
    sample["query"] = question["prompt"]

    try:
        # Keep the semaphore around the entire subprocess lifetime.  Otherwise
        # five benchmark tasks become five independent Codex agents and quickly
        # exhaust a proxy's request/concurrency quota.
        with _codex_semaphore:
            method = get_method_class("codex")(general_config)
            response = method.inference(sample)
        if response.get("error"):
            raise RuntimeError(response["error"])
        if not response.get("response", "").strip():
            raise RuntimeError("Codex finished without writing a submission file.")
        if response.get("token_budget_exceeded"):
            logger.warning(
                "Codex token budget reached for {}; returning the saved solution.",
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
        # Empty code is indistinguishable from a wrong solution in HumanEval.
        # Preserve the actual agent/API failure in the benchmark log instead of
        # silently turning it into an empty completion.
        logger.exception("Codex agent failed for {}", question.get("question_id", "<unknown>"))
        return '',{
            "api_calls":0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
        
