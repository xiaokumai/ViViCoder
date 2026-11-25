from requimentAnal.agents import RequirementAgent
from utils.model_invoke import invoke_model
from requimentAnal.prompt import REQUIREMENT_PROMPT, REQUIREMENT_INPUT, TOOL_INPUT
from langchain_core.prompts import PromptTemplate
from utils.config_log import tracer
from utils.language import language_display, normalize_language

@tracer
def analysis(user_input: str, search_tool, language: str = "python"):
    
    user_input = PromptTemplate.from_template(REQUIREMENT_INPUT).format(
        requirement=user_input,
        language=language_display(normalize_language(language)),
    )

    response = invoke_model(REQUIREMENT_PROMPT, user_input)
    return response

    

# @tracer
# def analysis(user_input: str,search_tool) -> dict:
    
#     from langchain.tools import tool

#     @tool
#     def web_search(query: str) -> str:
#         """Performs a duckduckgo web search based on your query (think a Google search) then returns the top search results."""
#         try:
#             results = search_tool(query)
#             return results
#         except Exception as e:
#             return f"An error occurred during web search: {str(e)}"
        
        
#     model_config = config.get("model", {})
#     llm = init_chat_model(**model_config)
    
#     agent = create_agent(
#         model=llm,
#         system_prompt=REQUIREMENT_PROMPT + TOOL_INPUT,
#         tools=[web_search]
#     )
    
#     user_input = PromptTemplate.from_template(REQUIREMENT_INPUT).format(requirement=user_input)

#     response = agent.invoke(
#         {"messages": [{"role": "user", "content": user_input}]},
#     )['messages'][-1].content

#     return response

# @tracer
# def requirement_document(user_input: str) -> str:
#     """
#     Generates a structured documentation string from the analysis result.

#     Args:
#         analysis_result (dict): The dictionary containing categorized requirements.

#     Returns:
#         str: A formatted documentation string.
#     """
#     analysis_result = analysis(user_input)
    
#     document = f"""# Software Requirements Specification (SRS)

# ## 1. Introduction
# This document describes the results of the system requirements analysis, including functional requirements, non-functional requirements, operating environment requirements, and implicit requirements.

# ## 2. Overall Description
# User Requirements:
# > {user_input}

# ## 3. Refined User Requirements
# > {analysis_result['refined_user_input']}

# ## 4. Requirements
# {requirements_to_text(analysis_result['requirement'])}

#     """
#     analysis_result["doc"] = document
    
#     with open("SRS_document.md", "w", encoding="utf-8") as f:
#         f.write(document)
        
    return analysis_result
    



# def analysis(user_input: str) -> dict:
#     """
#     Analyzes the user input requirement and categorizes it into functional, environmental,
#     non-functional, and implicit requirements after refining it.

#     Args:
#         user_input (str): The user input requirement to be analyzed.

#     Returns:
#         dict: A dictionary containing categorized requirements.
#     """
    
#     refiner = RequirementRefiner()
#     model_name = config.get("model", {}).get("name", "gpt-3.5-turbo")

#     func_agent = FunctionalAgent(model_name=model_name)
#     interface_agent = InterfaceAgent(model_name=model_name)
#     env_agent = EnvironmentAgent(model_name=model_name)
#     # nfr_agent = NonFunctionalAgent(model_name=model_name)
#     implicit_agent = ImplicitAgent(model_name=model_name)
    
#     tasks = {
#         "functional": func_agent,
#         "interface": interface_agent,
#         "environment": env_agent,
#         # "nonfunctional": nfr_agent,
#         "implicit": implicit_agent,
#     }
    
#     results = {}
#     results["user_input"] = user_input
    
#     # Step 1: Refine the user input requirement
#     refined_requirement = refiner.refine_requirement(user_input)
#     results["refined_requirement"] = refined_requirement

#     # Step 2: Extract categorized requirements using respective agents
#     with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
#         future_to_key = {executor.submit(agent.Requirement_extraction, refined_requirement): key for key, agent in tasks.items()}
#         for future in as_completed(future_to_key):
#             key = future_to_key[future]
#             results[key] = future.result()    
    


#     return results
