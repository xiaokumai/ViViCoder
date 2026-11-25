from utils.config_log import config
from datasets import load_dataset
from benchmark.humaneval.humanEval import process_humaneval, process_humaneval_et, map_humaneval_sample_io
import requests
import json
import random
from pathlib import Path

from utils.evocodebench import DEFAULT_ROOT, enrich_dataset


def shuffle_evocodebench_dataset(dataset: list[dict], seed: int | None) -> list[dict]:
    """Return a reproducibly shuffled copy of an EvoCodeBench dataset."""
    shuffled = list(dataset)
    random.Random(seed).shuffle(shuffled)
    return shuffled


BENCHMARKS = {
    "humaneval": {
        "config": {
            "run_timeout": 50,
            "dataset_type": "AutoEvalDataset",
        },
        "dataset": "dataset_id",
        "load_params": {
            "args": ("openai/openai_humaneval",),
            "kwargs": {"split": "test"},
        },
    },
    "humaneval-et": {
        "config": {
            "run_timeout": 50,
            "dataset_type": "AutoEvalDataset",
        },
        "dataset": "dataset_id",
        "load_params": {
            "args": ("dz1/CodeScore-HumanEval-ET",),
            "kwargs": {"split": "train"},
        },
    },
    "mhpp": {
        "config": {
            "pretrain_mode": False,
            "run_timeout": 50,
            "dataset_type": "MHPPDataset",
        },
        "dataset": "mhpp",
        "load_params": {
            "args": ("laylarsssss/FusedMHPP", "mhpp_210"),
            "kwargs": {"split": "test"},
        },
    },
    "codecontests": {
        "config": {
            "language": "python",
            "locale": "en",
            "compile_timeout": 20,
            "run_timeout": 50,
            "dataset_type": "CommonOJDataset",
        },
        "dataset": "code_contests_test",
        "load_params": {
            "args": ("sine/FusedCodeContests",),
            "kwargs": {"split": "test"},
        },
    },
    "contests_python": {
        "config": {
            "language": "python",
            "locale": "en",
            "compile_timeout": 50,
            "run_timeout": 50,
            "dataset_type": "CommonOJDataset",
        },
        "dataset": "code_contests_test",
        "load_params": {
            "args": ("sine/FusedCodeContests",),
            "kwargs": {"split": "test"},
        },
    },
    "contests_cpp": {
        "config": {
            "language": "cpp",
            "locale": "en",
            "compile_timeout": 50,
            "run_timeout": 50,
            "dataset_type": "CommonOJDataset",
        },
        "dataset": "code_contests_test",
        "load_params": {
            "args": ("sine/FusedCodeContests",),
            "kwargs": {"split": "test"},
        },
    },
    "contests_java": {
        "config": {
            "language": "java",
            "locale": "en",
            "compile_timeout": 50,
            "run_timeout": 50,
            "dataset_type": "CommonOJDataset",
        },
        "dataset": "code_contests_test",
        "load_params": {
            "args": ("sine/FusedCodeContests",),
            "kwargs": {"split": "test"},
        },
    },
}


def load_benchmark(name: str, num_tasks: int = -1):
    """
    Load the requested benchmark and return the requested number of records.
    :param name: Benchmark name.
    :param num_tasks: Number of tasks; -1 selects all tasks.
    :return: (config, data)
    """
    name = name.lower().strip()
    if name == 'livecodebench':
        # Read the input JSON file.
        with open('benchmark/livecodebench/process_io.json', "r", encoding="utf-8") as f:
            dataset = json.load(f)
            
        if num_tasks != -1:
            dataset = dataset[:num_tasks]
        return dataset
    
    if name == 'evocodebench':
        evo_config = config.get("evocodebench", {})
        benchmark_root = Path(evo_config.get("root", DEFAULT_ROOT))
        processed_file = Path(
            evo_config.get("processed_file", "benchmark/evocodebench/processed.json")
        )
        feedback_metadata_file = Path(
            evo_config.get(
                "feedback_metadata_file",
                "benchmark/evocodebench/feedback_metadata.jsonl",
            )
        )
        source_code_root = Path(
            evo_config.get("source_code_root", benchmark_root / "Source_Code")
        )

        with processed_file.open("r", encoding="utf-8") as f:
            dataset = json.load(f)

        dataset = enrich_dataset(
            dataset,
            benchmark_root=benchmark_root,
            feedback_metadata_file=feedback_metadata_file,
            source_code_root=source_code_root,
        )
        for question in dataset:
            question["evocodebench"]["test_timeout"] = int(
                evo_config.get("test_timeout", 120)
            )
            question["evocodebench"]["max_feedback_chars"] = int(
                evo_config.get("max_feedback_chars", 12000)
            )
        if evo_config.get("shuffle", True):
            dataset = shuffle_evocodebench_dataset(
                dataset,
                evo_config.get("shuffle_seed", 42),
            )
        if num_tasks != -1:
            dataset = dataset[:num_tasks]
        return dataset
    
        
    
    
    if name not in BENCHMARKS:
        raise ValueError(f"Unknown benchmark name: {name}")

    
    
    info = BENCHMARKS[name]
    cfg = info["config"]
    params = info["load_params"]
    
    dataset = list(load_dataset(*params["args"], **params["kwargs"]))
    
    if num_tasks != -1:
        dataset = dataset[:num_tasks]
        
    if name == "humaneval":
        dataset = process_humaneval(dataset)
    elif name == "humaneval-et":
        dataset = process_humaneval_et(dataset)
        
    cfg['provided_data'] = dataset

    return cfg


def get_prompts(config: dict, name: str):
    name = name.lower().strip()
    if name not in BENCHMARKS:
        raise ValueError(f"Unknown benchmark name: {name}")
    
    dataset = BENCHMARKS[name]["dataset"]
    
    prompt = requests.post('http://localhost:8081/get_prompts', json={
  'dataset': dataset,
  'config': config
}).json()[0]
    
    if name == 'humaneval' or name == 'humaneval-et':
        prompt['sample_io'] = map_humaneval_sample_io[prompt['id']]

    elif name == 'mhpp':
        from benchmark.MHPP.mhpp import map_mhpp_sample_io

        prompt['sample_io'] = map_mhpp_sample_io[prompt['id']]
    elif name in {'codecontests', 'contests_python', 'contests_cpp', 'contests_java'}:
        from benchmark.codecontests import get_public_cases

        prompt['sample_io'] = get_public_cases(prompt['id'])

    prompt['language'] = config.get('language', 'python')
    
    
    return prompt
