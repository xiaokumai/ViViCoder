from langchain_core.prompts import PromptTemplate
from utils.config_log import tracer, config
from HighLevel_Design.prompt import (
    MODULE_DESIGN_PROMPT,
    MODULE_DESIGN_INPUT,
    MODULE_REDESIGN_INPUT,
    SIMULATION_SYSTEM,
    SIMULATION_INPUT,
    REFINEMENT_SYSTEM,
    REFINEMENT_INPUT,
    TOOL_INPUT,
)
from utils.model_invoke import invoke_model
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from utils.model_invoke import llm
from utils.language import language_display, normalize_language

# @tracer
# def overall_design(prompt: str, requirement: str) -> dict:
#     """
#     Generates a structured documentation string from the requirements analysis.
#     """


#     user_input = PromptTemplate.from_template(MODULE_DESIGN_INPUT).format(prompt=prompt,analysis=requirement)

#     response = invoke_model(MODULE_DESIGN_PROMPT, user_input)
#     return response
    

@tracer
def overall_design(
    prompt: str,
    requirement: str,
    search_tool,
    failure_experience: str | None = None,
    language: str = "python",
):
    """
    Generates a structured documentation string from the requirements analysis.
    """
    
    
    from langchain.tools import tool

    @tool
    def web_search(query: str) -> str:
        """Performs a duckduckgo web search based on your query (think a Google search) then returns the top search results."""
        try:
            results = search_tool(query)
            return results
        except Exception as e:
            return f"An error occurred during web search: {str(e)}"
    
    model_config = config.get("model", {})
    
    lang = language_display(normalize_language(language))
    system_prompt = PromptTemplate.from_template(
        MODULE_DESIGN_PROMPT + TOOL_INPUT
    ).format(lang=lang)
    agent = create_agent(
        model=llm,
        system_prompt=system_prompt,
        tools=[web_search]
    )
    

    if failure_experience:
        user_input = PromptTemplate.from_template(MODULE_REDESIGN_INPUT).format(
            prompt=prompt,
            analysis=requirement,
            failure_experience=failure_experience,
        )
    else:
        user_input = PromptTemplate.from_template(MODULE_DESIGN_INPUT).format(
            prompt=prompt,
            analysis=requirement,
        )
    
    response = agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]},
    )['messages'][-1].content

    return response



@tracer
def simulate(prompt: str, design: str, language: str = "python"):
    input_for_simulation = PromptTemplate.from_template(SIMULATION_INPUT).format(
        prompt=prompt,
        design=design
    )
    
    system_prompt = PromptTemplate.from_template(SIMULATION_SYSTEM).format(
        lang=language_display(normalize_language(language))
    )
    response = invoke_model(system_prompt, input_for_simulation)
    return response


@tracer
def refine(prompt: str, design: str, simulation: str, language: str = "python"):
    input_for_plan_refinement = PromptTemplate.from_template(REFINEMENT_INPUT).format(
        prompt=prompt,
        wrong_plan=design,
        critique=simulation
    )
    
    system_prompt = PromptTemplate.from_template(REFINEMENT_SYSTEM).format(
        lang=language_display(normalize_language(language))
    )
    response = invoke_model(system_prompt, input_for_plan_refinement)
    return response
