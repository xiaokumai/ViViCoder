"""Shared language selection helpers for ViViCoder and benchmark execution."""

from __future__ import annotations

from utils.config_log import config


SUPPORTED_LANGUAGES = {"python", "cpp", "java"}
_ALIASES = {
    "py": "python",
    "python3": "python",
    "c++": "cpp",
    "cplusplus": "cpp",
    "cpp": "cpp",
    "java": "java",
}
_DISPLAY_NAMES = {"python": "Python", "cpp": "C++", "java": "Java"}


def normalize_language(value: str | None) -> str:
    """Return the Sandbox Fusion language identifier for a supported language."""
    normalized = _ALIASES.get(str(value or "python").strip().lower(), str(value or "python").strip().lower())
    if normalized not in SUPPORTED_LANGUAGES:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
        raise ValueError(f"Unsupported ViViCoder language {value!r}; expected one of: {supported}")
    return normalized


def language_from_dataset(dataset_name: str | None) -> str | None:
    name = str(dataset_name or "").strip().lower()
    if name == "contests_cpp":
        return "cpp"
    if name == "contests_java":
        return "java"
    if name in {"contests_python", "codecontests"}:
        return "python"
    return None


def get_language(
    question: dict | None = None,
    data_config: dict | None = None,
    dataset_name: str | None = None,
) -> str:
    """Resolve language without relying solely on mutable global configuration."""
    question = question or {}
    data_config = data_config or {}
    dataset_name = (
        dataset_name
        or question.get("dataset_name")
        or config.get("dataset", {}).get("name")
    )
    candidate = (
        question.get("language")
        or data_config.get("language")
        or language_from_dataset(dataset_name)
        or config.get("language", "python")
    )
    return normalize_language(candidate)


def language_display(language: str) -> str:
    return _DISPLAY_NAMES[normalize_language(language)]


def language_fence(language: str) -> str:
    return normalize_language(language)


def uses_standard_input(question: dict | None = None) -> bool:
    question = question or {}
    dataset_name = str(
        question.get("dataset_name")
        or config.get("dataset", {}).get("name", "")
    ).lower()
    if dataset_name in {"codecontests", "contests_python", "contests_cpp", "contests_java"}:
        return True
    return dataset_name == "livecodebench" and question.get("platform") == "atcoder"


def sample_stdin(sample: dict) -> str:
    value = sample.get("input", "")
    if isinstance(value, dict):
        return str(value.get("stdin", ""))
    return str(value)


def sample_stdout(sample: dict) -> str:
    value = sample.get("output", "")
    if isinstance(value, dict):
        return str(value.get("stdout", ""))
    return str(value)
