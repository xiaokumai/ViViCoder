from utils.config_log import config
from langchain_core.prompts import PromptTemplate
from prompts.Analogical import STSTEM_PROMPT, ANALOGICAL_PROMPT
from utils.model_invoke import invoke_model
from utils.language import get_language, language_display, language_fence


def analogical(question: dict):
    language = get_language(question)
    user_input = PromptTemplate.from_template(ANALOGICAL_PROMPT).format(
        prompt=question['prompt'],
        lang=language_display(language),
        fence=language_fence(language),
    )
    
    response = invoke_model(system_prompt=STSTEM_PROMPT, user_prompt=user_input)
        
    return response
    
    
