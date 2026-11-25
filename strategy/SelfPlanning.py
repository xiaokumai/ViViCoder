from utils.config_log import config, tracer
from langchain_core.prompts import PromptTemplate
from prompts.SelfPlanning import PLANNING_SYSTEM_PROMPT, PLANNING_INPUT, IMPLEMENTATION_SYSTEM_PROMPT, IMPLEMENTATION, planning_map
from utils.model_invoke import invoke_model




@tracer
def SelfPlanning(question: dict) -> str:
    """Self-Planning reasoning strategy.
    Args:
        question (str): The input question.
        n (int): Number of responses to generate.
    Returns:
        str: The generated response.
    """
    
    dataset_name = config.get("dataset", {}).get("name", "humaneval")
    planning = planning_map[dataset_name]
    
    planning_input = PromptTemplate.from_template(PLANNING_INPUT).format(planning=planning, prompt=question['prompt'])
    
    planning_responses = invoke_model(system_prompt=PLANNING_SYSTEM_PROMPT, user_prompt=planning_input)
    
    
    implementation_input = PromptTemplate.from_template(IMPLEMENTATION).format(planning=planning_responses, prompt=question['prompt'])
    

    response = invoke_model(system_prompt=IMPLEMENTATION_SYSTEM_PROMPT, user_prompt=implementation_input)
    
    return response

    
    