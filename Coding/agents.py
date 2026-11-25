from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from utils.config_log import tracer, config
from Coding.prompt import CODE_PROMPT, CODE_INPUT, STD_INPUT_PROMPT
from utils.model_invoke import invoke_model



class ViViCoder:
    @tracer
    @staticmethod
    def generate_code(detailed_modules: dict) -> str:
        dataset_name = config.get("dataset", {}).get("name", "humaneval")
        if dataset_name == 'livecodebench' and detailed_modules['platform'] == 'atcoder':
            std_input_prompt = STD_INPUT_PROMPT
        else:
            std_input_prompt = ''
        

        user_input = PromptTemplate.from_template(CODE_INPUT).format(
            raw=detailed_modules['prompt'],
            pseudo_code=detailed_modules['detail'],
            std_input_prompt=std_input_prompt,
            )


        response = invoke_model(CODE_PROMPT, user_input)
        return response
