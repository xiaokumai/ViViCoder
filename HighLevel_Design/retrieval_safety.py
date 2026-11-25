"""Filters that keep benchmark material out of ViViCoder's web retrieval."""

from urllib.parse import unquote, urlparse


BLOCKED_CODE_HOSTING_DOMAINS = frozenset(
    {
        "bitbucket.org",
        "gitee.com",
        "github.com",
        "github.io",
        "githubusercontent.com",
        "gitlab.com",
        "hf.co",
        "huggingface.co",
    }
)

BENCHMARK_MARKERS = frozenset(
    {
        "codecontests",
        "code_contests",
        "evo code bench",
        "evocodebench",
        "human eval",
        "human-eval",
        "humaneval",
        "live code bench",
        "live-code-bench",
        "livecodebench",
        "mbpp",
        "mhpp",
        "openai_humaneval",
    }
)

SOLUTION_MARKERS = frozenset(
    {
        "answer key",
        "canonical solution",
        "code solution",
        "official solution",
        "reference answer",
        "reference solution",
        "solutions.json",
        "solutions.jsonl",
    }
)


def _domain_matches(hostname: str, blocked_domain: str) -> bool:
    return hostname == blocked_domain or hostname.endswith(f".{blocked_domain}")


def is_blocked_retrieval_url(url: str) -> bool:
    """Return True for code-hosting and benchmark-specific result URLs."""
    if not isinstance(url, str) or not url.strip():
        return True

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        return True

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        return True

    if any(
        _domain_matches(hostname, blocked_domain)
        for blocked_domain in BLOCKED_CODE_HOSTING_DOMAINS
    ):
        return True

    normalized_url = unquote(url).lower()
    return any(marker in normalized_url for marker in BENCHMARK_MARKERS)


def contains_benchmark_solution_material(content: str) -> bool:
    """Detect fetched pages that combine benchmark and solution indicators."""
    if not isinstance(content, str):
        return False

    normalized_content = content.lower()
    mentions_benchmark = any(
        marker in normalized_content for marker in BENCHMARK_MARKERS
    )
    mentions_solution = any(
        marker in normalized_content for marker in SOLUTION_MARKERS
    )
    return mentions_benchmark and mentions_solution
