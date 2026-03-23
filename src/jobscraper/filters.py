"""4-stage filter pipeline for JobScraper."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from .config import (
    get_exclude_keywords,
    get_include_keywords,
    get_manual_exclude_titles,
    get_min_workload,
)
from .models import FilterStats, Job

_CAT_LABELS = {
    "retail":       "Retail & Detailhandel",
    "lager":        "Lager & Logistik",
    "verkauf":      "Verkauf & Kundenberatung",
    "gastro":       "Gastronomie & Service",
    "quereinstieg": "Quereinstieg / Offen",
}


@dataclass
class FilterProfile:
    """Per-user filter overrides. None fields fall back to config.toml defaults."""
    min_workload:          int | None       = None
    include_keywords:      list[str] | None = None
    exclude_keywords:      list[str] | None = None
    manual_exclude_titles: list[str] | None = None
    allow_quereinstieg:    bool             = True


def parse_workload(workload_str: str) -> tuple[int, int]:
    """Parse workload strings like '80 – 100%' or '100%'. Returns (min, max)."""
    if not workload_str:
        return (0, 0)
    cleaned = workload_str.lower().replace("%", "").replace(" ", "")
    for sep in ["–", "-"]:
        if sep in cleaned:
            parts = cleaned.split(sep)
            try:
                return (int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                pass
    try:
        val = int(cleaned)
        return (val, val)
    except ValueError:
        return (0, 0)


def workload_ok(workload_str: str, min_workload: int) -> bool:
    """Return True if the maximum workload is >= min_workload."""
    _, max_w = parse_workload(workload_str)
    return max_w >= min_workload


def is_excluded(title: str, excludes: list[str], manuals: list[str]) -> tuple[bool, str]:
    """Check if the title contains any exclusion keyword."""
    tl = title.lower()
    for kw in excludes:
        if kw in tl:
            return True, f"Ausschluss-Keyword: '{kw}'"
    for manual in manuals:
        if manual in tl:
            return True, f"Manueller Ausschluss: '{manual}'"
    return False, ""


def is_included(title: str, includes: list[str]) -> tuple[bool, str]:
    """Check if the title contains any inclusion keyword."""
    tl = title.lower()
    for kw in includes:
        if kw in tl:
            return True, f"Inklusions-Keyword: '{kw}'"
    return False, ""


def assign_category(title: str) -> str:
    """Assign one of five category keys based on the title."""
    tl = title.lower()
    if any(k in tl for k in ["detailhandel", "filial", "laden", "markt", "coop", "migros",
                               "volg", "food", "non-food", "kassi", "crew", "otto"]):
        return "retail"
    if any(k in tl for k in ["lager", "logistik", "magazin", "auslieferung",
                               "betriebsunterhalt", "kurier", "postdienst"]):
        return "lager"
    if any(k in tl for k in ["verkauf", "verkäufer", "kundenberater", "kundenberatung",
                               "kundendienst", "beratung", "sales", "versicherung",
                               "telemarketing", "frontoffice", "assistenz"]):
        return "verkauf"
    if any(k in tl for k in ["service", "gastro", "restaurant", "küche", "bar",
                               "koch", "köchin"]):
        return "gastro"
    return "quereinstieg"


def fix_company(job: Job) -> str:
    """Clean company name (workaround for jobs.ch hiding company names)."""
    company = job.company
    if company == "Is this job relevant to you?":
        ct = job.contract_type
        standard = {"Permanent position", "Festanstellung", "Internship", "Temporary", "Temporär"}
        if ct and ct not in standard and len(ct) > 3:
            return ct
        return "Unbekannt"
    return company


def filter_jobs(
    jobs: list[Job],
    verbose: bool = True,
    progress_fn: Callable[..., Any] | None = None,
    profile: FilterProfile | None = None,
) -> tuple[list[Job], FilterStats]:
    """
    Run the 4-stage filter pipeline.

    profile overrides individual filter settings; None fields fall back to config.toml.
    NOTE: fourth positional argument — run_in_executor callers must match this order.
    """
    # Resolve filter values from profile or config.toml defaults
    min_w    = profile.min_workload          if (profile and profile.min_workload is not None)          else get_min_workload()
    includes = profile.include_keywords      if (profile and profile.include_keywords is not None)      else get_include_keywords()
    excludes = profile.exclude_keywords      if (profile and profile.exclude_keywords is not None)      else get_exclude_keywords()
    manuals  = profile.manual_exclude_titles if (profile and profile.manual_exclude_titles is not None) else get_manual_exclude_titles()
    if profile and not profile.allow_quereinstieg:
        excludes = list(excludes) + ["quereinstieg", "quereinsteiger"]

    stats = FilterStats(total=len(jobs))

    # Stage 1: Workload
    stage1: list[Job] = []
    for job in jobs:
        if workload_ok(job.workload, min_w):
            stage1.append(job)
        else:
            stats.excluded_workload += 1
            if verbose:
                logger.debug("[Pensum] Ausgeschlossen: {} ({})", job.title[:60], job.workload)

    if verbose:
        logger.info("✓ Nach Pensum-Filter: {} verbleibend ({} ausgeschlossen)",
                    len(stage1), stats.excluded_workload)
    if progress_fn:
        progress_fn("stage", stage="workload",
                    remaining=len(stage1), excluded=stats.excluded_workload)

    # Stage 2: Exclusion keywords
    stage2: list[Job] = []
    for job in stage1:
        excluded, reason = is_excluded(job.title, excludes, manuals)
        if not excluded:
            stage2.append(job)
        else:
            stats.excluded_keyword += 1
            if verbose:
                logger.debug("[Keyword-Ausschluss] {} → {}", job.title[:60], reason)

    if verbose:
        logger.info("✓ Nach Keyword-Ausschluss: {} verbleibend ({} ausgeschlossen)",
                    len(stage2), stats.excluded_keyword)
    if progress_fn:
        progress_fn("stage", stage="keywords",
                    remaining=len(stage2), excluded=stats.excluded_keyword)

    # Stage 3: Inclusion/relevance
    stage3: list[Job] = []
    for job in stage2:
        included, _ = is_included(job.title, includes)
        if included:
            stage3.append(job)
        else:
            stats.excluded_no_match += 1
            if verbose:
                logger.debug("[Kein Match] Ausgeschlossen: {}", job.title[:60])

    if verbose:
        logger.info("✓ Nach Relevanz-Check: {} verbleibend ({} ausgeschlossen)",
                    len(stage3), stats.excluded_no_match)
    if progress_fn:
        progress_fn("stage", stage="relevance",
                    remaining=len(stage3), excluded=stats.excluded_no_match)

    # Stage 4: Deduplication by title + enrichment
    seen_titles: set[str] = set()
    deduplicated: list[Job] = []
    for job in stage3:
        key = job.title.lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            job.company_clean = fix_company(job)
            job.category      = assign_category(job.title)
            deduplicated.append(job)
        else:
            stats.duplicates_removed += 1
            if verbose:
                logger.debug("[Duplikat] Entfernt: {}", job.title[:60])

    stats.kept = len(deduplicated)
    if progress_fn:
        progress_fn("stage", stage="dedup", kept=stats.kept)

    return deduplicated, stats
