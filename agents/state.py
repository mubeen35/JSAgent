"""Shared state that flows through the LangGraph pipeline."""

from typing import Any, Dict, Optional
from typing_extensions import TypedDict

from models.job_schemas import JobRequirements


class AgentState(TypedDict, total=False):
    job_raw: Dict[str, Any]
    skip_pipeline: bool
    filter_reason: str
    requirements: Optional[JobRequirements]
    match_score: float
    evaluation_feedback: str
    error: Optional[str]
