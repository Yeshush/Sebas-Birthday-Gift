"""FastAPI web server for JobScraper."""
from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any

import bcrypt as _bcrypt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import (
    AsyncSessionLocal, Base, JobRow, ProfileRow, SearchHistoryRow, UserRow, engine, get_db,
)
from .filters import FilterProfile, filter_jobs
from .models import Job
from .scraper import scrape_async

load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM  = "HS256"
JWT_EXPIRE_DAYS = 7

def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode(), hashed.encode())


_scrape_lock: asyncio.Lock | None = None


def _get_scrape_lock() -> asyncio.Lock:
    global _scrape_lock
    if _scrape_lock is None:
        _scrape_lock = asyncio.Lock()
    return _scrape_lock

DIST_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(UserRow).where(UserRow.username == "seba")
        )
        if not result.scalar_one_or_none():
            seba = UserRow(username="seba", password_hash=_hash_password("seba123"))
            session.add(seba)
            await session.flush()
            profile = ProfileRow(
                user_id=seba.id,
                education_level="EFZ",
                min_workload=80,
                interests=json.dumps(["detailhandel", "verkauf", "lager", "gastro"]),
                allow_quereinstieg=True,
            )
            session.add(profile)
            await session.commit()
            logger.info("Seeded user 'seba'")
    yield


app = FastAPI(title="JobScraper", lifespan=lifespan, docs_url=None, redoc_url=None)


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


async def get_current_user(
    authorization: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db),
) -> UserRow:
    try:
        token   = authorization.removeprefix("Bearer ").strip()
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.get(UserRow, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.post("/api/login")
async def login(request: Request, db: AsyncSession = Depends(get_db)):
    body     = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    result   = await db.execute(select(UserRow).where(UserRow.username == username))
    user     = result.scalar_one_or_none()
    if not user or not _verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Bad username or password")
    return {"access_token": _create_token(user.id), "username": user.username}


@app.post("/api/register", status_code=201)
async def register(request: Request, db: AsyncSession = Depends(get_db)):
    body     = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    result = await db.execute(select(UserRow).where(UserRow.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")
    user = UserRow(username=username, password_hash=_hash_password(password))
    db.add(user)
    await db.flush()
    db.add(ProfileRow(user_id=user.id))
    await db.commit()
    return {"access_token": _create_token(user.id), "username": user.username}


@app.get("/api/me")
async def me(
    current_user: Annotated[UserRow, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    result  = await db.execute(
        select(ProfileRow).where(ProfileRow.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    return {
        "username": current_user.username,
        "profile": {
            "education_level": profile.education_level if profile else None,
            "min_workload":    profile.min_workload    if profile else 80,
            "interests":       profile.get_interests_list() if profile else [],
            "allow_quereinstieg": profile.allow_quereinstieg if profile else True,
        },
    }


@app.put("/api/profile")
async def update_profile(
    request: Request,
    current_user: Annotated[UserRow, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    result = await db.execute(
        select(ProfileRow).where(ProfileRow.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = ProfileRow(user_id=current_user.id)
        db.add(profile)

    if "education_level" in body:
        profile.education_level = (body["education_level"] or "").strip() or None
    if "min_workload" in body:
        profile.min_workload = max(0, min(100, int(body["min_workload"])))
    if "interests" in body:
        cleaned = [s.strip().lower() for s in body["interests"] if s.strip()]
        profile.interests = json.dumps(cleaned)
    if "allow_quereinstieg" in body:
        profile.allow_quereinstieg = bool(body["allow_quereinstieg"])

    await db.commit()
    await db.refresh(profile)
    return {
        "education_level": profile.education_level,
        "min_workload":    profile.min_workload,
        "interests":       profile.get_interests_list(),
        "allow_quereinstieg": profile.allow_quereinstieg,
    }


# ── History routes ─────────────────────────────────────────────────────────────

@app.get("/api/history")
async def history(
    current_user: Annotated[UserRow, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SearchHistoryRow)
        .where(SearchHistoryRow.user_id == current_user.id)
        .order_by(SearchHistoryRow.timestamp.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id":        r.id,
            "location":  r.location,
            "timestamp": r.timestamp.isoformat(),
            "summary":   {"total": r.total_count, "kept": r.kept_count, "easy": r.easy_count},
        }
        for r in rows
    ]


@app.get("/api/history/{search_id}")
async def history_detail(
    search_id: int,
    current_user: Annotated[UserRow, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SearchHistoryRow).where(
            SearchHistoryRow.id == search_id,
            SearchHistoryRow.user_id == current_user.id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")

    jobs_result = await db.execute(
        select(JobRow).where(JobRow.search_id == search_id)
    )
    jobs = jobs_result.scalars().all()

    return {
        "id":        row.id,
        "location":  row.location,
        "timestamp": row.timestamp.isoformat(),
        "summary":   {"total": row.total_count, "kept": row.kept_count, "easy": row.easy_count},
        "results": [
            {
                "title":      j.title,
                "company":    j.company_clean or j.company,
                "location":   j.location,
                "workload":   j.workload,
                "date":       j.published,   # published → date (frontend expects "date")
                "link":       j.url,         # url → link (frontend expects "link")
                "easy_apply": j.easy_apply,
                "category":   j.category,
            }
            for j in jobs
        ],
    }


# ── Scrape SSE ─────────────────────────────────────────────────────────────────

def _sanitize_location(raw: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "", raw.lower())[:50] or "winterthur"


@app.get("/scrape")
async def scrape_sse(
    location:  str           = Query("winterthur"),
    max_pages: int | None    = Query(None, ge=1, le=500),
    token:     str           = Query(...),
):
    # Validate JWT manually (EventSource cannot set headers)
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        async def _err():
            yield f'event: error_msg\ndata: {json.dumps({"msg": "Invalid token"})}\n\n'
        return StreamingResponse(_err(), media_type="text/event-stream")

    location = _sanitize_location(location)

    async def event_stream() -> Any:
        if _get_scrape_lock().locked():
            yield f'event: error_msg\ndata: {json.dumps({"msg": "Scraper läuft bereits – bitte warten!"})}\n\n'
            return

        async with _get_scrape_lock():
            progress_queue: asyncio.Queue = asyncio.Queue()

            scrape_task = asyncio.create_task(
                scrape_async(location, max_pages, progress_queue)
            )

            _PROGRESS_MAP = {"found": 5}
            _STAGE_PROGRESS = {
                "workload": 65, "keywords": 72, "relevance": 78, "dedup": 83,
            }

            # Drain progress events; stop when scrape_done sentinel arrives
            try:
                while True:
                    try:
                        event_type, data = await asyncio.wait_for(
                            progress_queue.get(), timeout=25
                        )
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue

                    if event_type == "scrape_done":
                        # Internal sentinel — do not forward to browser
                        break

                    # Attach progress %
                    if event_type == "page":
                        page  = data.get("page", 1)
                        total = data.get("total_pages", 1)
                        data["progress"] = 5 + int(55 * page / max(total, 1))
                    elif event_type == "stage":
                        data["progress"] = _STAGE_PROGRESS.get(data.get("stage", ""), 80)
                    else:
                        data["progress"] = _PROGRESS_MAP.get(event_type, 0)

                    yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

            except Exception as exc:
                logger.exception("SSE drain error")
                yield f'event: error_msg\ndata: {json.dumps({"msg": str(exc)})}\n\n'
                scrape_task.cancel()
                return

            raw_jobs: list[Job] = await scrape_task

            if not raw_jobs:
                yield f'event: error_msg\ndata: {json.dumps({"msg": "Keine Jobs gefunden"})}\n\n'
                return

            # Build per-user filter profile
            async with AsyncSessionLocal() as db:
                profile_result = await db.execute(
                    select(ProfileRow).where(ProfileRow.user_id == user_id)
                )
                profile = profile_result.scalar_one_or_none()
                interests = profile.get_interests_list() if profile else []

                # Derive keyword from EFZ field (e.g. "Detailhandel EFZ" → "detailhandel")
                efz_kw: list[str] = []
                if profile and profile.education_level:
                    efz_field = re.sub(r"\befz\b", "", profile.education_level, flags=re.IGNORECASE).strip().lower()
                    if efz_field and efz_field not in interests:
                        efz_kw = [efz_field]

                include_kw = efz_kw + interests
                filter_profile = FilterProfile(
                    min_workload=profile.min_workload if profile else None,
                    allow_quereinstieg=profile.allow_quereinstieg if profile else True,
                    include_keywords=include_kw if include_kw else None,
                )

            # Run synchronous filter pipeline off the event loop
            loop = asyncio.get_running_loop()
            try:
                filtered, stats = await loop.run_in_executor(
                    None, filter_jobs, raw_jobs, False, None, filter_profile
                )
            except Exception as exc:
                logger.exception("Filter pipeline error")
                yield f'event: error_msg\ndata: {json.dumps({"msg": f"Filter error: {exc}"})}\n\n'
                return

            # Persist to DB
            easy_count  = sum(1 for j in filtered if j.easy_apply)
            async with AsyncSessionLocal() as db:
                history_row = SearchHistoryRow(
                    user_id=user_id,
                    location=location,
                    total_count=stats.total,
                    kept_count=stats.kept,
                    easy_count=easy_count,
                )
                db.add(history_row)
                await db.flush()

                for job in filtered:
                    db.add(JobRow(
                        search_id=history_row.id,
                        uuid=job.uuid,
                        title=job.title,
                        company=job.company,
                        company_clean=job.company_clean,
                        location=job.location,
                        workload=job.workload,
                        contract_type=job.contract_type,
                        published=job.published,
                        is_promoted=job.is_promoted,
                        easy_apply=job.easy_apply,
                        url=job.url,
                        category=job.category,
                    ))
                await db.commit()
                search_id = history_row.id

            yield (
                f'event: done\ndata: {json.dumps({"stats": stats.model_dump(), "easy_count": easy_count, "search_id": search_id})}\n\n'
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Static files (React SPA) ───────────────────────────────────────────────────

_assets_dir = DIST_DIR / "assets"
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

# Mount public files (favicon, icons)
for _fname in ("favicon.svg", "icons.svg"):
    _fpath = DIST_DIR / _fname
    if _fpath.exists():
        @app.get(f"/{_fname}", include_in_schema=False)
        async def _static_file(f=_fpath):
            return FileResponse(f)


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str) -> FileResponse:
    index = DIST_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=503, detail="Frontend not built. Run: cd frontend && npm run build")
    return FileResponse(index)


# ── Entry point ────────────────────────────────────────────────────────────────

def start() -> None:
    import uvicorn
    port = int(os.getenv("PORT", "5001"))
    logger.info("JobScraper starting on port {}", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
