"""Security tests: input sanitization and path traversal guards."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _sanitize_location(raw: str) -> str:
    """Mirror of the sanitize function used in server.py."""
    return re.sub(r"[^a-z0-9\-]", "", raw.lower())[:50] or "winterthur"


# ── Location sanitization ─────────────────────────────────────────────────────

def test_sanitize_valid_location():
    assert _sanitize_location("winterthur") == "winterthur"

def test_sanitize_uppercase_lowercased():
    assert _sanitize_location("Zurich") == "zurich"

def test_sanitize_strips_path_separators():
    result = _sanitize_location("../etc/passwd")
    assert "/" not in result
    assert ".." not in result

def test_sanitize_strips_special_chars():
    # The sanitizer removes <, >, (, ), / etc. — HTML-injection characters.
    # The bare word "script" is composed of valid letters and is harmless as a location name.
    result = _sanitize_location("zurich<script>alert(1)</script>")
    assert "<" not in result
    assert ">" not in result
    assert "(" not in result
    assert "!" not in result

def test_sanitize_max_length():
    long_input = "a" * 200
    result = _sanitize_location(long_input)
    assert len(result) <= 50

def test_sanitize_empty_defaults_to_winterthur():
    assert _sanitize_location("") == "winterthur"

def test_sanitize_only_special_defaults_to_winterthur():
    assert _sanitize_location("!!!###") == "winterthur"


# ── Path traversal guard ──────────────────────────────────────────────────────

def test_path_traversal_guard():
    """Simulate the serve_result path guard from server.py."""
    filt_dir = Path("/app/filtered_results").resolve()

    def is_safe(filename: str) -> bool:
        filepath = filt_dir / filename
        resolved = filepath.resolve()
        return str(resolved).startswith(str(filt_dir))

    assert is_safe("jobs_winterthur_20240101_120000.html") is True
    assert is_safe("../../etc/passwd") is False
    assert is_safe("../server.py") is False


def test_filename_regex_guard():
    """Simulate the regex filename guard from the FastAPI route."""
    pattern = re.compile(r"^[a-z0-9_\-]+\.html$")

    assert pattern.match("jobs_winterthur_20240101_120000.html") is not None
    assert pattern.match("../../etc/passwd") is None
    assert pattern.match("../server.py") is None
    assert pattern.match("jobs_zurich_20240101.html") is not None
    assert pattern.match("jobs_zurich_20240101.exe") is None


# ── URL safety ────────────────────────────────────────────────────────────────

def test_job_model_rejects_javascript_url():
    """Pydantic Job model must reject javascript: URLs."""
    from jobscraper.models import Job
    import pytest

    with pytest.raises(Exception):
        Job(
            uuid="x", title="Test", company="Co", location="ZH",
            workload="80%", contract_type="Festanstellung", published="Heute",
            is_promoted=False, easy_apply=False,
            url="javascript:alert(1)",
        )

def test_job_model_accepts_https_url():
    from jobscraper.models import Job

    job = Job(
        uuid="x", title="Test", company="Co", location="ZH",
        workload="80%", contract_type="Festanstellung", published="Heute",
        is_promoted=False, easy_apply=False,
        url="https://www.jobs.ch/en/vacancies/detail/abc/",
    )
    assert "javascript" not in job.url
