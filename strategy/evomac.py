from strategy.methods import get_method_class
from utils.config_log import config, tracer
import os

model_config = config.get("model", {})

model_name = model_config['model']
model_temperature = model_config['temperature']
model_max_tokens = 4096
model_timeout = 60


model_url = os.environ['OPENAI_BASE_URL']
api_key = os.environ['OPENAI_API_KEY']

general_config = {
    "model_name": model_name,
    "model_temperature": model_temperature,
    "model_max_tokens": model_max_tokens,
    "model_timeout": model_timeout,
    "model_api_config": {
        model_name: {
                "model_list": [{"model_name": model_name, "model_url": model_url, "api_key": api_key}],
            "max_workers_per_model": 10
        }
    }
}



@tracer
def evomac(question: dict):
    method = get_method_class("evomac")(general_config)
    
    
    # Preserve repository metadata for EvoCodeBench.  EvoMAC's validation
    # stage needs more than the textual query in order to run the candidate in
    # the subject project's local environment.
    sample = dict(question)
    sample['query'] = question['prompt']
    response = method.inference(sample)
    usage = method.get_token_stats()
    usage = usage[model_name]
    usage = {
        "api_calls": usage['num_llm_calls'],
        "prompt_tokens": usage['prompt_tokens'],
        "completion_tokens": usage['completion_tokens'],
    }
    
    
    
    return response['response'], usage
    
