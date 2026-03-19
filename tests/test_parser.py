"""Tests for HTML parser functions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bs4 import BeautifulSoup

from jobscraper.parser import make_soup, parse_jobs, parse_total_count


def _minimal_serp_html(total: int = 42, jobs: list[dict] | None = None) -> str:
    """Build a minimal jobs.ch SERP HTML fixture."""
    jobs = jobs or []
    job_items = ""
    for j in jobs:
        job_items += f"""
        <article data-cy="serp-item">
          <a data-cy="job-link" href="/en/vacancies/detail/{j.get('uuid','abc123')}/"></a>
          <span class="c_purple someclass">{j.get('title','Test Job')}</span>
          <p class="textStyle_caption1 x">Heute</p>
          <p class="textStyle_caption1 x">Winterthur</p>
          <p class="textStyle_caption1 x">80-100%</p>
          <p class="textStyle_caption1 x">Festanstellung</p>
          <p class="textStyle_caption1 x">{j.get('company','Migros AG')}</p>
        </article>"""
    return f"""<html><body>
      <div data-cy="page-header">{total} jobs found</div>
      {job_items}
    </body></html>"""


# ── make_soup ─────────────────────────────────────────────────────────────────

def test_make_soup_returns_beautifulsoup():
    soup = make_soup("<html><body></body></html>")
    assert isinstance(soup, BeautifulSoup)

def test_make_soup_accepts_bytes():
    soup = make_soup(b"<html><body><p>hello</p></body></html>")
    assert soup.find("p").get_text() == "hello"


# ── parse_total_count ─────────────────────────────────────────────────────────

def test_parse_total_count_extracts_number():
    soup = make_soup(_minimal_serp_html(total=1234))
    assert parse_total_count(soup) == 1234

def test_parse_total_count_returns_zero_on_missing():
    soup = make_soup("<html><body></body></html>")
    assert parse_total_count(soup) == 0


# ── parse_jobs ────────────────────────────────────────────────────────────────

def test_parse_jobs_returns_list():
    soup = make_soup(_minimal_serp_html(jobs=[{"uuid": "abc", "title": "Verkäufer"}]))
    jobs = parse_jobs(soup)
    assert isinstance(jobs, list)

def test_parse_jobs_extracts_title():
    soup = make_soup(_minimal_serp_html(jobs=[{"uuid": "abc", "title": "Kassiererin"}]))
    jobs = parse_jobs(soup)
    assert len(jobs) == 1
    assert jobs[0].title == "Kassiererin"

def test_parse_jobs_extracts_company():
    soup = make_soup(_minimal_serp_html(jobs=[{"uuid": "abc", "company": "Coop AG"}]))
    jobs = parse_jobs(soup)
    assert jobs[0].company == "Coop AG"

def test_parse_jobs_constructs_full_url():
    soup = make_soup(_minimal_serp_html(jobs=[{"uuid": "myuuid"}]))
    jobs = parse_jobs(soup)
    assert jobs[0].url.startswith("https://www.jobs.ch")
    assert "myuuid" in jobs[0].url

def test_parse_jobs_extracts_workload():
    soup = make_soup(_minimal_serp_html(jobs=[{"uuid": "x"}]))
    jobs = parse_jobs(soup)
    assert jobs[0].workload == "80-100%"

def test_parse_jobs_empty_page():
    soup = make_soup(_minimal_serp_html(jobs=[]))
    jobs = parse_jobs(soup)
    assert jobs == []
