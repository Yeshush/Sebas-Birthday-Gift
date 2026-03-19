"""CSV, JSON, and HTML export functions."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from loguru import logger

from .models import FilterStats, Job

# Templates directory: two levels above this file (project root / templates/)
_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

_DE_MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

_CAT_LABELS = {
    "retail":       "Retail & Detailhandel",
    "lager":        "Lager & Logistik",
    "verkauf":      "Verkauf & Kundenberatung",
    "gastro":       "Gastronomie & Service",
    "quereinstieg": "Quereinstieg / Offen",
}


def save_csv(jobs: list[Job], path: Path) -> None:
    """Write jobs to a UTF-8 CSV file."""
    if not jobs:
        return
    rows = [j.model_dump() for j in jobs]
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.success("CSV gespeichert: {}", path)


def save_json(jobs: list[Job], path: Path) -> None:
    """Write jobs to a UTF-8 JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump([j.model_dump() for j in jobs], f, ensure_ascii=False, indent=2)
    logger.success("JSON gespeichert: {}", path)


def generate_html(jobs: list[Job], stats: FilterStats, location: str, path: Path) -> None:
    """Render the interactive HTML report using Jinja2."""
    now            = datetime.now()
    generated_date = f"{now.day}. {_DE_MONTHS[now.month - 1]} {now.year}"
    easy_count     = sum(1 for j in jobs if j.easy_apply)
    cat_count      = len({j.category for j in jobs})
    querei_count   = sum(1 for j in jobs if "quereinstieg" in j.title.lower())
    cat_breakdown  = dict(Counter(j.category for j in jobs))

    env = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html")

    # Serialize jobs to JSON once here; mark as Markup so Jinja2 won't re-escape.
    # The </script> sequence is escaped to prevent breaking out of the script block.
    jobs_raw = json.dumps([j.model_dump() for j in jobs], ensure_ascii=False)
    jobs_raw = jobs_raw.replace("</script>", "<\\/script>")

    html = template.render(
        jobs_json=Markup(jobs_raw),
        stats=stats,
        location=location,
        generated_date=generated_date,
        easy_count=easy_count,
        cat_count=cat_count,
        querei_count=querei_count,
        cat_breakdown=cat_breakdown,
        cat_labels=_CAT_LABELS,
    )
    path.write_text(html, encoding="utf-8")
    logger.success("HTML gespeichert: {}", path)
