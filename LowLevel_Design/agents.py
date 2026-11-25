from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from utils.config_log import tracer
from LowLevel_Design.prompt import DETAILED_PROMPT, DETAILED_INPUT
from langchain_core.messages import HumanMessage, SystemMessage
from utils.model_invoke import invoke_model

# class DetailedDesignAgent:
#     PROMPT = DETAILED_PROMPT

#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         self.agent = create_react_agent(model=model_name, tools=[], prompt=self.PROMPT, response_format=DetailedOutput)

#     @tracer.chain
#     def generate_detailed_design(self, requirements: dict, modules_design: dict) -> str:
#         input_template = ChatPromptTemplate.from_messages(
#             [("user", DETAILED_INPUT)]
#         )
#         raw = requirements["user_input"]
#         fr = requirements["functional"]
#         modules = modules_design["modules"]
#         module_dependency = modules_design["module_dependency"]
        
#         user_input = input_template.invoke({"raw": raw, "fr": fr, "modules": modules, "module_dependency": module_dependency})
#         response = self.agent.invoke(user_input)
#         return response["structured_response"]


class DetailedDesignAgent:
    @tracer
    @staticmethod
    def generate_detailed_design(overall_design: dict) -> str:
        raw = overall_design["prompt"]
        overall = overall_design["overall"]
        
        user_input = PromptTemplate.from_template(DETAILED_INPUT).format(
            raw=raw,
            plan=overall
        )
        

        response = invoke_model(DETAILED_PROMPT, user_input)
        return response
    
    