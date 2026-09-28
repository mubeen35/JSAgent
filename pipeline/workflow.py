"""
LangGraph workflow definition.

    filter_node -> (relevant?) -> extractor_node -> matchmaker_node -> END
                   (irrelevant) -> END

Irrelevant jobs skip the LLM entirely.
"""

import logging
from typing import Any, Dict, Literal

from langgraph.graph import END, START, StateGraph

from agents.extractor_node import extractor_node
from agents.filter_node import filter_node
from agents.matchmaker_node import matchmaker_node
from agents.state import AgentState

logger = logging.getLogger(__name__)


def _route_after_filter(state: AgentState) -> Literal["extractor", "__end__"]:
    if state.get("skip_pipeline", False):
        return END
    return "extractor"


# build graph once at import
_builder = StateGraph(AgentState)

_builder.add_node("filter",     filter_node)
_builder.add_node("extractor",  extractor_node)
_builder.add_node("matchmaker", matchmaker_node)

_builder.add_edge(START, "filter")
_builder.add_conditional_edges(
    "filter",
    _route_after_filter,
    {"extractor": "extractor", END: END},
)
_builder.add_edge("extractor",  "matchmaker")
_builder.add_edge("matchmaker", END)

_workflow = _builder.compile()


def run_pipeline(initial_state: Dict[str, Any]) -> AgentState:
    """Run the full pipeline for one job posting. Returns final state."""
    job_title = initial_state.get("job_raw", {}).get("title", "Unknown")
    logger.debug("Starting pipeline for: '%s'", job_title)

    result: AgentState = _workflow.invoke(initial_state)

    logger.debug(
        "Done with '%s' -- %s, score=%.3f",
        job_title,
        "SKIPPED" if result.get("skip_pipeline") else "OK",
        result.get("match_score", 0.0),
    )
    return result
