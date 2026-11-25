from utils.config_log import tracer, config
from utils.local_runner import parse_response
from Coding.prompt import CODE_PROMPT, CODE_INPUT, STD_INPUT_PROMPT, TOOL_INPUT, SMOL_PROMPT
from Coding.tool import python_interpreter
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from utils.model_invoke import invoke_model
from utils.language import get_language, language_display, language_fence, uses_standard_input


@tracer
def code_generation(question :dict, prompt :str, design :str, requirement :str, search_tool) -> str:
    """
    Generates code for each module based on the detailed design.
    """
    
    language = get_language(question)
    if uses_standard_input(question):
        std_input_prompt = STD_INPUT_PROMPT
    else:
        std_input_prompt = ''
    

    user_input = PromptTemplate.from_template(CODE_INPUT).format(
        prompt=prompt,
        plan=design,
        std_input_prompt=std_input_prompt,
        requirement=requirement,
        lang=language_display(language),
        fence=language_fence(language),
    )

    system_prompt = PromptTemplate.from_template(CODE_PROMPT).format(
        lang=language_display(language)
    )
    response = invoke_model(system_prompt, user_input)

    
    return parse_response(response)


# @tracer
# def code_generation(question :dict, prompt :str, design :str, requirement :str, search_tool) -> str:
#     """
#     Generates code for each module based on the detailed design.
#     """
    
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
    
    
#     dataset_name = config.get("dataset", {}).get("name", "humaneval")
#     if dataset_name == 'livecodebench' and question['platform'] == 'atcoder':
#         std_input_prompt = STD_INPUT_PROMPT
#     else:
#         std_input_prompt = ''

#     agent = create_agent(
#         model=llm,
#         system_prompt=CODE_PROMPT + TOOL_INPUT,
#         tools=[web_search],
#     )
    
#     user_input = PromptTemplate.from_template(CODE_INPUT).format(
#         prompt=prompt,
#         plan=design,
#         std_input_prompt=std_input_prompt,
#         requirement=requirement,
#     )
    
    
#     response = agent.invoke(
#         {"messages": [{"role": "user", "content": user_input}]},
#     )['messages'][-1].content

#     return parse_response(response)


