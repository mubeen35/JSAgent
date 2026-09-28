"""Pydantic models for structured LLM output."""

from typing import List, Literal

from pydantic import BaseModel, Field, field_validator


RoleType = Literal["backend", "frontend", "fullstack", "devops", "ml", "data", "other"]


class JobRequirements(BaseModel):
    """What we extract from a job posting via the LLM."""

    tech_stack: List[str] = Field(
        default_factory=list,
        description="Technologies, frameworks, and tools required.",
        max_length=20,
    )
    years_experience: int = Field(
        default=0, ge=0, le=30,
        description="Min years of experience (0 if not mentioned).",
    )
    role_type: RoleType = Field(
        default="other",
        description="Primary role category.",
    )
    summary: str = Field(
        default="", max_length=500,
        description="One-sentence role summary.",
    )

    @field_validator("tech_stack", mode="before")
    @classmethod
    def _clean_tech_stack(cls, v):
        if not isinstance(v, list):
            return []
        return [str(item).strip() for item in v if str(item).strip()][:20]

    @field_validator("summary", mode="before")
    @classmethod
    def _truncate_summary(cls, v):
        return str(v)[:500] if v else ""


# used when the LLM gives us something unparseable
FALLBACK_REQUIREMENTS = JobRequirements(
    tech_stack=[],
    years_experience=0,
    role_type="other",
    summary="Extraction failed",
)
