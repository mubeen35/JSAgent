"""
Creates the job_postings table. Run once before first pipeline run:

    python db/setup_db.py

Safe to re-run (uses IF NOT EXISTS).
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from db.connection import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS job_postings (
    id                   SERIAL PRIMARY KEY,
    job_id               TEXT UNIQUE NOT NULL,
    title                TEXT,
    company              TEXT,
    location             TEXT,
    remote               BOOLEAN DEFAULT FALSE,
    raw_description      TEXT,
    tech_stack           TEXT[],
    years_experience     INTEGER DEFAULT 0,
    role_type            TEXT,
    match_score          DOUBLE PRECISION DEFAULT 0.0,
    evaluation_feedback  TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_job_postings_match_score
    ON job_postings (match_score DESC);
"""

CREATE_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGER = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'set_updated_at_job_postings'
    ) THEN
        CREATE TRIGGER set_updated_at_job_postings
        BEFORE UPDATE ON job_postings
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END;
$$;
"""


def initialize_schema():
    """Create tables, indexes, and triggers."""
    conn = None
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                logger.info("Creating table: job_postings")
                cur.execute(CREATE_TABLE_SQL)

                logger.info("Creating index on match_score")
                cur.execute(CREATE_INDEX_SQL)

                logger.info("Setting up updated_at trigger")
                cur.execute(CREATE_TRIGGER_FN)
                cur.execute(CREATE_TRIGGER)

        logger.info("Schema ready.")

    except psycopg2.Error as exc:
        logger.error("Schema setup failed: %s", exc)
        sys.exit(1)
    finally:
        if conn and not conn.closed:
            conn.close()


if __name__ == "__main__":
    initialize_schema()
