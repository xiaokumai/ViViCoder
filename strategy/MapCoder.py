from utils.config_log import config, tracer
from langchain_core.prompts import PromptTemplate
from prompts.MapCoder import INPUT_KB_EXAMPLARS, PROBLEM_PLANNNING, PLANNING_VERIFICATION, FINAL_CODE_GENERATION, IMPROVING_CODE
import xml.etree.ElementTree as ET
import re
from utils.local_runner import evaluate_sample_io, parse_response as parse_code_response
from utils.model_invoke import invoke_model
from loguru import logger
from utils.language import (
    get_language,
    language_display,
    language_fence,
    sample_stdin,
    sample_stdout,
    uses_standard_input,
)



mapping = {
    1: "one (01)",
    2: "two (02)",
    3: "three (03)",
    4: "four (04)",
    5: "five (05)",
    6: "six (06)",
    7: "seven (07)",
    8: "eight (08)",
    9: "nine (09)",
}

k = 5
t = 10

def trim_text(text: str, trimmed_text: str):
    return text.replace(trimmed_text, '').strip()

def replace_tag(text: str, tag: str):
    if f'<{tag}><![CDATA[' in text and f']]></{tag}>' in text:
        return text 
    else:
        return text.replace(f'<{tag}>', f'<{tag}><![CDATA[').replace(f'</{tag}>', f']]></{tag}>').strip()


def xml_to_dict(element):
    result = {}
    for child in element:
        if child:
            child_data = xml_to_dict(child)
            if child.tag in result:
                if isinstance(result[child.tag], list):
                    result[child.tag].append(child_data)
                else:
                    result[child.tag] = [result[child.tag], child_data]
            else:
                result[child.tag] = child_data
        else:
            result[child.tag] = child.text
    return result

def parse_xml(response: str) -> dict:
    if '```xml' in response:
        response = response.replace('```xml', '')
    if '```' in response:
        response = response.replace('```', '')

    try:
        root = ET.fromstring(response)
    except:
        try:
            root = ET.fromstring('<root>\n' + response + '\n</root>')
        except:
            root = ET.fromstring('<root>\n' + response)
    return xml_to_dict(root)

def parse_code(response: str) -> str:
    return parse_code_response(response)

    # Kept below for compatibility reference; parse_code_response handles all
    # supported fence spellings, including the `cpp` tag.
    if "```" not in response:
        return response

    code_pattern = r'```((.|\n)*?)```'
    if "```Python" in response:
        code_pattern = r'```Python((.|\n)*?)```'
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

    return code_str



def get_sample_io_str(sample_io: any) -> str:
    if len(sample_io) > 0:
        if type(sample_io[0]) == str:
            return "\n".join(sample_io)
        if type(sample_io[0]) == dict:
            return "\n".join(
                f"Input:\n{sample_stdin(io)}\nExpected output:\n{sample_stdout(io)}"
                for io in sample_io
            )
    return sample_io


@tracer
def relevant_problem_exemplars(question: dict):
    dataset_name = config.get("dataset", {}).get("name", "humaneval")
    lang = language_display(get_language(question))
    input_kb_exemplars = PromptTemplate.from_template(INPUT_KB_EXAMPLARS).format(
        prompt=question['prompt'],
        k=mapping[k],
        lang=lang,
    )
    

    response = invoke_model(system_prompt=None, user_prompt=input_kb_exemplars)
    
        # Post processing
    response = trim_text(
        response, "# Identify the algorithm (Brute-force, Dynamic Programming, Divide-and-conquer, Greedy, Backtracking, Recursive, Binary search, and so on) that needs to be used to solve the original problem.")
    response = trim_text(
        response, "# Write a useful tutorial about the above mentioned algorithms. Provide a high level generic tutorial for solving this types of problem. Do not generate code.")
    response = trim_text(
        response, "# Planning to solve this problem:")
    response = trim_text(
        response, f"# Let's think step by step to solve this problem in {lang} programming language.")
    response = replace_tag(response, 'algorithm')
    response = replace_tag(response, 'description')
    response = replace_tag(response, 'code')
    response = replace_tag(response, 'planning')
    
    response = parse_xml(response)
    return response
    

@tracer
def plan(user_prompt, question: dict):
    planning = invoke_model(system_prompt=None, user_prompt=user_prompt)
    lang = language_display(get_language(question))
    
    input_for_planning_verification = PromptTemplate.from_template(PLANNING_VERIFICATION).format(
        prompt=question['prompt'],
        planning=planning,
        lang=lang,
    )
    verification_res = invoke_model(system_prompt=None, user_prompt=input_for_planning_verification)
    
    verification_res = replace_tag(
        verification_res, 'explanation')
    verification_res = replace_tag(verification_res, 'confidence')

    verification_res = parse_xml(verification_res)

    verification_res['confidence'] = int(
        str(verification_res['confidence']).strip())
    
    
    return planning, verification_res
    

@tracer
def code_generation(user_prompt):
    code = invoke_model(system_prompt=None, user_prompt=user_prompt)
    code = parse_code(code)
    return code



@tracer
def code_improvement(user_prompt):
    improved_code = invoke_model(system_prompt=None, user_prompt=user_prompt)
    improved_code = parse_code(improved_code)
    return improved_code



@tracer
def MapCoder(question: dict):
    
    code = ''
    language = get_language(question)
    lang = language_display(language)
    fence = language_fence(language)
    
    try:
        response = relevant_problem_exemplars(question)
        dataset_name = config.get("dataset", {}).get("name", "humaneval")

        algorithm_prompt = f"## Relevant Algorithm to solve the next problem:\n{response['algorithm']}"
        sample_io_prompt = f"## Sample Test cases: \n{get_sample_io_str(question['sample_io'])}\n"
        
        
        plannings = []
        for example_no, example in enumerate(response["problem"], start=1):
            example_problem = example.get('description', '')
            example_planning = example.get('planning', '')
            
            input_for_problem_planning = PromptTemplate.from_template(PROBLEM_PLANNNING).format(
                example_problem=example_problem,
                example_planning=example_planning,
                algorithm_prompt=algorithm_prompt,
                prompt=question['prompt'],
                sample_io_prompt=sample_io_prompt,
            )
            
            planning, verification_res = plan(input_for_problem_planning, question)
            
            
            

            plannings.append((
                planning,
                verification_res['confidence'],
                example
            ))
            
        plannings.sort(key=lambda x: x[1], reverse=True)
        if uses_standard_input(question):
            std_input_prompt = "## Note: Generate a complete executable program that reads standard input and writes only the required output. For Java use public class Main; for C++ include main. Do not print prompts or debug output."
            
        else:
            std_input_prompt = ""
            
        for planning_with_ex in plannings:
            planning, confidence, example = planning_with_ex
            
            input_for_final_code_generation = PromptTemplate.from_template(FINAL_CODE_GENERATION).format(
                algorithm_prompt=algorithm_prompt,
                prompt=question['prompt'],
                planning=planning,
                sample_io_prompt=sample_io_prompt,
                std_input_prompt=std_input_prompt,
                lang=lang,
            )
            
            code = code_generation(input_for_final_code_generation)
            
            response = f"## Planning: {planning}\n## Code:\n```\n{code}\n```"
            passed = False
            
            for i in range(1, t+1):
                passed, test_log = evaluate_sample_io(
                        question,
                        code,
                    )
                
                if passed:
                    break
                
                input_for_improving_code = PromptTemplate.from_template(IMPROVING_CODE).format(
                    algorithm_prompt=algorithm_prompt,
                    prompt=question['prompt'],
                    response=response,
                    test_log=test_log,
                    std_input_prompt=std_input_prompt,
                    lang=lang,
                )
                code = code_improvement(input_for_improving_code)

            if passed:
                break
            
            
    except Exception as e:
        logger.error(f"Error in MapCoder strategy: {e}")
    return f"```{fence}\n{code}\n```"

        
        
            
        
        
                    
        
