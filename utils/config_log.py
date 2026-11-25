import yaml


def load_config(path="config.yaml"):
    
    with open(path, "r") as f:
        return yaml.safe_load(f)
config = load_config()

env = config.get("env", ".env")


from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
from tabulate import tabulate
from utils.evocodebench import extract_function_body


current_path = Path.cwd()
env_path = current_path.joinpath(env)
load_dotenv(dotenv_path=env_path, verbose=True , override=True)

from datetime import datetime
import json

def no_tracer(func):
    return func

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

dataset_name = config.get("dataset", {}).get("name", "HumanEval")
model_name = config.get("model", {}).get("model", "gpt-3.5-turbo")
strategy = config.get("strategy", "vanilla")

tracer = no_tracer
whether_trace = config.get("whether_trace", False)

if whether_trace:
    from phoenix.otel import register
    

    tracer_provider = register(
    project_name=model_name + '-' + dataset_name + '-' + strategy + '-' + timestamp, # Default is 'default'
    auto_instrument=True, # See 'T    race all calls made to a library' below
    )
    tracer = tracer_provider.get_tracer("humanEval").chain
    


def get_run_output_dir(base="log"):
    
    run_dir = Path(base) / dataset_name / (strategy + "_" + timestamp)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

def save_results(result, jsonl_path="results.jsonl"):
    # Write JSONL.
    with open(jsonl_path, mode="a", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
        f.write("\n")
        
def save_repro_result(result, jsonl_path="reproduce_results.jsonl"):
    with open(jsonl_path, mode="w", encoding="utf-8") as f:
        for item in result:
            json.dump(item, f, ensure_ascii=False)
            f.write("\n")
            
            

            

def save_completion(result: list[dict], json_path="results.json"):
    dataset_name = config.get("dataset", {}).get("name", "HumanEval")
    dataset_name = dataset_name.lower().strip()
    filtered_data = []
    if dataset_name == 'livecodebench':
        for item in result:
            filtered_item = {
                'question_id': item['question_id'],
                'output_list': item['output_list'],
                'code_list': item['code_list']
            }
            filtered_data.append(filtered_item)
            
    if dataset_name == 'evocodebench':
        for item in result:
            namespace = item['question_id']
            completions = item.get('code_list') or item.get('output_list', [])
            for completion in completions:
                filtered_data.append({
                    'namespace': namespace,
                    'completion': extract_function_body(completion, namespace),
                })
            
        jsonl_path = json_path.with_suffix('.jsonl')
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for item in filtered_data:
                json_line = json.dumps(item, ensure_ascii=False)
                f.write(json_line + "\n")
        return
            
    if dataset_name == 'bigcodebench':
        for item in result:
            filtered_item = {
                'task_id': item['question_id'],
                'raw_solution': item['output_list'],
            }
            filtered_data.append(filtered_item)
            
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=2)


def log_result(k_values, pass_at_k):
    """
    Generate a horizontal Markdown table with tabulate.
    """
    if len(k_values) != len(pass_at_k):
        logger.error("k_values and pass_at_k must have the same length!")
        return

    headers = [str(k) for k in k_values]
    table = [pass_at_k]

    md_table = tabulate(
        table,
        headers=headers,
        tablefmt="github",  # Markdown format
        floatfmt=".6f",
        showindex=["pass@k"]
    )

    logger.info("\n" + md_table)
    return md_table  # The caller may save or write the table as needed.
