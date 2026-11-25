import json

from langchain_core.prompts import PromptTemplate

from HighLevel_Design.prompt import FAILURE_FEEDBACK_INPUT, FAILURE_FEEDBACK_SYSTEM
from utils.config_log import tracer
from utils.model_invoke import invoke_model
from utils.language import language_display, normalize_language


MAX_FAILURE_TRAJECTORY_CHARS = 60_000


def _serialize_failure_trajectory(failure_trajectory: list[dict]) -> str:
    """Serialize a trajectory while keeping the retrospective prompt bounded."""
    trajectory_text = json.dumps(
        failure_trajectory,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    if len(trajectory_text) <= MAX_FAILURE_TRAJECTORY_CHARS:
        return trajectory_text

    half = MAX_FAILURE_TRAJECTORY_CHARS // 2
    return (
        trajectory_text[:half]
        + "\n... [middle of failure trajectory truncated] ...\n"
        + trajectory_text[-half:]
    )


@tracer
def failure_feedback(
    prompt: str,
    requirement: str,
    design: str,
    failure_trajectory: list[dict],
    language: str = "python",
) -> str:
    """Turn one failed round into task-specific lessons for the next design."""
    user_input = PromptTemplate.from_template(FAILURE_FEEDBACK_INPUT).format(
        prompt=prompt,
        analysis=requirement,
        design=design,
        failure_trajectory=_serialize_failure_trajectory(failure_trajectory),
    )
    system_prompt = PromptTemplate.from_template(FAILURE_FEEDBACK_SYSTEM).format(
        lang=language_display(normalize_language(language))
    )
    return invoke_model(system_prompt, user_input)
