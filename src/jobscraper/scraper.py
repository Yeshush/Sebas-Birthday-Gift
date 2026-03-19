"""HTTP scraper: fetches jobs.ch pages with httpx and polite delays."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable
from typing import Any

import httpx
from loguru import logger

from .models import Job
from .parser import make_soup, parse_jobs, parse_total_count

BASE_URL   = "https://www.jobs.ch"
SEARCH_URL = f"{BASE_URL}/en/vacancies/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer":         "https://www.jobs.ch/",
}

DELAY_BETWEEN_REQUESTS = 1.0   # polite delay between requests (seconds)
ITEMS_PER_PAGE         = 20    # jobs.ch shows ~20 jobs per page
MAX_CONCURRENT_PAGES   = 3     # async semaphore limit


# ── Sync scraper (used by CLI and legacy server.py) ───────────────────────────

def fetch_page_sync(
    client: httpx.Client, location: str, page: int
) -> bytes | None:
    """Fetch one search result page, return raw HTML bytes or None on error."""
    params = {"location": location, "term": "", "page": page}
    try:
        response = client.get(SEARCH_URL, params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as exc:
        logger.warning("Page {} fetch failed: {}", page, exc)
        return None


def scrape(
    location: str,
    max_pages: int | None = None,
    progress_fn: Callable[..., Any] | None = None,
) -> list[Job]:
    """
    Scrape all jobs for a given location (synchronous).

    Args:
        location:    City name, e.g. "winterthur" or "zurich"
        max_pages:   Maximum pages to fetch (None = all)
        progress_fn: Optional callback(event, **kwargs) for the web UI.

    Returns:
        List of unique Job objects.
    """
    all_jobs: list[Job] = []

    transport = httpx.HTTPTransport(retries=3)
    with httpx.Client(transport=transport) as client:
        logger.info("Starting scrape for location: «{}»", location)

        html = fetch_page_sync(client, location, page=1)
        if html is None:
            logger.error("Could not load page 1 — aborting.")
            return []

        soup  = make_soup(html)
        total = parse_total_count(soup)
        if total == 0:
            logger.warning("No jobs found or count not readable.")
            return []

        total_pages = math.ceil(total / ITEMS_PER_PAGE)
        if max_pages:
            total_pages = min(total_pages, max_pages)

        logger.info("Found {:,} jobs across ~{} pages", total, total_pages)
        if progress_fn:
            progress_fn("found", total=total, total_pages=total_pages, location=location)

        all_jobs.extend(parse_jobs(soup))

        for page in range(2, total_pages + 1):
            time.sleep(DELAY_BETWEEN_REQUESTS)
            if progress_fn:
                progress_fn("page", page=page, total_pages=total_pages, jobs_so_far=len(all_jobs))
            html = fetch_page_sync(client, location, page)
            if html is None:
                continue
            page_jobs = parse_jobs(make_soup(html))
            if not page_jobs:
                logger.info("No more jobs on page {} — stopping.", page)
                break
            all_jobs.extend(page_jobs)

    # Deduplicate by UUID (promoted jobs appear on multiple pages)
    seen: set[str] = set()
    unique: list[Job] = []
    for job in all_jobs:
        if job.uuid not in seen:
            seen.add(job.uuid)
            unique.append(job)

    logger.success("Scraping done: {:,} unique jobs found", len(unique))
    if progress_fn:
        progress_fn("scrape_done", jobs=len(unique))
    return unique


# ── Async scraper (used by FastAPI server) ────────────────────────────────────

async def fetch_page_async(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    location: str,
    page: int,
) -> bytes | None:
    """Fetch one page asynchronously, respecting the semaphore."""
    async with sem:
        await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
        params = {"location": location, "term": "", "page": page}
        try:
            response = await client.get(SEARCH_URL, params=params, headers=HEADERS, timeout=15)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            logger.warning("Async page {} fetch failed: {}", page, exc)
            return None


async def scrape_async(
    location: str,
    max_pages: int | None = None,
    progress_queue: asyncio.Queue | None = None,
) -> list[Job]:
    """
    Scrape all jobs for a given location (async, 3x faster via concurrency).

    Args:
        location:       City name.
        max_pages:      Maximum pages to fetch (None = all).
        progress_queue: asyncio.Queue for SSE progress events.
    """

    async def emit(event: str, **kwargs: Any) -> None:
        if progress_queue is not None:
            await progress_queue.put((event, kwargs))

    transport = httpx.AsyncHTTPTransport(retries=3)
    async with httpx.AsyncClient(transport=transport) as client:
        logger.info("Async scraping «{}»", location)

        html = await fetch_page_async(client, asyncio.Semaphore(1), location, page=1)
        if html is None:
            logger.error("Could not load page 1 — aborting.")
            return []

        soup  = make_soup(html)
        total = parse_total_count(soup)
        if total == 0:
            logger.warning("No jobs found or count not readable.")
            return []

        total_pages = math.ceil(total / ITEMS_PER_PAGE)
        if max_pages:
            total_pages = min(total_pages, max_pages)

        logger.info("Found {:,} jobs across ~{} pages", total, total_pages)
        await emit("found", total=total, total_pages=total_pages, location=location)

        all_jobs: list[Job] = list(parse_jobs(soup))
        sem = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

        async def fetch_and_report(page: int) -> list[Job]:
            page_html = await fetch_page_async(client, sem, location, page)
            if page_html is None:
                return []
            jobs = parse_jobs(make_soup(page_html))
            await emit("page", page=page, total_pages=total_pages, jobs_so_far=len(all_jobs))
            return jobs

        tasks = [fetch_and_report(p) for p in range(2, total_pages + 1)]
        for page_jobs in await asyncio.gather(*tasks):
            all_jobs.extend(page_jobs)

    # Deduplicate by UUID
    seen: set[str] = set()
    unique: list[Job] = []
    for job in all_jobs:
        if job.uuid not in seen:
            seen.add(job.uuid)
            unique.append(job)

    logger.success("Async scraping done: {:,} unique jobs found", len(unique))
    await emit("scrape_done", jobs=len(unique))
    return unique
