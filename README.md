# Job Search AI Agent

A local, privacy-focused multi-agent system that finds relevant jobs and ranks them against your skill profile.

## What it does

Pulls job postings from Arbeitnow and Remotive, extracts requirements using a local LLM (Ollama), computes a semantic match score against your CV profile using sentence embeddings, and stores everything in PostgreSQL.

## Stack

- **LangGraph** for agent orchestration
- **Ollama** running a local LLM (no cloud API calls)
- **sentence-transformers** for semantic matching
- **PostgreSQL** for persistence
- **FastAPI** for the dashboard API

## How it works

```
Job APIs → fetcher.py → filter_node → extractor_node → matchmaker_node → PostgreSQL
                        (keywords)     (LLM)           (embeddings)
```

## Project layout

```
JobSearchAgent/
├── config/settings.py        # reads .env, exposes config
├── db/
│   ├── connection.py         # pg connection factory
│   └── setup_db.py           # creates tables (run once)
├── models/
│   ├── job_schemas.py        # pydantic models for LLM output
│   └── cv_profile.py         # your skills profile (no PII)
├── ingestion/fetcher.py      # pulls jobs from APIs
├── embeddings/embedder.py    # sentence-transformer wrapper
├── agents/
│   ├── state.py              # shared state dict
│   ├── filter_node.py        # keyword pre-filter (no LLM)
│   ├── extractor_node.py     # structured extraction via LLM
│   └── matchmaker_node.py    # semantic CV matching
├── pipeline/workflow.py      # LangGraph graph definition
├── api/server.py             # FastAPI dashboard backend
├── ui/index.html             # dashboard frontend
├── main.py                   # CLI entry point
└── requirements.txt
```

## Getting started

### Prerequisites
- Python 3.10+
- PostgreSQL on `localhost:5432`
- Ollama running (`ollama serve`)

### Setup
```bash
pip install -r requirements.txt
copy .env.example .env        # then edit DB_PASSWORD
python db/setup_db.py         # create tables
```

### Edit your profile
Open `models/cv_profile.py` and update the skills list. Only put technical skills — no personal info needed.

### Run it
```bash
python main.py
```

### Check results
```sql
SELECT title, match_score, evaluation_feedback
FROM job_postings
ORDER BY match_score DESC
LIMIT 10;
```

### Dashboard
```bash
python -m api.server
# open http://localhost:8000
```

## Configuration

Everything is in `.env`:
- `OLLAMA_MODEL` — which local model to use
- `SEARCH_QUERIES` — comma-separated job search terms
- `TARGET_KEYWORDS` — jobs must mention at least one
- `NEGATIVE_KEYWORDS` — jobs with these in the title get skipped
- `MAX_JOBS_PER_RUN` — cap on total jobs fetched
