from langchain_core.prompts import ChatPromptTemplate, PromptTemplate, FewShotChatMessagePromptTemplate
from utils.config_log import tracer, config
from langchain_core.messages import HumanMessage, SystemMessage
from Integration.prompt import INTEGRATION_PROMPT, INTEGRATION_INPUT, example
from utils.model_invoke import llm



class IntegrationAgent:
    def __init__(self):
        model_config = config.get("model", {})
        self.llm = llm
        self.system_prompt = INTEGRATION_PROMPT
        self.user_input = PromptTemplate.from_template(INTEGRATION_INPUT)
        example_prompts = ChatPromptTemplate.from_messages(
            [
                ("human", "{raw}\n{modules}\n"),
                ("ai", "{output}"),
            ]
        )
        
        # self.few_shot_prompt = FewShotChatMessagePromptTemplate(
        #     example_prompt=example_prompts,
        #     examples=example,
        # ).invoke({}).to_messages()

    @tracer
    def integrate_code(self, requirement: dict, modules: dict) -> str:
        raw = requirement["user_input"]
        modules = modules["code_design"].model_dump_json(exclude={'modules': {'__all__': {'pseudo_code', 'tech_stack', 'nonfunctional_notes', 'dependencies', 'function_signature'}}})
        user_input = self.user_input.format(raw=raw, modules=modules)
        
        messages = [
            SystemMessage(content=self.system_prompt),
            # *self.few_shot_prompt,
            HumanMessage(content=user_input)
        ]
        response = self.llm.invoke(messages)
        return response.content
    
    
integration_agent = IntegrationAgent()