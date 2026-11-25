from requimentAnal.prompt import REQUIREMENT_PROMPT, REQUIREMENT_INPUT
from langchain_core.prompts import PromptTemplate
from utils.config_log import tracer
from utils.model_invoke import invoke_model


class RequirementAgent:
    @tracer
    @staticmethod
    def requirement_analyse(requiremnet: str) -> str:
        user_input = PromptTemplate.from_template(REQUIREMENT_INPUT).format(requirement=requiremnet)

        response = invoke_model(REQUIREMENT_PROMPT, user_input)
        return response

    
# class FunctionalAgent(BaseAgent):
#     PROMPT = FUNC_PROMPT
    
#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         super().__init__(prompt_template=self.PROMPT, model_name=model_name)
        
# class InterfaceAgent(BaseAgent):
#     PROMPT = INTERFACCE_PROMPT
    
#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         super().__init__(prompt_template=self.PROMPT, model_name=model_name)

# class EnvironmentAgent(BaseAgent):
#     PROMPT = ENV_PROMPT
    
#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         super().__init__(prompt_template=self.PROMPT, model_name=model_name)
        
# class NonFunctionalAgent(BaseAgent):
#     PROMPT = NFR_PROMPT
    
#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         super().__init__(prompt_template=self.PROMPT, model_name=model_name)
        
# class ImplicitAgent(BaseAgent):
#     PROMPT = IMPLICIT_PROMPT
    
#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         super().__init__(prompt_template=self.PROMPT, model_name=model_name)