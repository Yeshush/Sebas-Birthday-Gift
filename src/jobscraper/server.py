"""FastAPI web UI with SSE progress streaming for JobScraper."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger

# Re-export scraper functions that server.py accesses directly
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from jobscraper.export import generate_html, save_csv, save_json
from jobscraper.filters import filter_jobs
from jobscraper.scraper import scrape

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
FILT_DIR = Path("filtered_results")
RAW_DIR  = Path("results")

_run_lock = asyncio.Lock()

app = FastAPI(title="JobScraper", docs_url=None, redoc_url=None)

_jinja = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


def _sanitize_location(raw: str) -> str:
    """Strip all characters except lowercase letters, digits, and hyphens."""
    return re.sub(r"[^a-z0-9\-]", "", raw.lower())[:50] or "winterthur"


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _jinja.get_template("start.html").render()


@app.get("/scrape")
async def scrape_sse(
    location: str = Query("winterthur"),
    max_pages: int | None = Query(None, ge=1, le=500),
) -> StreamingResponse:
    location = _sanitize_location(location)

    async def event_stream():
        if _run_lock.locked():
            yield f"event: error_msg\ndata: {json.dumps({'msg': 'Scraper läuft bereits – bitte warten!'})}\n\n"
            return

        async with _run_lock:
            progress_q: asyncio.Queue = asyncio.Queue()
            result: dict = {}
            error_occurred = False

            def on_progress(event_type: str, **kwargs):
                """Sync callback bridging the scraper thread to the async queue."""
                asyncio.get_event_loop().call_soon_threadsafe(
                    progress_q.put_nowait, (event_type, kwargs)
                )

            def run_scraper():
                nonlocal error_occurred
                try:
                    raw_jobs = scrape(location, max_pages, progress_fn=on_progress)

                    if not raw_jobs:
                        progress_q.put_nowait(("error_msg", {"msg": "Keine Jobs gefunden"}))
                        return

                    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                    stem = f"jobs_{location}_{ts}"

                    RAW_DIR.mkdir(parents=True, exist_ok=True)
                    save_csv(raw_jobs,  RAW_DIR / f"{stem}.csv")
                    save_json(raw_jobs, RAW_DIR / f"{stem}.json")

                    filtered, stats = filter_jobs(raw_jobs, verbose=False,
                                                  progress_fn=on_progress)

                    on_progress("stage", stage="generating",
                                remaining=len(filtered), excluded=0)

                    FILT_DIR.mkdir(parents=True, exist_ok=True)
                    save_json(filtered, FILT_DIR / f"{stem}_filtered.json")

                    html_name = f"jobs_{location}_{ts}.html"
                    generate_html(filtered, stats, location, FILT_DIR / html_name)

                    easy_count = sum(1 for j in filtered if j.easy_apply)
                    progress_q.put_nowait(("done", {
                        "html_name": html_name,
                        "stats":     stats.model_dump(),
                        "easy_count": easy_count,
                    }))

                except Exception as exc:
                    logger.exception("Scraper thread error")
                    progress_q.put_nowait(("error_msg", {"msg": f"{type(exc).__name__}: {exc}"}))
                finally:
                    progress_q.put_nowait(("__sentinel__", {}))

            t = threading.Thread(target=run_scraper, daemon=True)
            t.start()

            _PROGRESS_MAP = {
                "found":       5,
                "scrape_done": 62,
            }
            _STAGE_PROGRESS = {
                "workload":   65,
                "keywords":   72,
                "relevance":  78,
                "dedup":      83,
                "generating": 90,
            }

            while True:
                try:
                    event_type, data = await asyncio.wait_for(progress_q.get(), timeout=25)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if event_type == "__sentinel__":
                    break

                # Attach progress percentage to data
                if event_type == "page":
                    page  = data.get("page", 1)
                    total = data.get("total_pages", 1)
                    data["progress"] = 5 + int(55 * page / max(total, 1))
                elif event_type == "stage":
                    data["progress"] = _STAGE_PROGRESS.get(data.get("stage", ""), 80)
                else:
                    data["progress"] = _PROGRESS_MAP.get(event_type, 0)

                yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

                if event_type in ("done", "error_msg"):
                    break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/results/{filename:path}")
async def serve_result(filename: str) -> FileResponse:
    # Guard: only allow simple filenames (no path separators, must end in .html)
    if not re.match(r"^[a-z0-9_\-]+\.html$", filename):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    filepath = FILT_DIR / filename
    resolved = filepath.resolve()

    # Guard against path traversal
    if not str(resolved).startswith(str(FILT_DIR.resolve())):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    if not resolved.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")

    return FileResponse(resolved, media_type="text/html")


def start() -> None:
    """Entry point for the `jobscraper-web` console script."""
    port = 5001
    url  = f"http://localhost:{port}"
    logger.info("JobScraper web UI starting at {}", url)
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    start()
