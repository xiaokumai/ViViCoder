from utils.config_log import config, tracer
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from prompts.CodeSIM import PROMPT_FOR_PLANNING, PROMPT_FOR_SIMULATION, PROMPT_FOR_REFINEMENT, PROMPT_FOR_CODE_GENERATION, PROMPT_FOR_DEBUGGING
from utils.local_runner import evaluate_sample_io, evaluate_additional_io, parse_response
from typing import List
from utils.model_invoke import invoke_model
import re
from loguru import logger
from utils.language import get_language, language_display, language_fence, uses_standard_input




def process_test_log(test_logs: str):
    passed_test_cases = []
    failed_test_cases = []
    for test_log in test_logs.splitlines():
        if test_log.startswith("Passed"):
            passed_test_cases.append(test_log[test_log.index("assert"):])
        if test_log.startswith("Failed"):
            failed_test_cases.append(test_log[test_log.index("assert"):])
    
    failed_test_cases_str = "\n".join(failed_test_cases)
    return f"### Test Cases where the generated code failed to generate the expected output:\n{failed_test_cases_str}"


def check(
        data_row: dict,
        additional_io: List[str],
        code: str
) -> bool:
    passed_sample, test_log_sample = evaluate_sample_io(
        data_row,
        code,
        )
    
    passed_additional, test_log_additional = evaluate_additional_io(
        data_row,
        additional_io,
        code,
    )
    
    dataset_name = config.get("dataset", {}).get("name", "humaneval")
    if dataset_name == 'evocodebench':
        # Repository pytest output is already structured debugging feedback;
        # assertion-only parsing would discard it (or fail on missing `assert`).
        test_log = test_log_sample
    elif uses_standard_input(data_row):
        
        test_log_sample = test_log_sample[test_log_sample.find("## Tests failed:"):]
        test_log = test_log_sample + test_log_additional
    else:
        test_log = process_test_log(test_log_sample + test_log_additional)
        
    return passed_sample & passed_additional, test_log
    
    
    

max_plan_try = 5
max_debug_try = 10


@tracer
def make_plan(problem, language: str):
    input_for_planning = PromptTemplate.from_template(PROMPT_FOR_PLANNING).format(
        problem=problem,
        lang=language_display(language),
    )
    response = invoke_model(system_prompt=None, user_prompt=input_for_planning)
    
    if "### Plan" not in response:
        plan = f"### Plan\n\n{response}"
    else:
        plan = response[response.rfind("### Plan"):]
        
    return plan


@tracer
def simulate(problem_with_planning: str, language: str):
    input_for_simulation = PromptTemplate.from_template(PROMPT_FOR_SIMULATION).format(
        problem_with_planning=problem_with_planning,
        lang=language_display(language),
    )
    response = invoke_model(system_prompt=None, user_prompt=input_for_simulation)
    
    return response

@tracer
def refine_plan(input_for_plan_refinement: str):
    response = invoke_model(system_prompt=None, user_prompt=input_for_plan_refinement)
    
    return response

@tracer
def code_generation(input_for_final_code_generation: str):
    response = invoke_model(system_prompt=None, user_prompt=input_for_final_code_generation)
    code = parse_response(response)
    
    return code


@tracer
def debug(input_for_debugging: str):
    response = invoke_model(system_prompt=None, user_prompt=input_for_debugging)
    code = parse_response(response)
    return code


@tracer
def CodeSIM(question: dict):
    code = ''
    language = get_language(question)
    lang = language_display(language)
    fence = language_fence(language)
    try:
        
        dataset_name = config.get("dataset", {}).get("name", "humaneval")
        
        problem = question['prompt']

        std_input_prompt = ""
        
        if uses_standard_input(question):
            std_input_prompt = \
    """- Strictly follow the sample input and output format. 
- Generate a complete executable program that reads standard input and writes only the required output.
- For Java use public class Main; for C++ include main.
- Do not add prompts or debug output."""

            marker = problem.find("-------\nImportant Note:")
            if marker != -1:
                problem = problem[:marker]
            
        additional_io = []

        # Planning, Coding, Debugging
        for plan_no in range(1, max_plan_try + 1):
            # Planning Phase
            plan = make_plan(problem, language)

            problem_with_planning = f"## Problem:\n{problem}\n\n{plan}"

            response = simulate(problem_with_planning, language)
            
        
            if "Plan Modification Needed" in response and \
                "No Plan Modification Needed" not in response:
                
                input_for_plan_refinement = PromptTemplate.from_template(PROMPT_FOR_REFINEMENT).format(
                    problem_with_planning=problem_with_planning,
                    critique=response,
                    lang=lang,
                )
                
                plan = refine_plan(input_for_plan_refinement)
                
                problem_with_planning = f"## Problem:\n{problem}\n\n{plan}"

            input_for_final_code_generation = PromptTemplate.from_template(PROMPT_FOR_CODE_GENERATION).format(
                problem_with_planning=problem_with_planning,
                std_input_prompt=std_input_prompt,
                lang=lang,
            )

            code = code_generation(input_for_final_code_generation)
            
            
            passed, test_log = check(question, additional_io, code)
            # Do not need to go for debugging steps
            if passed:
                break
            for debug_no in range(1, max_debug_try + 1):
                input_for_debugging = PromptTemplate.from_template(PROMPT_FOR_DEBUGGING).format(
                    problem_with_planning=problem_with_planning,
                    code=code,
                    test_log=test_log,
                    std_input_prompt=std_input_prompt,
                    lang=lang,
                    fence=fence,
                )
                
                code = debug(input_for_debugging)
                
                passed, test_log = check(question, additional_io, code)
                if passed: 
                    break
                
            if passed:
                break
            
        return f"```{fence}\n{code}\n```"
    except Exception as e:
        logger.error(f"Error in CodeSIM strategy: {e}")
        return f'```{fence}\n{code}\n```'
        


            


        
