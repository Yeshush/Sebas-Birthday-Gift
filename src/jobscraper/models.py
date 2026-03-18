"""Pydantic models for type-safe job data throughout the pipeline."""

from __future__ import annotations

from pydantic import BaseModel, HttpUrl, field_validator, model_validator


class Job(BaseModel):
    uuid:          str
    title:         str
    company:       str
    location:      str
    workload:      str
    contract_type: str
    published:     str
    is_promoted:   bool
    easy_apply:    bool
    url:           str

    # Added by filter pipeline
    company_clean: str | None = None
    category:      str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not str(v).startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http(s)://: {v!r}")
        return str(v)

    def model_dump_str(self) -> dict:
        """Dump to a plain dict with all values as strings (for CSV export)."""
        return {k: str(v) if v is not None else "" for k, v in self.model_dump().items()}


class FilterStats(BaseModel):
    total:               int = 0
    excluded_workload:   int = 0
    excluded_keyword:    int = 0
    excluded_no_match:   int = 0
    duplicates_removed:  int = 0
    kept:                int = 0
