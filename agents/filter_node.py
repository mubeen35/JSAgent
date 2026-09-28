"""
Fast keyword-based pre-filter that runs before the LLM.

Skips jobs that are obviously irrelevant so we don't waste
inference time on them. No LLM calls here, just regex matching.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict

from agents.state import AgentState
from config import settings

logger = logging.getLogger(__name__)

RECENCY_DAYS = 30

# pre-compile patterns with word boundaries so "rag" won't match "management" etc
_POSITIVE_PATTERNS = [
    re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
    for kw in settings.TARGET_KEYWORDS
]
_NEGATIVE_PATTERNS = [
    re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
    for kw in settings.NEGATIVE_KEYWORDS
]


def _title_has_negative(title: str) -> str | None:
    """Check if title contains any disqualifying keyword."""
    for pattern, kw in zip(_NEGATIVE_PATTERNS, settings.NEGATIVE_KEYWORDS):
        if pattern.search(title):
            return kw
    return None


def _has_positive_keyword(title: str, description: str) -> str | None:
    """Find the first matching target keyword in title or description."""
    for pattern, kw in zip(_POSITIVE_PATTERNS, settings.TARGET_KEYWORDS):
        if pattern.search(title):
            return kw
    for pattern, kw in zip(_POSITIVE_PATTERNS, settings.TARGET_KEYWORDS):
        if pattern.search(description):
            return kw
    return None


def _is_stale(job: Dict[str, Any]) -> bool:
    """Check if the job is older than RECENCY_DAYS."""
    if RECENCY_DAYS <= 0:
        return False
    created_at = job.get("created_at")
    if not created_at:
        return False
    try:
        posted = datetime.fromtimestamp(int(created_at), tz=timezone.utc)
        age = (datetime.now(tz=timezone.utc) - posted).days
        return age > RECENCY_DAYS
    except (ValueError, TypeError, OSError):
        return False


def filter_node(state: AgentState) -> AgentState:
    """Pre-filter: skip irrelevant jobs before they hit the LLM."""
    job: Dict[str, Any] = state.get("job_raw", {})
    title = str(job.get("title", ""))
    description = str(job.get("description", ""))
    search_query = job.get("_search_query", "")

    # negative keyword in title -> skip
    neg = _title_has_negative(title)
    if neg:
        reason = f"Filtered -- title has disqualifying keyword: '{neg}'"
        logger.debug("  SKIP '%s' | %s", title[:60], reason)
        return {
            **state,
            "skip_pipeline": True,
            "filter_reason": reason,
            "match_score": 0.0,
            "evaluation_feedback": reason,
        }

    # must have at least one relevant keyword
    pos = _has_positive_keyword(title, description)
    if not pos:
        reason = "Filtered -- no target keywords found"
        logger.debug("  SKIP '%s' | %s", title[:60], reason)
        return {
            **state,
            "skip_pipeline": True,
            "filter_reason": reason,
            "match_score": 0.0,
            "evaluation_feedback": reason,
        }

    # too old?
    if _is_stale(job):
        reason = f"Filtered -- older than {RECENCY_DAYS} days"
        logger.debug("  SKIP '%s' | %s", title[:60], reason)
        return {
            **state,
            "skip_pipeline": True,
            "filter_reason": reason,
            "match_score": 0.0,
            "evaluation_feedback": reason,
        }

    # passed all checks
    logger.info(
        "  PASS '%s' (matched: '%s', query: '%s')",
        title[:60], pos, search_query,
    )
    return {**state, "skip_pipeline": False, "filter_reason": ""}
