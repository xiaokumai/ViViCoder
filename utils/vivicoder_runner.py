from utils.config_log import config
from utils.evocodebench import evaluate as evaluate_evocodebench
import requests
from utils.language import (
    get_language,
    sample_stdin,
    sample_stdout,
    uses_standard_input,
)



def check_syntax_error(question, completion: str):
    """
    Check the code for syntax errors.
    """
    
    dataset_name = config.get("dataset", {}).get("name", "humaneval")
    sample_io = question.get('sample_io', [])
    
    code = ("from typing import *\n" if "from typing import *" not in completion else "") + \
        completion + "\n" + \
        ("solution = Solution()\n" if (dataset_name == 'livecodebench' and question.get('platform') != 'atcoder') else "")
        
    if len(sample_io) > 0:
        sample = sample_io[0]
        sample = sample[6:].strip()
        code = code + sample + "\n"
            
    data = {
        "code": code,
        "language": "python",
        "compile_timeout": 20,
        "run_timeout": 20,
    }
    
    res = requests.post("http://localhost:8081/run_code", json=data).json()
    error = []
    if res['run_result']['stderr']:
        error.append(res['run_result']['stderr'])
    if res['run_result']['status'] == 'TimeLimitExceeded':
        error.append("TimeLimitExceeded\n")
        
    if error:
        return False, f"## Tests failed:\nSyntax Error Message:{error}", []
    return True, "", []
        


def evaluate_assertion_io(question: dict, completion: str):
    """
    Evaluate input and output for a single sample.
    """
    
    passed, error, failed = check_syntax_error(question, completion)
    if not passed:
        return passed, error, failed
    
    sample_io = question.get('sample_io', [])
    dataset_name = config.get("dataset", {}).get("name", "humaneval")
    
    failed = []
    
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
            failed.append(io)
            passed = False
            test_log += f"Failed in test case: {io}"
            
            
    return passed, test_log, failed


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
        unique_errors = list(dict.fromkeys(errors))
        return False, f"## Tests failed:\nSyntax Error or Execution Error:{unique_errors}", []

    passed = True
    passed_feedback = []
    failed_feedback = []
    failed = []
    for sample, result in zip(sample_io, results):
        output = str((result.get("run_result") or {}).get("stdout", "")).strip()
        display_output = output[:500] + "..." if len(output) > 500 else output
        expected = sample_stdout(sample).strip()
        test_case = (
            f"Input:\n{sample_stdin(sample)}\nExpected Output:\n{expected}\n"
            f"Your Output:\n{display_output}\n"
        )
        if output == expected:
            passed_feedback.append(test_case)
        else:
            failed.append(sample)
            passed = False
            failed_feedback.append(test_case)

    passed_text = '\n'.join(passed_feedback) if passed_feedback else "No test cases passed."
    failed_text = '\n'.join(failed_feedback)
    feedback = f'## Tested passed:\n{passed_text}\n\n## Tests failed:\n{failed_text}'
    return passed, feedback, failed
    
   



def evaluate_evo(question: dict, completion: str):
    evo = question["evocodebench"]
    passed, feedback = evaluate_evocodebench(
        question,
        completion,
        timeout=int(evo.get("test_timeout", 120)),
        max_feedback_chars=int(evo.get("max_feedback_chars", 12000)),
    )
    return passed, feedback, []



def evaluate_sample_io(question: dict, completion: str):
    """
    Evaluate input and output for a single sample.
    """
    dataset_name = config.get("dataset", {}).get("name", "humaneval")

    if dataset_name=='evocodebench':
        return evaluate_evo(question,completion)

    sample_io = question.get('sample_io', [])
    
    if len(sample_io) == 0:
        return True, "", []
    
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
