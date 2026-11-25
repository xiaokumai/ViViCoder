import logging
from copy import deepcopy

import litellm
import openai
from aiolimiter import AsyncLimiter
from litellm import acompletion
from litellm import embedding
from litellm import RateLimitError
from litellm.exceptions import APIError
from retry import retry

from settings.config_loader import get_settings
from log import get_logger

logger = get_logger(__name__)
OPENAI_RETRIES = 5


class AiHandler:
    """
    This class handles interactions with the OpenAI API for chat completions.
    It initializes the API key and other settings from a configuration file,
    and provides a method for performing chat completions using the OpenAI ChatCompletion API.
    """

    def __init__(self):
        """
        Initializes the OpenAI API key and other settings from a configuration file.
        Raises a ValueError if the OpenAI key is missing.
        """
        settings = get_settings()
        self.limiter = AsyncLimiter(settings.config.max_requests_per_minute)
        self.reset_stats()
        try:
            if "gpt" in settings.get("config.model").lower() or \
                "text" in settings.get("config.embedding_model").lower():
                openai.api_key = settings.openai.key
                litellm.openai_key = settings.openai.key
                base_url = settings.get("openai.base_url", None)
                if base_url:
                    openai.base_url = base_url
                    litellm.api_base = base_url
        except AttributeError as e:
            raise ValueError("OpenAI key is required") from e

    def _get_completion_api_key(self):
        return get_settings().get("openai.key")

    def _get_embedding_api_key(self):
        return get_settings().get("openai.embedding_key", self._get_completion_api_key())

    def _get_api_base(self):
        return get_settings().get("openai.base_url", None)

    def _get_provider_model_name(self, model: str) -> str:
        for prefix in ("openai/", "custom_openai/"):
            if model.startswith(prefix):
                return model.split("/", 1)[1]
        return model

    def _normalize_content_blocks(self, content):
        if isinstance(content, str):
            return content
        if content is None:
            return ""
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                    continue
                if not isinstance(block, dict):
                    parts.append(str(block))
                    continue
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(text, dict):
                    value = text.get("value") or text.get("content")
                    if isinstance(value, str):
                        parts.append(value)
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
            return "".join(parts)
        return str(content)

    def _normalize_openai_compatible_response(self, response: dict) -> dict:
        normalized = deepcopy(response)
        choices = normalized.get("choices", []) or []
        for choice in choices:
            message = choice.get("message", {}) or {}
            message["content"] = self._normalize_content_blocks(message.get("content"))
            choice["message"] = message
        normalized["choices"] = choices
        return normalized

    def _should_fallback_to_raw_openai(self, model: str, error: Exception) -> bool:
        if not model.startswith(("openai/", "custom_openai/")):
            return False
        message = str(error)
        return "Invalid response object" in message and "Input should be a valid string" in message

    async def _chat_completion_raw_openai(self, completion_kwargs: dict) -> dict:
        client = openai.AsyncOpenAI(
            api_key=self._get_completion_api_key(),
            base_url=self._get_api_base(),
            timeout=get_settings().config.ai_timeout,
        )
        try:
            raw_response = await client.chat.completions.with_raw_response.create(
                model=self._get_provider_model_name(completion_kwargs["model"]),
                messages=completion_kwargs["messages"],
                temperature=completion_kwargs["temperature"],
                frequency_penalty=completion_kwargs["frequency_penalty"],
                n=completion_kwargs["n"],
                top_p=completion_kwargs["top_p"],
                extra_body=completion_kwargs.get("extra_body"),
                timeout=get_settings().config.ai_timeout,
            )
            if hasattr(raw_response, "http_response") and raw_response.http_response is not None:
                response = raw_response.http_response.json()
            else:
                response = raw_response.parse(to=dict)
            return self._normalize_openai_compatible_response(response)
        finally:
            await client.close()

    async def _request_chat_completion(self, completion_kwargs: dict) -> dict:
        try:
            return await acompletion(**completion_kwargs)
        except Exception as e:
            if not self._should_fallback_to_raw_openai(completion_kwargs["model"], e):
                raise
            logger.warning(
                "Falling back to raw OpenAI-compatible response handling for model %s due to content block format",
                completion_kwargs["model"],
            )
            return await self._chat_completion_raw_openai(completion_kwargs)

    def reset_stats(self):
        self._stats = {
            "api_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_cost": 0.0,
        }

    def get_stats(self):
        return dict(self._stats)

    def _update_stats(self, response, model: str):
        self._stats["api_calls"] += 1
        usage = {}
        if isinstance(response, dict):
            usage = response.get("usage", {}) or {}
        else:
            usage = getattr(response, "usage", {}) or {}
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or 0
        total_cost = 0.0
        if isinstance(response, dict):
            total_cost = response.get("cost", None)
        if total_cost is None:
            try:
                total_cost = litellm.cost_calculator(
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            except Exception:
                total_cost = 0.0
        self._stats["prompt_tokens"] += int(prompt_tokens)
        self._stats["completion_tokens"] += int(completion_tokens)
        try:
            self._stats["total_cost"] += float(total_cost or 0.0)
        except (TypeError, ValueError):
            pass


    @retry(
        exceptions=(AttributeError, RateLimitError),
        tries=OPENAI_RETRIES,
        delay=2,
        backoff=2,
        jitter=(1, 3),
    )
    async def chat_completion(
            self, model: str,
            system: str,
            user: str,
            temperature: float = 0.2,
            frequency_penalty: float = 0.0,
            n: int = 1,
            top_p: float = 1.0
    ):
        try:
            if get_settings().config.verbosity_level >= 2:
                logging.debug(
                    f"Generating completion with {model}"
                )
            extra_body = get_settings().config.get("extra_body", None)
            completion_kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "frequency_penalty": frequency_penalty,
                "n": n,
                "top_p": top_p,
                "force_timeout": get_settings().config.ai_timeout,
                "api_key": self._get_completion_api_key(),
            }
            api_base = self._get_api_base()
            if api_base:
                completion_kwargs["api_base"] = api_base
            if extra_body is not None:
                completion_kwargs["extra_body"] = dict(extra_body)

            async with self.limiter:
                logger.info("-----------------")
                logger.info("Running inference ...")
                logger.debug(f"system:\n{system}")
                logger.debug(f"user:\n{user}")
                response = await self._request_chat_completion(completion_kwargs)
        except (APIError) as e:
            logging.error("Error during OpenAI inference")
            raise
        except RateLimitError as e:
            logging.error("Rate limit error during OpenAI inference")
            raise
        except Exception as e:
            logging.exception("Unknown error during OpenAI inference: %s", e)
            raise
        if response is None or len(response["choices"]) == 0:
            raise RuntimeError("Empty response returned from LLM")
        self._update_stats(response, model=model)
        
        if len(response["choices"]) == 1:
            resp = response["choices"][0]["message"]["content"]
            finish_reason = response["choices"][0]["finish_reason"]
        else:
            resp = [choice["message"]["content"] for choice in response["choices"]]
            finish_reason = [choice["finish_reason"] for choice in response["choices"]]
        logger.debug(f"response:\n{resp}")
        logger.info('done')
        logger.info("-----------------")
        return resp, finish_reason

    def text_embedding(
            self, model: str,
            texts: list[str],
    ):
        logger.info("-----------------")
        logger.info(f"Generating embeddings with {model}")
        try:
            embedding_kwargs = {
                "model": model,
                "input": texts,
                "api_key": self._get_embedding_api_key(),
            }
            api_base = self._get_api_base()
            if api_base:
                embedding_kwargs["api_base"] = api_base
            embeddings = embedding(**embedding_kwargs)
        except (APIError) as e:
            logging.error("Error during OpenAI inference")
            raise
        except RateLimitError as e:
            logging.error("Rate limit error during OpenAI inference")
            raise
        except Exception as e:
            logging.exception("Unknown error during OpenAI embedding inference: %s", e)
            raise
        if embeddings is None or len(embeddings["data"]) == 0:
            raise RuntimeError("Empty embedding response returned from LLM")
        logger.info('done')
        logger.info("-----------------")
        return embeddings
    
if __name__ == '__main__':
    def dict_to_string(solution_dict):
        string = ""
        for key, value in solution_dict.items():
            if isinstance(value, list):
                value = ', '.join(value)
            string += f"{key}: {value}\n"
        return string
    import json
    from sklearn.cluster import KMeans
    import numpy as np
    with open('bbbbb.json', 'r') as f:
        data = json.load(f)
    
    str_list = [dict_to_string(solution_dict) for solution_dict in data]
    ai_handler = AiHandler()
    model = get_settings().config.embedding_model
    num_clusters = get_settings().possible_solutions.num_clusters
    response = ai_handler.text_embedding(
        model = model, 
        texts = str_list
    )
    embeddings = [e['embedding'] for e in response['data']]
    embeddings = np.array(embeddings)
    kmeans = KMeans(n_clusters=num_clusters)
    kmeans.fit(embeddings)
    cluster_centers = kmeans.cluster_centers_ 
    labels = kmeans.labels_ 
    representative_examples = []
    representative_indices = []
    for cluster_id in range(num_clusters):
        cluster_embeddings = embeddings[labels == cluster_id]
        cluster_texts = [str_list[i] for i, label in enumerate(labels) if label == cluster_id]
        distances = [np.linalg.norm(embedding - cluster_centers[cluster_id]) for embedding in cluster_embeddings]
        representative_index = np.argmin(distances)
        representative_example = cluster_texts[representative_index]
        representative_examples.append(representative_example)
        original_index = [i for i, label in enumerate(labels) if label == cluster_id][representative_index]
        representative_indices.append(original_index)
