from utils.config_log import tracer, config
from Coding.prompt import STD_INPUT_PROMPT
from debug.prompt import DUBUG_SYSTEM, DUBUG_INPUT, TOOL_INPUT, IC_DEDUG_INPUT, ADD_DEBUG_INPUT, ADD_DUBUG_SYSTEM, PBT_DEBUG_SYSTEM, PBT_DEBUG_INPUT
from langchain_core.prompts import PromptTemplate
from utils.model_invoke import invoke_model
from utils.local_runner import parse_response
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from utils.language import get_language, language_display, language_fence, uses_standard_input

@tracer
def debug_code(
    question: dict,
    prompt: str,
    design: str,
    code: str,
    test_log: str,
    weather_ic=False,
):
    language = get_language(question)
    lang = language_display(language)
    fence = language_fence(language)

    if uses_standard_input(question):
        std_input_prompt = STD_INPUT_PROMPT
    else:
        std_input_prompt = ''
        
    if weather_ic:
        user_input = PromptTemplate.from_template(IC_DEDUG_INPUT).format(
            prompt=prompt,
            design=design,
            code=code,
            test_log=test_log,
            std_input_prompt=std_input_prompt,
            lang=lang,
            fence=fence,
        )
        
    else:
        user_input = PromptTemplate.from_template(DUBUG_INPUT).format(
            prompt=prompt,
            design=design,
            code=code,
            test_log=test_log,
            std_input_prompt=std_input_prompt,
            lang=lang,
            fence=fence,
        )
    system_prompt = PromptTemplate.from_template(DUBUG_SYSTEM).format(lang=lang)
    response = invoke_model(
        system_prompt=system_prompt,
        user_prompt=user_input,
    )
    return parse_response(response)





@tracer
def PBT_debug_code(prompt :str, code :str, test_log :str):
    user_input = PromptTemplate.from_template(PBT_DEBUG_INPUT).format(
        prompt=prompt,
        code=code,
        test_log=test_log,
    )
        
    response = invoke_model(
        system_prompt=PBT_DEBUG_SYSTEM,
        user_prompt=user_input,
    )
    return parse_response(response)




@tracer
def add_debug_code(
    question: dict,
    prompt: str,
    design: str,
    code: str,
    test_log: str,
    weather_ic=False,
):
    language = get_language(question)
    lang = language_display(language)
    fence = language_fence(language)

    if uses_standard_input(question):
        std_input_prompt = STD_INPUT_PROMPT
    else:
        std_input_prompt = ''
        
    if weather_ic:
        user_input = PromptTemplate.from_template(ADD_DEBUG_INPUT).format(
            prompt=prompt,
            design=design,
            code=code,
            test_log=test_log,
            std_input_prompt=std_input_prompt,
            lang=lang,
            fence=fence,
        )
        system_prompt = PromptTemplate.from_template(ADD_DUBUG_SYSTEM).format(
            lang=lang
        )
        response = invoke_model(
            system_prompt=system_prompt,
            user_prompt=user_input,
        )
        
    else:
        user_input = PromptTemplate.from_template(DUBUG_INPUT).format(
            prompt=prompt,
            design=design,
            code=code,
            test_log=test_log,
            std_input_prompt=std_input_prompt,
            lang=lang,
            fence=fence,
        )
        system_prompt = PromptTemplate.from_template(DUBUG_SYSTEM).format(lang=lang)
        response = invoke_model(
            system_prompt=system_prompt,
            user_prompt=user_input,
        )
    return parse_response(response)

# @tracer
# def debug_code(question: dict, prompt :str, code :str, test_log :str, search_tool):
#     dataset_name = config.get("dataset", {}).get("name", "humaneval")
    
#     if dataset_name == 'livecodebench' and question['platform'] == 'atcoder':
#         std_input_prompt = STD_INPUT_PROMPT
#     else:
#         std_input_prompt = ''
    
    
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
#         system_prompt=DUBUG_SYSTEM + TOOL_INPUT,
#         tools=[web_search]
#     )
    
#     user_input = PromptTemplate.from_template(DUBUG_INPUT).format(
#         prompt=prompt,
#         code=code,
#         test_log=test_log,
#         std_input_prompt=std_input_prompt
#     )
    
#     response = agent.invoke(
#         {"messages": [{"role": "user", "content": user_input}]},
#     )['messages'][-1].content

#     return parse_response(response)
