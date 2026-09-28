"""
Entry point for the job search pipeline.

Fetches job postings, runs them through the LangGraph workflow,
and saves results to PostgreSQL.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# windows console chokes on unicode without this
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

import psycopg2

from agents.state import AgentState
from config import settings
from db.connection import get_connection
from ingestion.fetcher import fetch_jobs
from models.job_schemas import JobRequirements
from pipeline.workflow import run_pipeline


_UPSERT_SQL = """
INSERT INTO job_postings (
    job_id, title, company, location, remote,
    raw_description, tech_stack, years_experience,
    role_type, match_score, evaluation_feedback
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (job_id) DO UPDATE SET
    title                = EXCLUDED.title,
    company              = EXCLUDED.company,
    location             = EXCLUDED.location,
    remote               = EXCLUDED.remote,
    raw_description      = EXCLUDED.raw_description,
    tech_stack           = EXCLUDED.tech_stack,
    years_experience     = EXCLUDED.years_experience,
    role_type            = EXCLUDED.role_type,
    match_score          = EXCLUDED.match_score,
    evaluation_feedback  = EXCLUDED.evaluation_feedback,
    updated_at           = NOW();
"""


def _persist_result(conn, job: Dict[str, Any], state: AgentState) -> None:
    """Save a single pipeline result to the database."""
    req: Optional[JobRequirements] = state.get("requirements")

    job_id = str(job.get("slug") or job.get("id") or "unknown")[:255]
    title = str(job.get("title") or "")[:500]
    company = str(job.get("company_name") or "")[:255]
    location = str(job.get("location") or "")[:255]
    remote = bool(job.get("remote", False))
    raw_description = str(job.get("description") or "")[:10_000]

    tech_stack: List[str] = req.tech_stack if req else []
    years_experience: int = req.years_experience if req else 0
    role_type: str = req.role_type if req else "other"

    match_score: float = float(state.get("match_score") or 0.0)
    evaluation_feedback: str = str(state.get("evaluation_feedback") or "")[:1000]

    params = (
        job_id, title, company, location, remote,
        raw_description, tech_stack, years_experience,
        role_type, match_score, evaluation_feedback,
    )

    with conn.cursor() as cur:
        cur.execute(_UPSERT_SQL, params)


def main() -> None:
    logger.info("=" * 60)
    logger.info("Job Search Agent -- starting up")
    logger.info("Model  : %s @ %s", settings.OLLAMA_MODEL, settings.OLLAMA_BASE_URL)
    logger.info("DB     : %s:%s/%s", settings.DB_HOST, settings.DB_PORT, settings.DB_NAME)
    logger.info("Source : Arbeitnow + Remotive")
    logger.info("=" * 60)

    # fetch jobs
    logger.info("Step 1/3 -- Fetching job postings")
    logger.info("Search queries: %s", settings.SEARCH_QUERIES)
    jobs = fetch_jobs()
    if not jobs:
        logger.warning("No jobs fetched, nothing to do.")
        return
    logger.info("Got %d unique job(s).", len(jobs))

    # db connection
    try:
        conn = get_connection()
    except psycopg2.OperationalError:
        logger.error("Can't connect to PostgreSQL. Check .env and make sure the DB is running.")
        sys.exit(1)

    # process each job through the pipeline
    logger.info("Step 2/3 -- Processing %d job(s)", len(jobs))
    results: List[Dict[str, Any]] = []
    passed = 0
    skipped = 0

    for idx, job in enumerate(jobs, start=1):
        job_title = job.get("title", "Unknown")
        logger.info("[%d/%d] %s", idx, len(jobs), job_title)

        try:
            state = run_pipeline({"job_raw": job})
            results.append({"job": job, "state": state})

            if state.get("skip_pipeline"):
                skipped += 1
                continue

            passed += 1
            _persist_result(conn, job, state)
            conn.commit()

        except Exception as exc:
            logger.error("Failed on '%s': %s", job_title, exc)
            conn.rollback()
            continue

    conn.close()

    # print results
    logger.info("Step 3/3 -- Results")
    logger.info("%d passed, %d filtered out", passed, skipped)
    logger.info("=" * 60)

    relevant = [r for r in results if not r["state"].get("skip_pipeline")]
    ranked = sorted(relevant, key=lambda r: r["state"].get("match_score", 0.0), reverse=True)

    print(f"\n{'=' * 70}")
    print(f"{'RANK':<5} {'SCORE':<7} {'TITLE':<45} {'ROLE':<12}")
    print("-" * 70)

    for rank, item in enumerate(ranked, start=1):
        state = item["state"]
        job = item["job"]
        req: Optional[JobRequirements] = state.get("requirements")
        score = state.get("match_score", 0.0)
        title = str(job.get("title", ""))[:44]
        role = req.role_type if req else "other"
        query = job.get("_search_query", "")[:20]

        print(f"{rank:<5} {score:<7.3f} {title:<45} {role:<12}")
        if rank <= 5:
            print(f"       >> {state.get('evaluation_feedback', '')[:120]}")
            if query:
                print(f"       [query] Found via: '{query}'")

    print("=" * 70)
    print(
        f"\nDone -- {passed} relevant jobs scored & stored "
        f"({skipped} filtered out)."
    )
    print(
        "   Check results:\n"
        "   SELECT title, match_score, evaluation_feedback\n"
        "   FROM job_postings ORDER BY match_score DESC LIMIT 10;"
    )


if __name__ == "__main__":
    main()
