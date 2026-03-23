# Design: FastAPI Consolidation & Deployment Fix

**Date:** 2026-03-23
**Status:** Approved (v2 — post spec-review)

## Problem

The app fails to start on Railway with `Error: '$PORT' is not a valid port number`. Root cause: `start.sh` may have CRLF line-endings or a permission issue causing the shebang to fail silently, so gunicorn receives the literal string `$PORT` as its bind address. Additionally, gunicorn cannot serve an async FastAPI app correctly. The fix is to drop gunicorn + `start.sh` entirely and use uvicorn with a shell-form `CMD` in the Dockerfile, which guarantees shell variable expansion.

Beyond the crash, the codebase has two parallel implementations — a legacy `JobScraper.py` monolith and a `src/jobscraper/` package — plus two server files (Flask root `server.py` and FastAPI `src/jobscraper/server.py`). This duplication creates confusion, maintenance overhead, and a mismatched `filter_jobs` signature between the two layers.

## Goals

1. Fix the Railway crash.
2. Consolidate to a single clean stack: FastAPI + SQLAlchemy 2.0.
3. Store job results as proper DB rows (not JSON blobs).
4. Remove all legacy/CLI code. Web app only.

## Non-Goals

- CLI interface (dropped by design).
- Switching DB providers (Postgres on Railway, SQLite locally — unchanged).
- Redesigning the frontend (React SPA stays as-is; no frontend changes).
- Changing the scraper logic (parser, filters, `config.toml` rules unchanged).

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

| File | Change |
|------|--------|
| `src/jobscraper/db.py` | New — SQLAlchemy 2.0 async models |
| `src/jobscraper/server.py` | New — FastAPI app (auth + DB + SSE + static) |
| `src/jobscraper/filters.py` | Updated — accept optional `FilterProfile` override |
| `requirements.txt` | Updated — FastAPI/uvicorn/asyncpg stack, Flask deps removed |
| `Dockerfile` | Updated — fixed CMD, no more `start.sh` |
| `pyproject.toml` | Updated — remove CLI entry point; final `[project.scripts]` block: `jobscraper-web = "jobscraper.server:start"` (bare module name, not `src.jobscraper.server`, because `where = ["src"]` in `[tool.setuptools.packages.find]` makes `jobscraper` the importable package root) |

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
  user_id            INTEGER UNIQUE NOT NULL FK→users
  education_level    VARCHAR(50)
  min_workload       INTEGER NOT NULL DEFAULT 80
  interests          TEXT     -- JSON array string (SQLAlchemy JSON type: TEXT on SQLite, JSON on Postgres)
  allow_quereinstieg BOOLEAN NOT NULL DEFAULT true

search_history
  id          SERIAL PRIMARY KEY
  user_id     INTEGER NOT NULL FK→users
  location    VARCHAR(100) NOT NULL
  timestamp   TIMESTAMP NOT NULL DEFAULT now()
  total_count INTEGER     -- nullable: NULL if scrape failed before completion
  kept_count  INTEGER     -- nullable: NULL if scrape failed before completion
  easy_count  INTEGER     -- nullable: NULL if scrape failed before completion
  -- results_json REMOVED (replaced by jobs table)

  INDEX ON search_history(user_id)    -- for GET /api/history

jobs                                  -- NEW: one row per filtered job
  id             SERIAL PRIMARY KEY
  search_id      INTEGER NOT NULL FK→search_history ON DELETE CASCADE
  uuid           VARCHAR(100)
  title          VARCHAR(500)
  company        VARCHAR(200)         -- raw company from scraper
  company_clean  VARCHAR(200)         -- cleaned by filter pipeline
  location       VARCHAR(200)
  workload       VARCHAR(100)
  contract_type  VARCHAR(100)
  published      VARCHAR(100)
  is_promoted    BOOLEAN
  easy_apply     BOOLEAN
  url            TEXT
  category       VARCHAR(50)

  INDEX ON jobs(search_id)            -- for GET /api/history/{id}
```

**Data stored:** Only filtered jobs (post-pipeline) are inserted into `jobs`. Raw scrape results are not stored in the DB (they are still exported to disk via `export.py` as a backup).

**Partial scrapes:** A `search_history` row is only written after a successful scrape + filter cycle. If scraping fails, no DB row is created. `total_count`, `kept_count`, `easy_count` are always set on insert and are non-null in practice, but declared nullable to allow the schema to evolve.

**Migration:** Tables are recreated via `create_all()` on first deploy. Existing Railway Postgres data is dropped. The seeded `seba` user is recreated automatically on startup.

---

## Filter Override

`filter_jobs()` gains an optional `profile` parameter (fourth positional argument — order matters for `run_in_executor`). The function resolves all filter values locally and passes them explicitly into the helper functions, so the helpers never call the `@lru_cache` getters directly.

```python
from dataclasses import dataclass

@dataclass
class FilterProfile:
    min_workload:          int | None       = None
    include_keywords:      list[str] | None = None
    exclude_keywords:      list[str] | None = None
    manual_exclude_titles: list[str] | None = None
    allow_quereinstieg:    bool             = True  # False → appends "quereinstieg"/"quereinsteiger" to excludes

def filter_jobs(
    jobs: list[Job],
    verbose: bool = True,
    progress_fn: Callable[..., Any] | None = None,
    profile: FilterProfile | None = None,       # ← 4th positional; run_in_executor must match this order
) -> tuple[list[Job], FilterStats]:
    # Resolve all values upfront from profile or config.toml defaults
    min_w    = (profile.min_workload if profile and profile.min_workload is not None
                else get_min_workload())
    includes = (profile.include_keywords if profile and profile.include_keywords is not None
                else get_include_keywords())
    excludes = (profile.exclude_keywords if profile and profile.exclude_keywords is not None
                else get_exclude_keywords())
    manuals  = (profile.manual_exclude_titles if profile and profile.manual_exclude_titles is not None
                else get_manual_exclude_titles())
    if profile and not profile.allow_quereinstieg:
        excludes = excludes + ["quereinstieg", "quereinsteiger"]

    # All four pipeline stages use the local variables above.
    # The helper functions workload_ok / is_excluded / is_included are refactored to
    # accept the resolved lists as parameters rather than calling get_*() themselves:
    #   workload_ok(job.workload, min_w)
    #   is_excluded(job.title, excludes, manuals)
    #   is_included(job.title, includes)
    # This ensures the profile override cannot be silently bypassed.
```

The `@lru_cache` getters in `config.py` are only called when the corresponding `FilterProfile` field is `None`. They remain the authoritative global defaults.

**Building `FilterProfile` for a user in the server:**
```python
p = FilterProfile(
    min_workload=user.profile.min_workload,
    allow_quereinstieg=user.profile.allow_quereinstieg,
    include_keywords=user.profile.get_interests_list() or None,  # None → config.toml defaults
)
# For the seeded 'seba' user: pass FilterProfile() with all defaults → pure config.toml behaviour
```

---

## Scrape + Filter + DB Data Flow

**`filters.py` helper signature changes (required):** `workload_ok`, `is_excluded`, and `is_included` currently call the `get_*()` config getters directly with no arguments. As part of this change they must be updated to accept the resolved values as parameters — `workload_ok(workload_str, min_w)`, `is_excluded(title, excludes, manuals)`, `is_included(title, includes)` — so that the profile override cannot be silently bypassed by the helpers.

The SSE endpoint does the following in order:

1. Validate JWT token from `?token=` query param.
2. Acquire async lock (prevent concurrent scrapes).
3. Start `scrape_async(location, max_pages, progress_queue)` as an `asyncio.Task`.
4. Drain `progress_queue` in a loop, forwarding each event as an SSE frame to the browser — **except** `scrape_done`, which is the internal sentinel that signals scraping is complete and must not be forwarded to the client. When `scrape_done` is received, exit the drain loop and proceed to step 5.
5. When scraping completes, run `filter_jobs()` **via `run_in_executor`** (it is synchronous and CPU-blocking — must not run on the event loop thread):
   ```python
   filtered, stats = await loop.run_in_executor(None, filter_jobs, raw_jobs, False, None, user_filter_profile)
   ```
6. Insert one `search_history` row + bulk-insert all filtered `Job` objects into `jobs`.
7. Emit `done` SSE event with `search_id`, `stats`, `easy_count`.
8. Release async lock.

---

## API Routes

### Auth

```
POST /api/login
  Body:     {"username": str, "password": str}
  200:      {"access_token": str, "username": str}
  401:      {"detail": "Bad username or password"}

POST /api/register
  Body:     {"username": str, "password": str}
  201:      {"access_token": str, "username": str}
  400:      {"detail": "Username already exists"}

GET /api/me
  Header:   Authorization: Bearer <token>
  200:      {"username": str, "profile": ProfileShape}
  401:      {"detail": "Not authenticated"}
```

`ProfileShape`:
```json
{
  "education_level": "EFZ",
  "min_workload": 80,
  "interests": ["detailhandel", "verkauf"],
  "allow_quereinstieg": true
}
```

### History

```
GET /api/history
  Header:  Authorization: Bearer <token>
  200:     [HistorySummary, ...]

GET /api/history/{id}
  Header:  Authorization: Bearer <token>
  200:     {id, location, timestamp, summary, results: [JobShape, ...]}
  404:     {"detail": "Not found"}
  -- Note: field is "results" not "jobs" — matches Dashboard.jsx line 60: res.data.results
```

`HistorySummary`:
```json
{
  "id": 42,
  "location": "winterthur",
  "timestamp": "2026-03-23T10:00:00",
  "summary": {"total": 120, "kept": 18, "easy": 5}
}
```

`JobShape` — fields match exactly what the existing frontend accesses:
```json
{
  "title":       "Verkäufer/in Detailhandel",
  "company":     "Migros AG",
  "location":    "Winterthur",
  "workload":    "80 – 100%",
  "date":        "Heute",        ← mapped from Job.published
  "link":        "https://...",  ← mapped from Job.url
  "easy_apply":  true,
  "category":    "retail"
}
```

Note: `url` (DB column / Pydantic field) is serialized as `link`, and `published` is serialized as `date`, to match what the React frontend reads. This mapping happens in the API response serializer, not in the DB.

### Scrape (SSE)

```
GET /scrape?location=winterthur&max_pages=5&token=<jwt>
  Content-Type: text/event-stream

SSE events:
  found      → {total, total_pages, location, progress}
               -- scrape_async emits {total, total_pages, location}; server adds progress before forwarding
  page       → {page, total_pages, jobs_so_far, progress}
  stage      → {stage, remaining, excluded, progress}
               -- Exception: "dedup" stage emits {stage, kept} not {remaining, excluded}.
               -- Dashboard shows "undefined left" for dedup — pre-existing bug, not fixed here.
  done       → {stats, easy_count, search_id}
  error_msg  → {msg}

stats shape in done event:
  {total, excluded_workload, excluded_keyword, excluded_no_match, duplicates_removed, kept}
```

### Static

```
GET /assets/*  → frontend/dist/assets/ (JS, CSS, icons)
GET /*         → frontend/dist/index.html (SPA catch-all)
```

---

## Auth Implementation

- Algorithm: `HS256`
- Token expiry: 7 days (matches existing frontend behaviour — stored token stays valid)
- Claim: `sub` = `str(user.id)` (integer id as string, matches existing stored tokens)
- Env var: `JWT_SECRET_KEY` (required in production; falls back to `"dev-secret-change-me"` locally)
- Library: `python-jose[cryptography]` + `passlib[bcrypt]`
- 401 response body: FastAPI default `{"detail": "..."}`. The `Login.jsx` error handler reads `err.response?.data?.msg` — since the field is `detail` not `msg`, login error messages will always fall back to the hardcoded `'Login failed'` string. This is accepted behaviour; no frontend change is made.

### Auth Dependency Injection Pattern

All protected routes (except `/scrape`) use a FastAPI `Depends`:

```python
async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> UserRow:
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.get(UserRow, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

The `/scrape` SSE route cannot use `Header` injection (browser `EventSource` sends no custom headers). It reads `token` from the query string and decodes it manually at the top of the route handler.

**History scoping:** `GET /api/history` and `GET /api/history/{id}` filter by `search_history.user_id == current_user.id`. Users only see their own history.

## SQLAlchemy Models (`src/jobscraper/db.py`)

The `Profile` model includes a helper method for the `interests` JSON column:

```python
class ProfileRow(Base):
    __tablename__ = "profiles"
    id                 = Column(Integer, primary_key=True)
    user_id            = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    education_level    = Column(String(50), nullable=True)
    min_workload       = Column(Integer, nullable=False, default=80)
    interests          = Column(Text, nullable=True)   # JSON array string
    allow_quereinstieg = Column(Boolean, nullable=False, default=True)

    def get_interests_list(self) -> list[str]:
        if self.interests:
            try:
                return json.loads(self.interests)
            except (json.JSONDecodeError, TypeError):
                return []
        return []
```

The `GET /api/me` response serialises `interests` by calling `profile.get_interests_list()` — never returning the raw TEXT value directly. This ensures the frontend always receives a JSON array, not a string.

---

## Deployment Fix

**Old (broken):**
```dockerfile
CMD ["./start.sh"]   # exec form: no shell → $PORT never expanded
```

**New (fixed):**
```dockerfile
CMD ["sh", "-c", "uvicorn src.jobscraper.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

Shell form (`sh -c "..."`) expands `${PORT:-8080}` before uvicorn receives the argument. The `:-8080` fallback keeps local development working without setting `PORT`.

### Updated `requirements.txt`

Removed: `Flask`, `gunicorn`, `Flask-SQLAlchemy`, `Flask-JWT-Extended`, `requests`, `tqdm`, `psycopg-binary`

Added:
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

---

## Seeded Data

On startup, if `seba` does not exist in `users`:
- User: `seba` / `seba123`
- Profile: `education_level="EFZ"`, `min_workload=80`, `interests=["detailhandel","verkauf","lager","gastro"]`, `allow_quereinstieg=True`
- Filter behaviour: `FilterProfile` with all keyword fields as `None` → uses pure `config.toml` defaults

---

## Security Notes

- The `?token=` query param in `/scrape` makes the JWT visible in server access logs and browser history. This is an accepted limitation of the SSE protocol (no custom headers). Railway log format should be reviewed if log privacy is a concern.

---

## Out of Scope

- Profile editing via UI (profile set at seed time or via direct DB)
- Pagination of `/api/history/{id}` jobs list
- Background job scheduling
- Any frontend changes
