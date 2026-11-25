from langchain_core.prompts import PromptTemplate
from utils.config_log import config, tracer
from requimentAnal.prompt import refinement_system_prompt
from langchain_core.messages import HumanMessage, SystemMessage
from utils.model_invoke import llm



class RequirementRefiner:
    def __init__(self):
        """
        Initializes the RequirementRefiner class with the specified language model.
        
        Args:
            model (str): The language model to be used (default is "gpt-3.5-turbo").
        """
        
        
        model_config = config.get("model", {})
        
        self.llm = llm
        self.system_prompt = refinement_system_prompt
        
        # self.user_input = PromptTemplate.from_template(User_requirement_prompt)
        
    @tracer
    def refine_requirement(self, user_input: str) -> str:
        """
        Refines the given user input requirement using the language model.
        
        Args:
            user_input (str): The user input requirement to be refined.
            tech_stack (str): The technology stack to consider while refining the requirement.
        
        Returns:
            str: The refined requirement.
        """
        
        user_input = self.user_input.format(user_input=user_input)
        
        # Create the prompt by filling in the user input and tech stack
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_input)
        ]
        
        # Get the response from the language model
        response = self.llm.invoke(messages)

        # Return the content of the response
        return response.content
        
        
        
       