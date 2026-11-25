"""Public CodeContests examples extracted from the bundled Contest variant."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_public_cases() -> dict[str, list[dict]]:
    repository_root = Path(__file__).resolve().parents[1]
    candidates = (
        repository_root / "benchmark" / "CodeContests" / "cases.json",
        repository_root / "Contest" / "benchmark" / "CodeContests" / "cases.json",
    )
    cases_path = next((path for path in candidates if path.is_file()), None)
    if cases_path is None:
        searched = ", ".join(str(path) for path in candidates)
        raise FileNotFoundError(f"CodeContests public cases were not found; searched: {searched}")

    with cases_path.open("r", encoding="utf-8") as handle:
        entries = json.load(handle)
    return {entry["id"]: entry.get("extracted_cases", []) for entry in entries}


def get_public_cases(question_id: str) -> list[dict]:
    return load_public_cases().get(question_id, [])
