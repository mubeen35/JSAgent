"""
CV matching and scoring using sentence embeddings.

Computes cosine similarity between job requirements and your
skill profile, adds a boost for preferred technologies, and
generates a plain-text feedback summary.
"""

import logging
from typing import Set

from agents.state import AgentState
from embeddings.embedder import compute_similarity
from models.cv_profile import MY_CV
from models.job_schemas import FALLBACK_REQUIREMENTS, JobRequirements

logger = logging.getLogger(__name__)

SCORE_EXCELLENT = 0.75
SCORE_GOOD = 0.55
SCORE_FAIR = 0.35


def _build_job_text(req: JobRequirements) -> str:
    """Turn structured requirements into a string for embedding."""
    tech = ", ".join(req.tech_stack) if req.tech_stack else "general"
    return (
        f"Job role: {req.role_type}. "
        f"Required technologies: {tech}. "
        f"Experience needed: {req.years_experience} years. "
        f"Summary: {req.summary}"
    )


def _skill_overlap(job_tech: list[str], cv_skills: list[str]) -> Set[str]:
    """Find skills that appear in both the job and the CV."""
    job_lower = {s.lower() for s in job_tech}
    cv_lower = {s.lower() for s in cv_skills}
    return job_lower & cv_lower


def _make_feedback(score: float, req: JobRequirements, overlap: Set[str]) -> str:
    """Build a readable feedback string based on score and skill overlap."""
    overlap_str = ", ".join(sorted(overlap)) if overlap else "none detected"
    missing = [t for t in req.tech_stack if t.lower() not in {s.lower() for s in MY_CV.skills}]
    missing_str = ", ".join(missing[:5]) if missing else "none"

    if score >= SCORE_EXCELLENT:
        tier = "Excellent match [***]"
    elif score >= SCORE_GOOD:
        tier = "Good match [**]"
    elif score >= SCORE_FAIR:
        tier = "Partial match [*]"
    else:
        tier = "Low match [ ]"

    yoe_gap = req.years_experience - MY_CV.years_experience
    yoe_note = ""
    if yoe_gap > 0:
        yoe_note = f" Asks for {req.years_experience} YoE (you have {MY_CV.years_experience}, gap: +{yoe_gap})."
    elif yoe_gap < 0:
        yoe_note = f" You exceed the {req.years_experience} YoE requirement by {abs(yoe_gap)} year(s)."

    role_match = req.role_type in MY_CV.role_types
    if role_match:
        role_note = f" Role type '{req.role_type}' fits your profile."
    else:
        role_note = f" Role type '{req.role_type}' is outside your preferences ({', '.join(MY_CV.role_types)})."

    return (
        f"{tier} | Score: {score:.2f} | "
        f"Matching skills: {overlap_str}. "
        f"Skills to develop: {missing_str}.{yoe_note}{role_note}"
    )


def matchmaker_node(state: AgentState) -> AgentState:
    """Score how well a job matches the CV profile using embeddings."""
    job_title = state.get("job_raw", {}).get("title", "Unknown")
    req: JobRequirements = state.get("requirements") or FALLBACK_REQUIREMENTS

    # don't bother scoring if extraction already failed
    if req is FALLBACK_REQUIREMENTS or state.get("error"):
        logger.warning("Skipping scoring for '%s' (upstream error)", job_title)
        return {
            **state,
            "match_score": 0.0,
            "evaluation_feedback": "Skipped -- extraction failed.",
        }

    logger.info("Scoring: '%s'", job_title)

    try:
        job_text = _build_job_text(req)
        cv_text = MY_CV.embed_text

        score = compute_similarity(cv_text, job_text)
        overlap = _skill_overlap(req.tech_stack, MY_CV.skills)

        # boost for preferred stack skills (+2% each, capped at +12%)
        pref_overlap = _skill_overlap(req.tech_stack, MY_CV.preferred_stack)
        boost = min(0.12, len(pref_overlap) * 0.02)
        final_score = round(min(1.0, score + boost), 4)

        feedback = _make_feedback(final_score, req, overlap)

        logger.info(
            "Scored '%s' -> %.3f (boost +%.2f), %d skill(s) overlap",
            job_title, final_score, boost, len(overlap),
        )
        return {**state, "match_score": final_score, "evaluation_feedback": feedback}

    except Exception as exc:
        logger.error("Scoring failed for '%s': %s", job_title, exc)
        return {
            **state,
            "match_score": 0.0,
            "evaluation_feedback": f"Scoring failed: {exc}",
            "error": str(exc),
        }
