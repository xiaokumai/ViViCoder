from utils.config_log import config, get_run_output_dir, save_results, tracer, log_result
from benchmark.load_benchmark import load_benchmark, get_prompts
from loguru import logger
from utils.local_runner import run_check_with_completion, parse_response
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from pass_at_k import pass_at_k
from utils.compute_metrics import compute_overall_passk
from utils.tqdmsink import TqdmSink
from strategy.strategyFectory import get_strategy
import copy
import json
from opentelemetry.trace import format_span_id, get_current_span
from phoenix.client import Client
from utils.language import get_language, language_fence


MULTILINGUAL_STRATEGIES = {
    "vivicoder",
    "vanilla",
    "analogical",
    "codesim",
    "mapcoder",
}



@tracer
def generate_code(question, n=1):
    """
    Generate code using the specified model.
    """
    
    logger.info(f"✏️ Generating {n} samples for: {question['question_id']}")
    
    strategy_name = config.get("strategy", "vanilla")
    language = get_language(question)
    if language != "python" and strategy_name.lower() not in MULTILINGUAL_STRATEGIES:
        supported = ", ".join(sorted(MULTILINGUAL_STRATEGIES))
        raise ValueError(
            f"Strategy {strategy_name!r} is Python-only. For {language}, choose one of: {supported}"
        )
    strategy = get_strategy(strategy_name)
    completions = []
    api_calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    
    for _ in range(n):
        
        completion = strategy(question)
        if strategy_name == 'Analogical':
            completion = parse_response(completion)
            completion = f'```{language_fence(get_language(question))}\n{completion}\n```'
        elif strategy_name.lower() in {'paircoder', 'evomac', 'chatdev', 'kode', 'ldb', 'openhands', 'codex', 'flowgen'}:
            completion, token_used = completion
            completion = f'```{language_fence(get_language(question))}\n{completion}\n```'
            api_calls += token_used.get("api_calls")
            prompt_tokens += token_used.get("prompt_tokens")
            completion_tokens += token_used.get("completion_tokens")

        
        completions.append(completion)
    

    question["completions"] = completions
    question["api_calls"] = api_calls
    question["prompt_tokens"] = prompt_tokens
    question["completion_tokens"] = completion_tokens
    return {"completions": completions}


@tracer
def run_test(question: dict, data_config: dict):
    logger.info(f"🔍 Starting evaluation for task {question['question_id']}")
    completions = question["completions"]
    dataset_name = config.get("dataset", {}).get("name", "HumanEval")
    
    passes = 0
    results = []
    one_hot = []
    
    for f in completions:
        res = run_check_with_completion(f, data_config=data_config, name=dataset_name)
        results.append(res)
        if res.get("accepted", False):
            passes += 1
            one_hot.append(1)
        else:
            one_hot.append(0)
            
    question["passes"] = passes
    question["results"] = results
    return {
        "passes": passes,
        "one_hot": one_hot,
        "results": results,
    }


@tracer
def report_results(question):
    k_val = config.get("evaluation", {}).get("k", [1])
    n = question.get("num_samples", 10)
    c = question.get("passes", 0)
    pass_at_k_results = []
    for k in k_val:
        pass_at_k_results.append(pass_at_k(n, c, k))

    logger.info(f"question{question['question_id']} pass@{k_val} result: {pass_at_k_results}")

    question["pass_at_k"] = pass_at_k_results
    return {"pass_at_k": pass_at_k_results}


from langchain_community.callbacks.manager import get_openai_callback


@tracer
def answer_single_question(id: int, sample: dict, data_config: dict, jsonl_path: str):
    local_config = copy.deepcopy(data_config)
    dataset_name = config.get("dataset", {}).get("name", "HumanEval")
    num_samples = config.get("dataset", {}).get("num_samples", 10)

    local_config['provided_data'] = [sample]
    prompt = get_prompts(local_config, dataset_name)
    
    question = {
        "question_id": prompt['id'],
        "task_id": f"{dataset_name}_{id}",
        "prompt": prompt['prompt'],
        "num_samples": num_samples,
        "sample_io": prompt.get('sample_io', []),
        "dataset_name": dataset_name.lower(),
        "language": get_language(
            data_config=local_config,
            dataset_name=dataset_name,
        ),
        "platform": prompt.get('platform'),
        "benchmark_sample": sample,
    }
    strategy_name = config.get("strategy", "vanilla")
    

    with get_openai_callback() as cb:
        generate_code(question, num_samples)
        if strategy_name.lower() not in {'paircoder', 'evomac', 'chatdev', 'kode', 'ldb', 'openhands', 'codex', 'flowgen'}:
        
            question['api_calls'] = cb.successful_requests
            question['prompt_tokens'] = cb.prompt_tokens
            question['completion_tokens'] = cb.completion_tokens
            question['total_tokens'] = cb.total_tokens
        
    
    logger.info(f"✅ Completed code generation for task {question['question_id']}")
    local_config["provided_data"] = sample

    run_test(question, local_config)
    res = report_results(question)
    
    span = get_current_span()
    span_id = format_span_id(span.get_span_context().span_id)

    if res['pass_at_k'][0] < 1e-1:
        client = Client()
        annotation = client.annotations.add_span_annotation(
            annotation_name="user feedback",
            annotator_kind="HUMAN",
            span_id=span_id,
            # label="thumbs-up",
            score=res['pass_at_k'][0],
        )
    
    save_results(question, jsonl_path=jsonl_path)
    
    return question
    
    
    
def load_existing_results(generated_file, data, data_config):
    k_values = config.get("evaluation", {}).get("k", 1)
    dataset_name = config.get("dataset", {}).get("name", "HumanEval")
    
    passes = []
    results = []
    with open(generated_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue  # Skip blank lines.
            try:
                sample = json.loads(line)
                results.append(sample)
                passes.append(sample.get("pass_at_k", [0]*len(k_values)))
            except json.JSONDecodeError as e:
                logger.error(f"⚠️ Skipping an unparseable line: {e}")
                    
    logger.info(f"📂 Loaded {len(results)} generated code samples from {generated_file}.")
    
    processed_ids = {item["question_id"] for item in results}
    filtered_data = []
    
    for item in data:
        local_config = copy.deepcopy(data_config)
        local_config['provided_data'] = [item]
        prompt = get_prompts(local_config, dataset_name)
        if prompt['id'] not in processed_ids:
            filtered_data.append(item)
            
    return filtered_data, results, passes

    
@tracer
def main():
    
    # Create the output directory.
    output_dir = get_run_output_dir()
    log_path = output_dir / "run.log"
    results_path = output_dir / "results.jsonl"
    
    logger.remove()  # Remove the default console sink.
    logger.add(TqdmSink(), enqueue=True, format="{level}\t| {file} | {name}:{function}:{line} - \t{message}")
    logger.add(log_path, encoding="utf-8", enqueue=True, format="{level}\t| {file} | {name}:{function}:{line} - \t{message}" )
    logger.info(f"📋 Logging initialized; output will be written to {log_path}")
    
    logger.info("⚙️ Current experiment configuration:")
    for k, v in config.items():
        logger.info(f"  {k}: {v}")
        
    num_tasks = config.get("evaluation", {}).get("num_tasks", 5)
    num_workers = config.get("evaluation", {}).get("num_workers", 4)
    num_samples = config.get("dataset", {}).get("num_samples", 10)
    k_values = config.get("evaluation", {}).get("k", 1)
    dataset_name = config.get("dataset", {}).get("name", "HumanEval")
    generated_file = config.get("generated_file", "")

    data_config = load_benchmark(dataset_name, num_tasks=num_tasks)
    data = data_config.get('provided_data', [])
    

    
    passes = []
    results = []
    
    ori_data_len = len(data)
    
    if generated_file:
        results_path = generated_file
        data, results, passes = load_existing_results(generated_file, data, data_config)

    
    num_tasks = len(data)
    api_calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    
    
    logger.info(f"🧾 Starting evaluation of {num_tasks} tasks with {num_samples} generated code samples per task"
        f" and {num_workers} worker threads.")
    
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(answer_single_question, idx, sample, data_config, results_path)
            for idx, sample in enumerate(data, start=len(results))
        ]
        for f in tqdm(as_completed(futures), total=len(data), desc="Processing tasks"):
            res = f.result()
            
            results.append(res)
            passes.append(res.get("pass_at_k", [0]*len(k_values)))
            

    for res in results:
        api_calls += res.get("api_calls", 0)
        prompt_tokens += res.get("prompt_tokens", 0)
        completion_tokens += res.get("completion_tokens", 0)
        total_tokens += res.get("total_tokens", 0)
    
    logger.info(f"📄 Results saved to {results_path}")
    
    
    logger.info("🧾 Evaluation complete")
    overall_passk = compute_overall_passk(passes)
    
    avg_calls = (api_calls / ori_data_len) / num_samples
    avg_prompt_tokens = ((prompt_tokens / ori_data_len) / num_samples) / 1000
    avg_completion_tokens = ((completion_tokens / ori_data_len) / num_samples) / 1000
    avg_total_tokens = avg_prompt_tokens + avg_completion_tokens
    
    logger.info(f"📊 Average API calls per task: {avg_calls:.6f}")
    logger.info(f"📊 Average prompt tokens per task: {avg_prompt_tokens:.6f} k"
        f", completion tokens: {avg_completion_tokens:.6f} k, total tokens: {avg_total_tokens:.6f} k")
    
    logger.info(f"📋 Logging initialized; output will be written to {log_path}")
    
    logger.info("⚙️ Current experiment configuration:")
    for key, value in config.items():
        logger.info(f"  {key}: {value}")

    log_result(k_values, overall_passk)
    
    
    return {
        "num_tasks": num_tasks,
        "k": k_values,
        "pass_k": overall_passk
    }
        

if __name__ == "__main__":
    main()
