"""HTML parsers for jobs.ch search result pages."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from loguru import logger

from .models import Job

BASE_URL = "https://www.jobs.ch"


def parse_total_count(soup: BeautifulSoup) -> int:
    """Extract total job count from the page header."""
    header = soup.find(attrs={"data-cy": "page-header"})
    if header:
        text = header.get_text(strip=True)
        numbers = re.findall(r"[\d\s']+(?=\s*jobs)", text)
        if numbers:
            clean = re.sub(r"[\s']", "", numbers[0])
            try:
                return int(clean)
            except ValueError:
                pass
    logger.warning("Could not parse total job count from page header")
    return 0


def parse_jobs(soup: BeautifulSoup) -> list[Job]:
    """Extract all job cards from a search result page."""
    jobs: list[Job] = []
    items = soup.find_all(attrs={"data-cy": "serp-item"})

    for item in items:
        job_link = item.find(attrs={"data-cy": "job-link"})
        if not job_link:
            continue
        href = job_link.get("href", "")
        full_url = BASE_URL + href if href.startswith("/") else href
        uuid = href.rstrip("/").split("/")[-1]

        title_el = item.find("span", class_=lambda c: c and "c_purple" in c)
        title = title_el.get_text(strip=True) if title_el else ""

        paragraphs = [
            p.get_text(strip=True)
            for p in item.find_all("p", class_=lambda c: c and "textStyle_caption1" in c)
        ]

        published     = paragraphs[0] if len(paragraphs) > 0 else ""
        location      = paragraphs[1] if len(paragraphs) > 1 else ""
        workload      = paragraphs[2] if len(paragraphs) > 2 else ""
        contract_type = paragraphs[3] if len(paragraphs) > 3 else ""
        company       = paragraphs[4] if len(paragraphs) > 4 else ""

        is_promoted    = bool(item.find(attrs={"data-cy": "recommended"}))
        has_easy_apply = bool(item.find(attrs={"data-cy": "quick-apply"}))

        # Skip jobs with invalid/missing URLs
        if not full_url.startswith(("http://", "https://")):
            logger.debug("Skipping job with invalid URL: {!r}", full_url)
            continue

        try:
            jobs.append(Job(
                uuid=uuid,
                title=title,
                company=company,
                location=location,
                workload=workload,
                contract_type=contract_type,
                published=published,
                is_promoted=is_promoted,
                easy_apply=has_easy_apply,
                url=full_url,
            ))
        except Exception as exc:
            logger.debug("Skipping malformed job card ({}): {}", exc, title[:60])

    return jobs


def make_soup(html: bytes | str) -> BeautifulSoup:
    """Create a BeautifulSoup object using the fast lxml parser."""
    return BeautifulSoup(html, "lxml")
