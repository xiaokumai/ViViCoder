from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
# ---------------------------
# BaseAgent class
# ---------------------------
# class BaseAgent:
#     def __init__(self, prompt_template: str, model_name: str = "gpt-3.5-turbo"):
#         self.agent = create_react_agent(model=model_name, tools=[], prompt=prompt_template)
        
#     @tracer.chain
#     def Requirement_extraction(self, user_input: str) -> str:
#         input_template = ChatPromptTemplate.from_messages(
#             [("user", User_requirement_prompt)]
#         )
#         user_input = input_template.invoke({"user_input": user_input})
#         response = self.agent.invoke(user_input)
#         return response["messages"][-1].content

   
# class BaseAgent:
#     def __init__(self, prompt_template: str, model_name: str = "gpt-3.5-turbo"):
#         self.llm = init_chat_model(model_name)
#         self.system_prompt = prompt_template
#         self.user_input = PromptTemplate.from_template(User_requirement_prompt)

        
#     @tracer
#     def Requirement_extraction(self, user_input: str) -> str:
#         user_input = self.user_input.format(user_input=user_input)
        
#         messages = [
#             SystemMessage(content=self.system_prompt),
#             HumanMessage(content=user_input)
#         ]

#         response = self.llm.invoke(messages)
#         return response.content
