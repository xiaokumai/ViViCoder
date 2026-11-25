import os

from strategy.methods import get_method_class
from utils.config_log import config, tracer


model_config = config.get("model", {})

model_name = model_config["model"]
model_temperature = model_config["temperature"]
model_max_tokens = 4096
model_timeout = 60

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
            "max_workers_per_model": 10,
        }
    },
}


@tracer
def ldb(question: dict):
    method = get_method_class("ldb")(general_config)
    if "debug" in config:
        method.max_iters = config["debug"]

    sample = dict(question)
    sample["query"] = question["prompt"]

    try:
        response = method.inference(sample)
        usage = method.get_token_stats().get(model_name, {})
        usage = {
            "api_calls": usage.get("num_llm_calls", 0),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        }
        return response["response"], usage
    except Exception:
        return "", {
            "api_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

