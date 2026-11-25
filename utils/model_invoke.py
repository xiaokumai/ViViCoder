from utils.config_log import config
from langchain.chat_models import init_chat_model
import tiktoken
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from langchain_openai import ChatOpenAI

# Context-window sizes supported by each model; extend this mapping as needed.
MODEL_CONTEXT_LIMITS = {
    "gpt-3.5-turbo": 16000,
    "gpt-4o-mini": 128000,
    "gpt-4o": 128000,
    "gpt-5-2025-08-07": 400000,
    "codellama-70b-instruct": 100000,
}

model_config = config.get("model", {})

if model_config['model'] == 'gpt-5-mini':
    model_config.pop('top_p')
    
    
llm = ChatOpenAI(
    model=model_config['model'], 
    temperature=model_config['temperature'],
    top_p=model_config['top_p'],
    # extra_body={
    # "enable_thinking": False, 
    # }
)

# llm = init_chat_model(**model_config)

def invoke_model(system_prompt: str | None, user_prompt: str,reserve_tokens: int = 2000):
    """
    Invoke the LLM safely, infer the context-window size from the model name,
    and truncate the input automatically when it exceeds the limit.
    """
    # Select the model's context-window limit automatically.
    
    system_prompt = system_prompt or ""  # None → ""
    
    model_name = model_config.get("model", "")
    
    if model_name == 'gpt-3.5-turbo':
        max_context_tokens = MODEL_CONTEXT_LIMITS.get(model_name)
        
        
        encoding = tiktoken.encoding_for_model(model_name)

        system_tokens = len(encoding.encode(system_prompt)) if system_prompt else 0
        user_tokens = len(encoding.encode(user_prompt))
        total_tokens = system_tokens + user_tokens
        
        
        if total_tokens > max_context_tokens:
            allowed = max_context_tokens - system_tokens - reserve_tokens
            if allowed <= 0:
                raise ValueError("⚠️ system_prompt fills the entire context window; shorten the prompt.")

            truncated_tokens = encoding.encode(user_prompt)[:allowed]
            user_prompt = encoding.decode(truncated_tokens)
            logger.warning(f"⚠️ Input was too long and was truncated to {allowed} tokens (originally {total_tokens}).")
        
    
    messages = []
    if system_prompt.strip():
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=user_prompt))
    
    return llm.invoke(messages).content
    
    
