# Design: FastAPI Consolidation & Deployment Fix

**Date:** 2026-03-23
**Status:** Approved

## Problem

The app fails to start on Railway with `Error: '$PORT' is not a valid port number`. Additionally, the codebase has grown two parallel implementations — a legacy `JobScraper.py` monolith and a `src/jobscraper/` package — plus two server files (Flask root `server.py` and FastAPI `src/jobscraper/server.py`). This duplication creates confusion, maintenance overhead, and a mismatched `filter_jobs` signature between the two layers.

## Goals

1. Fix the Railway crash immediately.
2. Consolidate to a single clean stack: FastAPI + SQLAlchemy 2.0.
3. Store job results as proper DB rows (not JSON blobs).
4. Remove all legacy/CLI code. Web app only.

## Non-Goals

- CLI interface (dropped by design).
- Switching DB providers (Postgres on Railway, SQLite locally — unchanged).
- Redesigning the frontend (React SPA stays as-is).
- Changing the scraper logic (parser, filters, config.toml rules unchanged).

---

## Architecture

### Files Deleted

| File | Reason |
|------|--------|
| `JobScraper.py` | Legacy monolith; all logic duplicated in `src/jobscraper/` |
| `server.py` (root) | Flask server; replaced by FastAPI |
| `database.py` | Flask-SQLAlchemy models; replaced by `src/jobscraper/db.py` |
| `src/jobscraper/cli.py` | CLI dropped |
| `src/jobscraper/log.py` | Inlined; loguru used directly |
| `src/jobscraper/server.py` | Old FastAPI stub; replaced with full implementation |
| `start.sh` | Replaced by shell-form Docker CMD |

### Files Kept (scraper core, unchanged)

- `src/jobscraper/parser.py`
- `src/jobscraper/scraper.py`
- `src/jobscraper/models.py` — Pydantic `Job` / `FilterStats`
- `src/jobscraper/export.py` — CSV/JSON backup exports
- `src/jobscraper/config.py` + `config.toml` — global filter defaults

### Files Created / Replaced

- `src/jobscraper/db.py` — SQLAlchemy 2.0 async models
- `src/jobscraper/server.py` — New FastAPI app (auth + DB + SSE + static)
- `src/jobscraper/filters.py` — Minor update: accept optional per-user `profile` override
- `requirements.txt` — Updated for FastAPI/uvicorn/asyncpg stack
- `Dockerfile` — Fixed PORT expansion, new CMD

---

## Database Schema

```sql
users
  id            SERIAL PRIMARY KEY
  username      VARCHAR(50) UNIQUE NOT NULL
  password_hash VARCHAR(255) NOT NULL
  created_at    TIMESTAMP DEFAULT now()

profiles
  id                 SERIAL PRIMARY KEY
  user_id            INTEGER UNIQUE FK→users
  education_level    VARCHAR(50)
  min_workload       INTEGER DEFAULT 80
  interests          TEXT  -- JSON array string
  allow_quereinstieg BOOLEAN DEFAULT true

search_history
  id          SERIAL PRIMARY KEY
  user_id     INTEGER FK→users
  location    VARCHAR(100) NOT NULL
  timestamp   TIMESTAMP DEFAULT now()
  total_count INTEGER
  kept_count  INTEGER
  easy_count  INTEGER
  -- results_json REMOVED

jobs                          -- NEW
  id             SERIAL PRIMARY KEY
  search_id      INTEGER FK→search_history
  uuid           VARCHAR(100)
  title          VARCHAR(500)
  company        VARCHAR(200)
  company_clean  VARCHAR(200)
  location       VARCHAR(200)
  workload       VARCHAR(100)
  contract_type  VARCHAR(100)
  published      VARCHAR(100)
  is_promoted    BOOLEAN
  easy_apply     BOOLEAN
  url            TEXT
  category       VARCHAR(50)
```

**Migration:** Tables are recreated on first deploy via `create_all()`. Existing Railway Postgres data (search history + users) is dropped and reseeded. This is acceptable — the seeded `seba` user is recreated automatically.

---

## API Routes

```
POST /api/login                 → {access_token, username}
POST /api/register              → {access_token, username}
GET  /api/me                    → {username, profile}

GET  /api/history               → [{id, location, timestamp, summary}]
GET  /api/history/{id}          → {id, location, timestamp, summary, jobs: [...]}

GET  /scrape?location=&max_pages=&token=   → SSE stream (text/event-stream)

GET  /assets/*                  → static files from frontend/dist/assets/
GET  /*                         → frontend/dist/index.html (SPA catch-all)
```

### SSE Events (unchanged contract, frontend needs no changes)

| Event | Data |
|-------|------|
| `found` | `{total, total_pages, location}` |
| `page` | `{page, total_pages, progress}` |
| `stage` | `{stage, remaining, excluded, progress}` |
| `done` | `{stats, easy_count, search_id}` |
| `error_msg` | `{msg}` |

---

## Server Implementation Details

### Auth
- `python-jose[cryptography]` for JWT signing, `passlib[bcrypt]` for password hashing.
- Tokens passed as `?token=` on `/scrape` (browser `EventSource` cannot set headers).
- Protected routes use a FastAPI `Depends(get_current_user)` dependency.

### Async SSE + Scraper
- `scrape_async()` (already in `src/jobscraper/scraper.py`) runs as an `asyncio` task.
- Progress events flow through an `asyncio.Queue` into the SSE generator.
- A single `asyncio.Lock` prevents concurrent scrapes (same behaviour as current threading lock).
- No more `threading.Thread` + `threading.Lock` — fully async.

### Filter Overrides
`filter_jobs()` gains an optional `profile` parameter:

```python
@dataclass
class FilterProfile:
    min_workload: int | None = None
    include_keywords: list[str] | None = None
    exclude_keywords: list[str] | None = None
    manual_exclude_titles: list[str] | None = None
```

When `None`, each field falls back to the `config.toml` value. This replaces the ad-hoc `profile_dict` in the old Flask server.

### DB Session
- SQLAlchemy 2.0 async engine.
- Local: `aiosqlite` driver (`sqlite+aiosqlite:///./jobscraper.db`).
- Railway: `asyncpg` driver (`DATABASE_URL` env var, `postgres://` → `postgresql+asyncpg://`).
- `AsyncSession` injected via `Depends(get_db)`.

---

## Deployment Fix

**Root cause of crash:** `CMD ["./start.sh"]` uses Docker exec form — no shell is invoked, so `$PORT` in `start.sh` is never expanded by gunicorn.

**Fix:** Use shell form directly in Dockerfile, eliminating `start.sh`:

```dockerfile
CMD ["sh", "-c", "uvicorn src.jobscraper.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

Shell form (`sh -c "..."`) expands `${PORT:-8080}` before uvicorn receives the argument.

### Updated `requirements.txt`

```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
aiosqlite
httpx
beautifulsoup4
lxml
pydantic
python-jose[cryptography]
passlib[bcrypt]
python-dotenv
loguru
jinja2
python-multipart
```

Flask, gunicorn, Flask-JWT-Extended, Flask-SQLAlchemy, requests, tqdm — all removed.

---

## Seeded Data

On startup, if `seba` does not exist in `users`, create:
- User: `seba` / `seba123`
- Profile: EFZ, 80% min workload, interests `[detailhandel, verkauf, lager, gastro]`, allow_quereinstieg=true

---

## Out of Scope

- Profile editing via UI (profile is set at seed time or via direct DB)
- Pagination of `/api/history/{id}` jobs list
- Background job scheduling
- Any frontend changes
