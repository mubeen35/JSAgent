"""Central config. Reads everything from .env so nothing is hardcoded."""

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)

# postgres
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "ai_job_hunter")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")

# embeddings
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

# ingestion
_raw_hosts = os.getenv("ALLOWED_HOSTS", "www.arbeitnow.com")
ALLOWED_HOSTS: frozenset[str] = frozenset(
    h.strip() for h in _raw_hosts.split(",") if h.strip()
)

MAX_JOBS_PER_RUN = int(os.getenv("MAX_JOBS_PER_RUN", "50"))

# search config
_raw_queries = os.getenv(
    "SEARCH_QUERIES",
    "react frontend engineer,AI engineer LLM,python fastapi backend,frontend typescript next.js",
)
SEARCH_QUERIES = [q.strip() for q in _raw_queries.split(",") if q.strip()]

MAX_PAGES_PER_QUERY = int(os.getenv("MAX_PAGES_PER_QUERY", "2"))

# filter keywords
_raw_target = os.getenv(
    "TARGET_KEYWORDS",
    "react,typescript,next.js,frontend,ai engineer,llm,langchain,langgraph,"
    "machine learning,python,fastapi,full stack,fullstack,nlp,rag,"
    "large language model,multiagent,multi-agent,data science,deep learning,"
    "node.js,redux,javascript engineer,software engineer",
)
TARGET_KEYWORDS = [k.strip().lower() for k in _raw_target.split(",") if k.strip()]

_raw_negative = os.getenv(
    "NEGATIVE_KEYWORDS",
    "sales,account executive,marketing,recruiter,hr manager,"
    "vfx artist,graphic designer,copywriter,operations manager,"
    "finance,accounting,legal,customer success,"
    "werkstudent,praktikant",
)
NEGATIVE_KEYWORDS = [k.strip().lower() for k in _raw_negative.split(",") if k.strip()]

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
