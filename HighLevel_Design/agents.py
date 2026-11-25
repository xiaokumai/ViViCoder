from langchain_core.prompts import PromptTemplate
from utils.config_log import tracer, config
from HighLevel_Design.prompt import MODULE_DESIGN_PROMPT, MODULE_DESIGN_INPUT
from utils.model_invoke import invoke_model
from HighLevel_Design.tool import web_search
from langchain.agents import create_agent
from utils.model_invoke import llm

class OverallDesignAgent:
    @tracer
    @staticmethod
    def Overall_design(requirements: dict) -> str:
        raw = requirements["prompt"]
        analysis = requirements["requirement"]

        user_input = PromptTemplate.from_template(MODULE_DESIGN_INPUT).format(raw=raw,analysis=analysis)

        response = invoke_model(MODULE_DESIGN_PROMPT, user_input)
        return response


def web_search_agent(requirements: dict):
    model_config = config.get("model", {})
    
    agent = create_agent(
        model=llm,
        system_prompt=MODULE_DESIGN_PROMPT,
        tools=[web_search]
    )
    
    raw = requirements["prompt"]
    analysis = requirements["requirement"]

    user_input = PromptTemplate.from_template(MODULE_DESIGN_INPUT).format(raw=raw,analysis=analysis)
    
    response = agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]},
    )['messages'][-1].content
    
    return response


# def web_search_agent():
#     model_id = config['model']['model']
#     temperature = config['model']['temperature']
#     top_p = config['model']['top_p']
    
#     model = OpenAIServerModel(
#         model_id=model_id,
#         stop=REMOVE_PARAMETER,
#         temperature=temperature,
#         top_p=top_p
#     )
    
#     agent = ToolCallingAgent(
#         model=model,
#         tools=[DuckDuckGoSearchTool(max_results=5, rate_limit=1.0)],
#         verbosity_level=0,
#         max_steps=2,
#         # additional_authorized_imports=['requests', 'bs4'],
#     )
    
#     return agent


# class ModuleDecomposeAgent:
#     PROMPT = MOD_DECOMPOSE_PROMPT

#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         self.agent = create_react_agent(model=model_name, tools=[], prompt=self.PROMPT)

#     @tracer.chain
#     def Module_decompose(self, requirements: dict) -> str:
#         input_template = ChatPromptTemplate.from_messages(
#             [("user", MOD_DECOMPOSE_INPUT)]
#         )
#         raw = requirements["user_input"]
#         fr = requirements["functional"]
        
#         user_input = input_template.invoke({"raw": raw, "fr": fr})
#         response = self.agent.invoke(user_input)
#         return response["messages"][-1].content


# class ModuleDecomposeAgent:    
#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         self.llm = init_chat_model(model_name)
#         self.system_prompt = MOD_DECOMPOSE_PROMPT
#         self.user_input = PromptTemplate.from_template(MOD_DECOMPOSE_INPUT)

#     @tracer
#     def Module_decompose(self, requirements: dict) -> str:
#         raw = requirements["user_input"]
#         fr = requirements["functional"]

#         user_input = self.user_input.format(raw=raw, fr=fr)
        
#         messages = [
#             SystemMessage(content=self.system_prompt),
#             HumanMessage(content=user_input)
#         ]

#         response = self.llm.invoke(messages)
#         return response.content
        

    
# class ModuleDependencyAgent:
#     PROMPT = DEPENDCY_MAP_PROMPT

#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         self.agent = create_react_agent(model=model_name, tools=[], prompt=self.PROMPT)

#     @tracer.chain
#     def Module_dependency(self, requirements: dict, modules_design: dict) -> str:
#         input_template = ChatPromptTemplate.from_messages(
#             [("user", DEPENDCY_MAP_INPUT)]
#         )
#         raw = requirements["user_input"]
#         fr = requirements["functional"]
#         modules = modules_design["module_decompose"]
        
#         user_input = input_template.invoke({"raw": raw, "fr": fr, "modules": modules})
#         response = self.agent.invoke(user_input)
#         return response["messages"][-1].content


# class ModuleDependencyAgent:    
#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         self.llm = init_chat_model(model_name)
#         self.system_prompt = DEPENDCY_MAP_PROMPT
#         self.user_input = PromptTemplate.from_template(DEPENDCY_MAP_INPUT)
#     @tracer
#     def Module_dependency(self, requirements: dict, modules_design: dict) -> str:
#         raw = requirements["user_input"]
#         fr = requirements["functional"]
#         modules = modules_design["module_decompose"]

#         user_input = self.user_input.format(raw=raw, fr=fr, modules=modules)
#         messages = [
#             SystemMessage(content=self.system_prompt),
#             HumanMessage(content=user_input)
#         ]

#         response = self.llm.invoke(messages)
#         return response.content


# class ModuleInterfaceAgent:
#     PROMPT = INTERFACE_DEFINE_PROMPT

#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         self.agent = create_react_agent(model=model_name, tools=[], prompt=self.PROMPT, response_format=InterfacesOutput)

#     @tracer.chain
#     def Module_interface(self, requirements: dict, modules_design: dict) -> str:
#         input_template = ChatPromptTemplate.from_messages(
#             [("user", INTERFACE_DEFINE_INPUT)]
#         )
#         fr = requirements["functional"]
#         tech_stack = requirements.get("environment", "python")
#         modules = modules_design["module_decompose"]
#         dependency = modules_design["module_dependency"]
        
#         user_input = input_template.invoke({"fr": fr, "tech_stack": tech_stack, "modules": modules, "dependency": dependency})
#         response = self.agent.invoke(user_input)
#         return response["structured_response"]
    

# class ModuleInterfaceAgent:
#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         self.llm = init_chat_model(model_name).with_structured_output(InterfacesOutput)
#         self.system_prompt = INTERFACE_DEFINE_PROMPT
#         self.user_input = PromptTemplate.from_template(INTERFACE_DEFINE_INPUT)
        
#     @tracer
#     def Module_interface(self, requirements: dict, modules_design: dict) -> str:
#         fr = requirements["functional"]
#         tech_stack = requirements.get("environment", "python")
#         modules = modules_design["module_decompose"]
#         dependency = modules_design["module_dependency"]

#         user_input = self.user_input.format(fr=fr, tech_stack=tech_stack, modules=modules, dependency=dependency)
#         messages = [
#             SystemMessage(content=self.system_prompt),
#             HumanMessage(content=user_input)
#         ]

#         response = self.llm.invoke(messages)
#         return response

# class NonFunctionalAgent:
#     PROMPT = NON_FUNCTION_PROMPT

#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         self.agent = create_react_agent(model=model_name, tools=[], prompt=self.PROMPT, response_format=NonFunctionOutput)

#     @tracer.chain
#     def Non_functional(self, requirements: dict, modules_design: dict) -> str:
#         input_template = ChatPromptTemplate.from_messages(
#             [("user", NON_FUNCTION_INPUT)]
#         )
#         raw = requirements["user_input"]
#         # nfr = requirements.get("nonfunctional", "")
#         nfr = requirements.get("implicit", "")
#         modules = modules_design["modules"]
        
        
#         user_input = input_template.invoke({"raw": raw, "nfr": nfr, "modules": modules})
#         response = self.agent.invoke(user_input)
#         return response["structured_response"]


# class NonFunctionalAgent:
#     def __init__(self, model_name: str = "gpt-3.5-turbo"):
#         self.llm = init_chat_model(model_name).with_structured_output(NonFunctionOutput)
#         self.system_prompt = NON_FUNCTION_PROMPT
#         self.user_input = PromptTemplate.from_template(NON_FUNCTION_INPUT)
        
#     @tracer
#     def Non_functional(self, requirements: dict, modules_design: dict) -> str:
#         raw = requirements["user_input"]
#         # nfr = requirements.get("nonfunctional", "")
#         nfr = requirements.get("implicit", "")
#         modules = modules_design["modules"].model_dump_json()

#         user_input = self.user_input.format(raw=raw, nfr=nfr, modules=modules)
#         messages = [
#             SystemMessage(content=self.system_prompt),
#             HumanMessage(content=user_input)
#         ]

#         response = self.llm.invoke(messages)
#         return response