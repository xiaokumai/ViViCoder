from smolagents import Tool
from utils.local_runner import select_best_gpu
from utils.config_log import config
from HighLevel_Design.retrieval_safety import (
    contains_benchmark_solution_material,
    is_blocked_retrieval_url,
)

strategy = config['strategy']
if strategy == 'ViViCoder' or strategy == 'CoCoST':
    device = select_best_gpu(required_mem_gb=5.0)
    from sentence_transformers import SentenceTransformer

    import numpy as np
    from langchain_core.documents import Document
    model = SentenceTransformer('BAAI/bge-large-en-v1.5', device=device)


class VisitWebpageTool(Tool):
    name = "visit_webpage"
    description = (
        "Visits a webpage at the given url and reads its content as a markdown string. Use this to browse webpages."
    )
    inputs = {
        "url": {
            "type": "string",
            "description": "The url of the webpage to visit.",
        }
    }
    output_type = "string"

    def __init__(self, max_output_length: int = 40000):
        super().__init__()
        self.max_output_length = max_output_length

    def _truncate_content(self, content: str, max_length: int) -> str:
        if len(content) <= max_length:
            return content
        return (
            content[:max_length] + f"\n..._This content has been truncated to stay below {max_length} characters_...\n"
        )

    def forward(self, url: str) -> str:
        try:
            import re

            import requests
            from markdownify import markdownify
            from requests.exceptions import RequestException
        except ImportError as e:
            raise ImportError(
                "You must install packages `markdownify` and `requests` to run this tool: for instance run `pip install markdownify requests`."
            ) from e
        try:
            # Send a GET request to the URL with a 20-second timeout
            response = requests.get(url, timeout=20)
            response.raise_for_status()  # Raise an exception for bad status codes

            # Convert the HTML content to Markdown
            markdown_content = markdownify(response.text).strip()

            # Remove multiple line breaks
            markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)

            return self._truncate_content(markdown_content, self.max_output_length)

        except requests.exceptions.Timeout:
            return "The request timed out. Please try again later or check the URL."
        except RequestException as e:
            return f"Error fetching the webpage: {str(e)}"
        except Exception as e:
            return f"An unexpected error occurred: {str(e)}"


class DuckDuckGoSearchTool(Tool):
    """Web search tool that performs searches using the DuckDuckGo search engine.

    Args:
        max_results (`int`, default `10`): Maximum number of search results to return.
        rate_limit (`float`, default `1.0`): Maximum queries per second. Set to `None` to disable rate limiting.
        **kwargs: Additional keyword arguments for the `DDGS` client.

    Examples:
        ```python
        >>> from smolagents import DuckDuckGoSearchTool
        >>> web_search_tool = DuckDuckGoSearchTool(max_results=5, rate_limit=2.0)
        >>> results = web_search_tool("Hugging Face")
        >>> print(results)
        ```
    """

    name = "web_search"
    description = """Performs a duckduckgo web search based on your query (think a Google search) then returns the top search results."""
    inputs = {"query": {"type": "string", "description": "The search query to perform."}}
    output_type = "string"

    def __init__(self, max_results: int = 10, rate_limit: float | None = 1.0, **kwargs):
        super().__init__()
        self.max_results = max_results
        self.rate_limit = rate_limit
        self._min_interval = 1.0 / rate_limit if rate_limit else 0.0
        self._last_request_time = 0.0

        try:
            from ddgs import DDGS
        except ImportError as e:
            raise ImportError(
                "You must install package `ddgs` to run this tool: for instance run `pip install ddgs`."
            ) from e
        self.ddgs = DDGS(**kwargs)
        

    def forward(self, query: str) -> str:

        self._enforce_rate_limit()

        # --- 1) DuckDuckGo search ---
        results = self.ddgs.text(query, max_results=self.max_results, region='us-en')
        
        # --- Fetch and combine page content, split the text, and write it to the vector store ---
        processed = self.retrieve_body(query, results)

        postprocessed_results = [
            f"[{result.metadata['source']}]({result.metadata['title']})\n{result.page_content}"
            for result in processed
        ]
        return "## Search Results\n\n" + "\n\n".join(postprocessed_results)
    
    def fetch_and_convert_to_markdown(self, url: str) -> str:
        import re
        import requests
        from markdownify import markdownify

        if is_blocked_retrieval_url(url):
            raise ValueError("Blocked a retrieval URL that may expose benchmark material.")

        response = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*"
        })
        response.raise_for_status()

        # Re-check after redirects so an allowed URL cannot redirect to a blocked host.
        if is_blocked_retrieval_url(response.url):
            raise ValueError("Blocked a redirected URL that may expose benchmark material.")


        # markdownify
        markdown_content = markdownify(response.text).strip()

        markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)
        if contains_benchmark_solution_material(markdown_content):
            raise ValueError("Blocked fetched content that may contain benchmark solutions.")
        return markdown_content
    
    def retrieve_body(self, query: str, search_results: list):
        from langchain_core.documents import Document

        docs = []

        # --- 2) Fetch the page and convert it to Markdown ---
        for result in search_results:
            try:
                result_url = result.get('href', '')
                if is_blocked_retrieval_url(result_url):
                    continue

                content = self.fetch_and_convert_to_markdown(result_url)
                docs.append(Document(
                    page_content=content,
                    metadata={
                        "source": result_url,
                        "title": result.get('title', result_url),
                    }
                ))

            except Exception:
                continue

        if not docs:
            return []

        # --- 3) text_split ---
        docs = self.text_split(docs)

        if not docs:
            return []


        # --- 5) similarity_search ---
        results = self.search_top_k(docs, query, k=self.max_results)

        return results

    def search_top_k(self, docs, query, k=5):
        """
        Retrieve LangChain Documents with bge-large-en-v1.5.
        Return the k Documents with the highest relevance scores.
        """

        if not docs:
            return []

        # 1. Initialize the model.

        # 2. Extract the document content.
        passages = [doc.page_content for doc in docs]

        # 3. Generate embeddings.
        instruction = "Represent this sentence for searching relevant passages:"
        q_emb = model.encode([instruction + query], normalize_embeddings=True)
        p_emb = model.encode(passages, normalize_embeddings=True)

        # 4. Compute similarity scores.
        scores = q_emb @ p_emb.T  # shape = (1, N)
        scores = scores[0]

        # 5. Select the k highest-scoring documents.
        top_k_idx = np.argsort(scores)[::-1][:k]

        # 6. Return the selected Documents and their scores.
        results = [docs[i] for i in top_k_idx]
        return results


    
    def text_split(self, docs: list):
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=100, add_start_index=True
        )
        
        all_splits = text_splitter.split_documents(docs)
        return all_splits


    def _enforce_rate_limit(self) -> None:
        import time

        # No rate limit enforced
        if not self.rate_limit:
            return

        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()




from langchain.tools import tool

@tool
def web_search(query: str) -> str:
    """Performs a duckduckgo web search based on your query (think a Google search) then returns the top search results."""
    try:
        web_search_tool = DuckDuckGoSearchTool(max_results=5, rate_limit=2.0)
        results = web_search_tool(query)
        return results
    except Exception as e:
        return f"An error occurred during web search: {str(e)}"
