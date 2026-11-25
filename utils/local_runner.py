from utils.config_log import config
import subprocess
import tempfile
import os
from langchain_sandbox import PyodideSandbox, SyncPyodideSandbox 
import requests
from benchmark.load_benchmark import BENCHMARKS
from typing import List
import re
from utils.evocodebench import evaluate as evaluate_evocodebench
from utils.language import (
    get_language,
    sample_stdin,
    sample_stdout,
    uses_standard_input,
)

sandbox = SyncPyodideSandbox(
    allow_net=True,
)


def run_in_local(full_code: str):
    """
    Execute user code safely in an isolated Python subprocess.
    full_code: Contains prompt + completion + test.
    """
    success, output = False, ""
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = os.path.join(tmpdir, 'user_code.py')
            with open(script_path, 'w') as f:
                f.write(full_code)
            
            result = subprocess.run(
                ['python3', script_path],
                capture_output=True,
                text=True,
                cwd=tmpdir,  # Change the working directory.
                timeout=5
            )
            
            success = result.returncode == 0
            output = result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        output = "Error: Code execution exceeded timeout."
    except Exception as e:
        output = f"Error: {str(e)}"
    
    return success, output

 
def run_in_sandbox(full_code: str):
    """
    Execute user code with PyodideSandbox.
    full_code: Contains prompt + completion + test.
    """
    result = sandbox.execute(full_code)
    success = result.status == "success"
    return success, (result.stdout or '') + (result.stderr or '')

    
    


def run_check_with_completion(completion: str, data_config: dict, name: str):
    """
    Check whether a code completion is correct.
    """
    name = name.lower().strip()
    if name not in BENCHMARKS:
        raise ValueError(f"Unknown benchmark name: {name}")
    dataset = BENCHMARKS[name]["dataset"]
    
    res = requests.post('http://localhost:8081/submit', json={
        'dataset': dataset,
        'id': '',
        'completion': completion,
        'config': data_config
    }).json()
    
    return res


def evaluate_assertion_io(question: dict, completion: str):
    """
    Evaluate input and output for a single sample.
    """
    
    sample_io = question.get('sample_io', [])
    dataset_name = config.get("dataset", {}).get("name", "humaneval")
    
    test_log = ""
    passed = True
    for io in sample_io:
        code = ("from typing import *\n" if "from typing import *" not in completion else "") + \
            completion + "\n" + \
            ("solution = Solution()\n" if (dataset_name == 'livecodebench' and question.get('platform') != 'atcoder') else "") + \
            io + "\n"
            
        data = {
            "code": code,
            "language": "python",
            "compile_timeout": 20,
            "run_timeout": 20,
        }
        
        res = requests.post("http://localhost:8081/run_code", json=data).json()
        
        if res['status'] == 'Success':
            test_log += f"Passed in test case: {io}\n"
            
        else:
            passed = False
            test_log += f"Failed in test case: {io}" + ("TimeLimitExceeded\n" if res['run_result']['status'] == 'TimeLimitExceeded' else '\n')
            
    return passed, test_log


def evaluate_stdin_io(question: dict, completion: str):
    """
    Evaluate a single sample using standard input and output.
    """
    sample_io = question.get('sample_io', [])
    language = get_language(question)
    code = completion
    if language == "python" and "from typing import *" not in code:
        code = "from typing import *\n" + code

    results = []
    errors = []
    for sample in sample_io:
        data = {
            "code": code,
            "stdin": sample_stdin(sample),
            "language": language,
            "run_timeout": 50 if language != "python" else 20,
            "compile_timeout": 50 if language != "python" else 20,
        }
        result = requests.post("http://localhost:8081/run_code", json=data).json()
        results.append(result)
        compile_result = result.get("compile_result") or {}
        run_result = result.get("run_result") or {}
        if compile_result.get("stderr"):
            errors.append(str(compile_result["stderr"]))
        if not run_result:
            errors.append(f"Execution did not start (status: {result.get('status', 'unknown')})")
        elif run_result.get("status") == "TimeLimitExceeded":
            errors.append("TimeLimitExceeded")
        elif run_result.get("stderr"):
            errors.append(str(run_result["stderr"]))

    if errors:
        return False, f"## Tests failed:\nSyntax Error or Execution Error:{list(dict.fromkeys(errors))}"

    passed = True
    passed_feedback = []
    failed_feedback = []
    for sample, result in zip(sample_io, results):
        output = str((result.get("run_result") or {}).get("stdout", "")).strip()
        expected = sample_stdout(sample).strip()
        display_output = output[:500] + "..." if len(output) > 500 else output
        test_case = (
            f"Input:\n{sample_stdin(sample)}\nExpected Output:\n{expected}\n"
            f"Your Output:\n{display_output}\n"
        )
        if output == expected:
            passed_feedback.append(test_case)
        else:
            passed = False
            failed_feedback.append(test_case)

    passed_text = '\n'.join(passed_feedback) if passed_feedback else "No test cases passed."
    failed_text = '\n'.join(failed_feedback)
    return passed, f'## Tested passed:\n{passed_text}\n\n## Tests failed:\n{failed_text}'
    

def evaluate_evo(question: dict, completion: str):
    evo_config = config.get("evocodebench", {})
    return evaluate_evocodebench(
        question,
        completion,
        timeout=int(evo_config.get("test_timeout", 120)),
        max_feedback_chars=int(evo_config.get("max_feedback_chars", 12000)),
    )



                    
def evaluate_sample_io(question: dict, completion: str):
    """
    Evaluate input and output for a single sample.
    """
    dataset_name = config.get("dataset", {}).get("name", "humaneval")
    
    if dataset_name=='evocodebench':
        return evaluate_evo(question,completion)
    
    
    sample_io = question.get('sample_io', [])
    
    if len(sample_io) == 0:
        return True, ""
    
    if uses_standard_input(question):
        return evaluate_stdin_io(question, completion)

    if get_language(question) != "python":
        raise ValueError("C++ and Java sample evaluation currently requires a standard-input benchmark")

    if dataset_name in ['humaneval', 'mbpp', 'humaneval-et', 'mbpp-et', 'mhpp']:
        return evaluate_assertion_io(question, completion)
    else:
        if question.get('platform') != 'atcoder':
            return evaluate_assertion_io(question, completion)
        else:
            return evaluate_stdin_io(question, completion)
    
    

                
def evaluate_additional_io(
    question: dict, 
    io: List[str],
    cur_imp: str,
):
    if len(io) == 0:
        return True, ""
    
    return evaluate_sample_io(
        question=question,
        completion=cur_imp,            
    )
    
    
def parse_response(response: str) -> str:

    if '<think>' in response and '</think>' in response:
        response = response.split('</think>')[1]
    
    if response is None:
        return ''
    
    if "```" not in response:
        return response

    code_pattern = r'```((.|\n)*?)```'
    if "```Python" in response:
        code_pattern = r'```Python((.|\n)*?)```'
    if "```json" in response:
        code_pattern = r'```json((.|\n)*?)```'
    
    if "```Python3" in response:
        code_pattern = r'```Python3((.|\n)*?)```'
    if "```python" in response:
        code_pattern = r'```python((.|\n)*?)```'
    if "```python3" in response:
        code_pattern = r'```python3((.|\n)*?)```'
    if "```C" in response:
        code_pattern = r'```C((.|\n)*?)```'
    if "```c" in response:
        code_pattern = r'```c((.|\n)*?)```'
    if "```C++" in response:
        code_pattern = r'```C\+\+((.|\n)*?)```'
    if "```c++" in response:
        code_pattern = r'```c\+\+((.|\n)*?)```'
    if "```cpp" in response:
        code_pattern = r'```cpp((.|\n)*?)```'
    if "```Cpp" in response:
        code_pattern = r'```Cpp((.|\n)*?)```'
    if "```Java" in response:
        code_pattern = r'```Java((.|\n)*?)```'
    if "```java" in response:
        code_pattern = r'```java((.|\n)*?)```'
    if "```Node" in response:
        code_pattern = r'```Node((.|\n)*?)```'
    if "```node" in response:
        code_pattern = r'```node((.|\n)*?)```'
    if "```Rust" in response:
        code_pattern = r'```Rust((.|\n)*?)```'
    if "```rust" in response:
        code_pattern = r'```rust((.|\n)*?)```'
    if "```PHP" in response:
        code_pattern = r'```PHP((.|\n)*?)```'
    if "```php" in response:
        code_pattern = r'```php((.|\n)*?)```'
    if "```Go" in response:
        code_pattern = r'```Go((.|\n)*?)```'
    if "```go" in response:
        code_pattern = r'```go((.|\n)*?)```'
    if "```Ruby" in response:
        code_pattern = r'```Ruby((.|\n)*?)```'
    if "```ruby" in response:
        code_pattern = r'```ruby((.|\n)*?)```'
    if "```C#" in response:
        code_pattern = r'```C#((.|\n)*?)```'
    if "```c#" in response:
        code_pattern = r'```c#((.|\n)*?)```'
    if "```csharp" in response:
        code_pattern = r'```csharp((.|\n)*?)```'

    code_blocks = re.findall(code_pattern, response, re.DOTALL)

    if type(code_blocks[-1]) == tuple or type(code_blocks[-1]) == list:
        code_str = "\n".join(code_blocks[-1])
    elif type(code_blocks[-1]) == str:
        code_str = code_blocks[-1]
    else:
        code_str = response

    return code_str.strip()


import torch
import nvidia_smi

def select_best_gpu(required_mem_gb: float = 4.0):
    required_mem = required_mem_gb * 1024 ** 3  # GB → bytes

    if not torch.cuda.is_available():
        # print("No CUDA available. Using CPU.")
        return "cpu"

    # Initialize NVML.
    nvidia_smi.nvmlInit()
    device_count = nvidia_smi.nvmlDeviceGetCount()

    best_gpu = None
    best_free_mem = 0

    for i in range(device_count):
        handle = nvidia_smi.nvmlDeviceGetHandleByIndex(i)
        mem_info = nvidia_smi.nvmlDeviceGetMemoryInfo(handle)

        free_mem = mem_info.free

        # print(f"GPU {i}: free {free_mem / 1024 ** 3:.2f} GB")

        if free_mem > required_mem and free_mem > best_free_mem:
            best_free_mem = free_mem
            best_gpu = i

    nvidia_smi.nvmlShutdown()

    if best_gpu is None:
        # print("No GPU meets requirements. Using CPU.")
        return "cpu"

    # print(f"Selected GPU: {best_gpu}")
    return f"cuda:{best_gpu}"
