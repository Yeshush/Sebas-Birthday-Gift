# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JobScraper is a FastAPI web application that scrapes jobs from [jobs.ch](https://www.jobs.ch) (a Swiss job board). Users log in, trigger scrapes by location, and browse filtered results stored in a database.

## Running the Application

### Web server (local)

```bash
source .venv/bin/activate
pip install -e .
uvicorn jobscraper.server:app --reload --port 5001
# → http://localhost:5001
```

### Tests

```bash
source .venv/bin/activate
pytest tests/ -v
# Single test:
pytest tests/test_filters.py::test_filter_profile_defaults -v
```

## Architecture

### Two-layer structure

| Layer | Files | Role |
|-------|-------|------|
| Scraper | `src/jobscraper/scraper.py`, `src/jobscraper/parser.py` | Fetches and parses jobs.ch HTML |
| Filter | `src/jobscraper/filters.py` | 4-stage pipeline (workload → exclude → include → dedup) |
| Models | `src/jobscraper/models.py` | Pydantic `Job` / `FilterStats` |
| DB | `src/jobscraper/db.py` | SQLAlchemy 2.0 async models (UserRow, ProfileRow, SearchHistoryRow, JobRow) |
| Server | `src/jobscraper/server.py` | FastAPI app: auth, history API, SSE scrape endpoint, static SPA serving |
| Config | `src/jobscraper/config.py` + `config.toml` | Global filter defaults (keywords, min workload) |
| Frontend | `frontend/src/` | React SPA (Vite build → `frontend/dist/`) |

### Key implementation notes

- **Deployment:** Dockerfile uses `CMD ["sh", "-c", "uvicorn jobscraper.server:app --host 0.0.0.0 --port ${PORT:-8080}"]` — the `sh -c` form expands `$PORT` before uvicorn receives it (fixes Railway deployment crash).
- **Database:** Postgres on Railway (`DATABASE_URL` env var), SQLite locally (default `sqlite+aiosqlite:///./jobscraper.db`).
- **Auth:** JWT HS256, 7-day expiry. `JWT_SECRET_KEY` env var required in production.
- **SSE scrape:** `/scrape?location=&token=` — token in query param because `EventSource` cannot set headers.
- **FilterProfile:** `filter_jobs()` accepts an optional `FilterProfile` dataclass as its 4th positional argument. `None` fields fall back to `config.toml` defaults. Pass with `run_in_executor` as: `await loop.run_in_executor(None, filter_jobs, raw_jobs, False, None, profile)`.
- **Frontend field mapping:** API serializes `url → link` and `published → date` to match `Dashboard.jsx`.
- **Seeded user:** `seba` / `seba123` (EFZ profile) is seeded on first startup.
