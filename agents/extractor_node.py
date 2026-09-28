"""
Structured extraction from job descriptions using a local LLM.

Calls Ollama, parses the response into a JobRequirements pydantic model,
and falls back gracefully if the LLM returns garbage.
"""

import json
import logging
from typing import Any, Dict

from langchain_ollama import ChatOllama
from pydantic import ValidationError

from agents.state import AgentState
from config import settings
from models.job_schemas import FALLBACK_REQUIREMENTS, JobRequirements

logger = logging.getLogger(__name__)

_llm = ChatOllama(
    model=settings.OLLAMA_MODEL,
    base_url=settings.OLLAMA_BASE_URL,
    temperature=0,
    format="json",
    num_predict=512,
)

_structured_llm = _llm.with_structured_output(JobRequirements, include_raw=True)

_EXTRACTION_PROMPT = """\
You are a precise job requirements extractor.
Extract structured information from the job posting below.

Return ONLY valid JSON matching this schema:
{{
  "tech_stack": ["list", "of", "technologies"],
  "years_experience": <integer, 0 if not specified>,
  "role_type": "<one of: backend, frontend, fullstack, devops, ml, data, other>",
  "summary": "<one sentence describing the role, max 100 words>"
}}

JOB TITLE: {title}
JOB DESCRIPTION:
{description}
"""


def _build_prompt(job: Dict[str, Any]) -> str:
    title = str(job.get("title", "Unknown Title"))[:200]
    desc = str(job.get("description", ""))[:3000]
    return _EXTRACTION_PROMPT.format(title=title, description=desc)


def extractor_node(state: AgentState) -> AgentState:
    """Extract structured job requirements via local LLM. Falls back on any error."""
    job = state.get("job_raw", {})
    job_title = job.get("title", "Unknown")

    logger.info("Extracting: '%s'", job_title)

    try:
        prompt = _build_prompt(job)
        result = _structured_llm.invoke(prompt)

        parsed: JobRequirements | None = result.get("parsed")
        parsing_error = result.get("parsing_error")

        if parsing_error:
            logger.warning("Parse error for '%s': %s", job_title, parsing_error)
            return {
                **state,
                "requirements": FALLBACK_REQUIREMENTS,
                "error": f"Parsing error: {parsing_error}",
            }

        if not isinstance(parsed, JobRequirements):
            logger.warning("Unexpected type for '%s': %s", job_title, type(parsed))
            return {
                **state,
                "requirements": FALLBACK_REQUIREMENTS,
                "error": "Unexpected parsed output type.",
            }

        logger.info(
            "Extracted '%s' -> role=%s, tech=%s, yoe=%d",
            job_title, parsed.role_type, parsed.tech_stack[:3], parsed.years_experience,
        )
        return {**state, "requirements": parsed, "error": None}

    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Bad LLM output for '%s': %s", job_title, exc)
        return {**state, "requirements": FALLBACK_REQUIREMENTS, "error": str(exc)}
    except Exception as exc:
        logger.error("LLM call failed for '%s': %s", job_title, exc)
        return {**state, "requirements": FALLBACK_REQUIREMENTS, "error": f"LLM error: {exc}"}
