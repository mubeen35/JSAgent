"""
FastAPI backend for the job search dashboard.

Serves the UI and provides endpoints for fetching/filtering jobs,
viewing stats, and triggering new pipeline runs.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from db.connection import get_connection

app = FastAPI(
    title="Job Search Dashboard API",
    version="1.0.0",
    docs_url="/api/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# simple flag to track if pipeline is running (single-user tool, no need for redis etc)
_pipeline_lock = threading.Lock()
_pipeline_running = False
_pipeline_last_run: Optional[float] = None
_pipeline_last_status = "Never run from dashboard"

UI_PATH = _ROOT / "ui" / "index.html"


@app.on_event("startup")
def _add_url_column():
    """Add url column if it's missing (schema migration)."""
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS url TEXT;")
        conn.close()
    except Exception as exc:
        print(f"[warn] couldn't add url column: {exc}")


@app.get("/", include_in_schema=False)
def serve_ui():
    if not UI_PATH.exists():
        raise HTTPException(404, detail="UI not found")
    return FileResponse(str(UI_PATH), media_type="text/html")


@app.get("/api/stats")
def get_stats() -> Dict[str, Any]:
    """Dashboard header stats."""
    sql = """
        SELECT
            COUNT(*)                                      AS total_jobs,
            ROUND(AVG(match_score)::numeric, 3)           AS avg_score,
            ROUND(MAX(match_score)::numeric, 3)           AS top_score,
            COUNT(*) FILTER (WHERE match_score >= 0.75)   AS excellent,
            COUNT(*) FILTER (WHERE match_score >= 0.55
                               AND match_score < 0.75)    AS good,
            COUNT(*) FILTER (WHERE match_score >= 0.35
                               AND match_score < 0.55)    AS partial,
            COUNT(*) FILTER (WHERE match_score < 0.35)    AS low,
            MAX(updated_at)                               AS last_scan
        FROM job_postings
    """
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            row = dict(cur.fetchone() or {})
        conn.close()
        row["pipeline_running"] = _pipeline_running
        row["pipeline_last_status"] = _pipeline_last_status
        return row
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.get("/api/jobs")
def get_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    role_type: Optional[str] = Query(None),
    remote: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, max_length=100),
    sort_by: str = Query("match_score"),
) -> Dict[str, Any]:
    """Paginated, filterable job listing."""

    ok_sorts = {"match_score", "created_at", "title", "years_experience"}
    if sort_by not in ok_sorts:
        sort_by = "match_score"

    where_parts = ["match_score >= %s"]
    params: List[Any] = [min_score]

    if role_type:
        where_parts.append("role_type = %s")
        params.append(role_type)
    if remote is not None:
        where_parts.append("remote = %s")
        params.append(remote)
    if search:
        where_parts.append("(title ILIKE %s OR company ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = "WHERE " + " AND ".join(where_parts)
    offset = (page - 1) * per_page

    count_sql = f"SELECT COUNT(*) FROM job_postings {where}"
    jobs_sql = f"""
        SELECT id, job_id, title, company, location, remote, role_type,
               tech_stack, years_experience, match_score, evaluation_feedback,
               url, created_at, updated_at
        FROM job_postings {where}
        ORDER BY {sort_by} DESC
        LIMIT %s OFFSET %s
    """

    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()["count"]

            cur.execute(jobs_sql, params + [per_page, offset])
            rows = cur.fetchall()
        conn.close()

        jobs = []
        for row in rows:
            job = dict(row)
            for ts_field in ("created_at", "updated_at"):
                if job.get(ts_field):
                    job[ts_field] = job[ts_field].isoformat()
            jobs.append(job)

        return {"jobs": jobs, "total": total, "page": page, "per_page": per_page}
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))


@app.post("/api/run")
def trigger_pipeline() -> Dict[str, str]:
    """Kick off a pipeline run in the background."""
    global _pipeline_running, _pipeline_last_status

    with _pipeline_lock:
        if _pipeline_running:
            return {"status": "already_running", "message": "Pipeline is already running."}
        _pipeline_running = True
        _pipeline_last_status = "Running..."

    def _run():
        global _pipeline_running, _pipeline_last_run, _pipeline_last_status
        try:
            python = str(_ROOT / "venv" / "Scripts" / "python.exe")
            result = subprocess.run(
                [python, str(_ROOT / "main.py")],
                cwd=str(_ROOT),
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                _pipeline_last_status = "Completed successfully"
            else:
                _pipeline_last_status = f"Failed (exit {result.returncode})"
        except subprocess.TimeoutExpired:
            _pipeline_last_status = "Timed out (10 min limit)"
        except Exception as exc:
            _pipeline_last_status = f"Error: {exc}"
        finally:
            _pipeline_running = False
            _pipeline_last_run = time.time()

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started", "message": "Pipeline started."}


@app.get("/api/run/status")
def pipeline_status() -> Dict[str, Any]:
    return {
        "running": _pipeline_running,
        "last_status": _pipeline_last_status,
        "last_run": _pipeline_last_run,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)
