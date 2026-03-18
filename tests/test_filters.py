"""Tests for the 4-stage filter pipeline."""

import sys
from pathlib import Path

# Add src to path so imports work without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jobscraper.filters import (
    assign_category,
    filter_jobs,
    is_excluded,
    is_included,
    parse_workload,
    workload_ok,
)
from jobscraper.models import Job


def _job(**kwargs) -> Job:
    defaults = dict(
        uuid="test-uuid",
        title="Verkäufer/in",
        company="Migros AG",
        location="Winterthur",
        workload="80-100%",
        contract_type="Festanstellung",
        published="Heute",
        is_promoted=False,
        easy_apply=False,
        url="https://www.jobs.ch/en/vacancies/detail/abc/",
    )
    defaults.update(kwargs)
    return Job(**defaults)


# ── parse_workload ─────────────────────────────────────────────────────────────

def test_parse_workload_range():
    assert parse_workload("80 – 100%") == (80, 100)

def test_parse_workload_single():
    assert parse_workload("100%") == (100, 100)

def test_parse_workload_hyphen():
    assert parse_workload("80-100%") == (80, 100)

def test_parse_workload_empty():
    assert parse_workload("") == (0, 0)

def test_parse_workload_garbage():
    assert parse_workload("vollzeit") == (0, 0)


# ── workload_ok ────────────────────────────────────────────────────────────────

def test_workload_ok_accepts_80():
    assert workload_ok("80-100%") is True

def test_workload_ok_accepts_100():
    assert workload_ok("100%") is True

def test_workload_ok_rejects_60():
    assert workload_ok("40-60%") is False

def test_workload_ok_rejects_empty():
    assert workload_ok("") is False


# ── is_excluded ────────────────────────────────────────────────────────────────

def test_exclude_engineering():
    excluded, reason = is_excluded("Software Entwickler")
    assert excluded is True
    assert "software" in reason.lower() or "entwickler" in reason.lower()

def test_exclude_medical():
    excluded, _ = is_excluded("Facharzt für Innere Medizin")
    assert excluded is True

def test_exclude_manual_title():
    excluded, reason = is_excluded("Werkstattmitarbeiter")
    assert excluded is True
    assert "werkstattmitarbeiter" in reason.lower()

def test_no_exclude_retail():
    excluded, _ = is_excluded("Verkäufer/in Detailhandel")
    assert excluded is False


# ── is_included ────────────────────────────────────────────────────────────────

def test_include_verkauf():
    included, reason = is_included("Verkäuferin Teilzeit")
    assert included is True

def test_include_lager():
    included, _ = is_included("Lagerist 80-100%")
    assert included is True

def test_include_migros():
    included, _ = is_included("Mitarbeiter Migros Filiale")
    assert included is True

def test_not_included_random():
    included, _ = is_included("Quantenphysiker")
    assert included is False


# ── assign_category ────────────────────────────────────────────────────────────

def test_category_retail():
    assert assign_category("Kassiererin Detailhandel") == "retail"

def test_category_lager():
    assert assign_category("Lagerist 100%") == "lager"

def test_category_verkauf():
    assert assign_category("Kundenberater Verkauf") == "verkauf"

def test_category_gastro():
    assert assign_category("Servicemitarbeiter Restaurant") == "gastro"

def test_category_quereinstieg():
    assert assign_category("Allrounder gesucht") == "quereinstieg"


# ── filter_jobs pipeline ───────────────────────────────────────────────────────

def test_filter_excludes_low_workload():
    jobs = [_job(workload="40-60%"), _job(workload="80-100%")]
    filtered, stats = filter_jobs(jobs, verbose=False)
    assert stats.excluded_workload == 1
    assert stats.total == 2

def test_filter_excludes_keyword():
    jobs = [_job(title="Software Entwickler", workload="80-100%"),
            _job(title="Verkäufer/in", workload="80-100%")]
    filtered, stats = filter_jobs(jobs, verbose=False)
    assert stats.excluded_keyword >= 1

def test_filter_keeps_relevant_job():
    jobs = [_job(title="Verkäufer/in Detailhandel", workload="80-100%")]
    filtered, stats = filter_jobs(jobs, verbose=False)
    assert stats.kept == 1
    assert len(filtered) == 1

def test_filter_deduplicates_by_title():
    jobs = [
        _job(title="Kassiererin 80%", uuid="uuid-1"),
        _job(title="kassiererin 80%", uuid="uuid-2"),
    ]
    filtered, stats = filter_jobs(jobs, verbose=False)
    assert stats.duplicates_removed == 1
    assert len(filtered) == 1

def test_filter_enriches_with_category():
    jobs = [_job(title="Verkäufer/in Detailhandel", workload="80-100%")]
    filtered, _ = filter_jobs(jobs, verbose=False)
    assert filtered[0].category is not None

def test_filter_enriches_with_company_clean():
    jobs = [_job(title="Verkäufer/in Detailhandel", workload="80-100%",
                 company="Is this job relevant to you?")]
    filtered, _ = filter_jobs(jobs, verbose=False)
    assert filtered[0].company_clean == "Unbekannt"
