from utils.config_log import tracer, config
from tester.prompt import TEST_SYSTEM, TEST_INPUT, TEST_REFINEMENT_SYSTEM, TEST_REFINEMENT_INPUT, PBT_SYSTEM, PBT_INPUT
from utils.model_invoke import invoke_model
from langchain_core.prompts import PromptTemplate
import json
from utils.local_runner import parse_response
from langchain_core.messages import HumanMessage


@tracer
def generate_test(prompt: str, requirement: str, code: str):
    user_input = PromptTemplate.from_template(PBT_INPUT).format(
        prompt=prompt,
        requirement=requirement,
        code=code,
    )
    
    response = invoke_model(
        system_prompt=PBT_SYSTEM,
        user_prompt=user_input,
    )
    
    return parse_response(response)

import requests
import json

@tracer
def run_test(code:str):
    url = "http://localhost:8081/run_code"
    data = {
        "code": code,
        "language": "pytest",
        "compile_timeout": 60,
        "run_timeout": 60,
    }
    res = requests.post(url, json=data).json()
    
    if res['status']=='Success':
        return True,''
    else:
        return False,res['run_result']['stdout']
    
    
        
    



# @tracer
# def generate_test(question: dict, prompt: str, requirement: str):
#     model_config = config.get("model", {})
#     llm = init_chat_model(**model_config)
    
#     agent = create_agent(
#         model=llm,
#         system_prompt=TEST_SYSTEM + GEN_TOOL_INPUT,
#         tools=[python_interpreter]
#     )
    
    
    
#     user_input = PromptTemplate.from_template(TEST_INPUT).format(
#         prompt=prompt,
#         requirement=requirement,
#         sample_io=json.dumps(question["sample_io"]),
#     )
    
#     response = agent.invoke(
#         {"messages": [{"role": "user", "content": user_input}]},
#     )['messages'][-1].content

#     return response
    


@tracer
def refine_test(question: dict, prompt: str, design: str, add_test_cases: str):
    user_input = PromptTemplate.from_template(TEST_REFINEMENT_INPUT).format(
        prompt=prompt,
        design=design,
        test_cases=add_test_cases,
        sample_io=json.dumps(question["sample_io"]),
    )
    response = invoke_model(
        system_prompt=TEST_REFINEMENT_SYSTEM,
        user_prompt=user_input,
    )
    return parse_response(response)




# @tracer
# def refine_test(question: dict, prompt: str, design: str, add_test_cases: str):
#     model_config = config.get("model", {})
#     llm = init_chat_model(**model_config)
    
#     agent = create_agent(
#         model=llm,
#         system_prompt=TEST_REFINEMENT_SYSTEM + REFINE_TOOL_INPUT,
#         tools=[python_interpreter]
#     )
    
    
    
#     user_input = PromptTemplate.from_template(TEST_REFINEMENT_INPUT).format(
#         prompt=prompt,
#         design=design,
#         test_cases=add_test_cases,
#         sample_io=json.dumps(question["sample_io"]),
#     )

#     response = agent.invoke(
#         {"messages": [{"role": "user", "content": user_input}]},
#     )['messages'][-1].content

#     return response
    
    
# from jsonfinder import jsonfinder

# text = 'text before [{"a":1,"b":{"c":2}}] text after {"x":10}'

# for start, end, obj in jsonfinder(text):
#     if obj:  # obj will be None if JSON is invalid
#         print(obj)
#         print(type(obj))
