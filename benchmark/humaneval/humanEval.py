from datasets import load_dataset
import json

def load_humaneval_dataset(num_tasks) -> list[dict]:
    # Use the OpenAI HumanEval dataset.
    dataset = load_dataset("openai/openai_humaneval")["test"]
    problems = [{
        "task_id": row["task_id"],
        "prompt": row["prompt"],
        "test": row["test"],
        "canonical_solution": row["canonical_solution"],
        "entry_point": row["entry_point"]
    } for row in dataset.select(range(num_tasks))]
       
    return problems


def process_humaneval(dataset: list[dict]) -> list[dict]:
    converted_data = []
    for item in dataset:
        converted_data.append({
            "id": item["task_id"],
            "content": item["prompt"],
            "canonical_solution": item["canonical_solution"],
            "labels": {
                "programming_language": "python",
                "execution_language": "python"
            },
            "test": {
                "code": f"#<INSERT>\n{item['test']}\ncheck({item['entry_point']})"
            }
        })
    return converted_data

def process_humaneval_et(dataset: list[dict]) -> list[dict]:
    converted_data = []
    for item in dataset:
        extra_tests = "\n".join(item['test_case_list'])
        
        converted_data.append({
            "id": item["task_id"],
            "content": item["prompt"],
            "canonical_solution": item["canonical_solution"],
            "labels": {
                "programming_language": "python",
                "execution_language": "python"
            },
            "test": {
                "code": f"#<INSERT>\n{item['test']}\ncheck({item['entry_point']})\n\n# Extra test cases\n{extra_tests}"
            }
        })
    return converted_data



def load_jsonl_to_dict(file_path):
    result = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue  # Skip blank lines.
            data = json.loads(line)
            task_id = data.get("task_id")
            sample_io = data.get("sample_io")
            if task_id is not None:
                result[task_id] = sample_io
    return result

map_humaneval_sample_io = load_jsonl_to_dict('benchmark/humaneval/HumanEval.jsonl')
