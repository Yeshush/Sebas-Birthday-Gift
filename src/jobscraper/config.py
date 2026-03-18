"""Load and expose filter configuration from config.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from functools import lru_cache

# Location of config.toml — sits at project root, two levels above this file
_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.toml"


@lru_cache(maxsize=1)
def load_config() -> dict:
    """Load config.toml once and cache it."""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"config.toml not found at {_CONFIG_PATH}. "
            "Copy config.toml to the project root and try again."
        )
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def get_min_workload() -> int:
    cfg = load_config()
    return cfg["filter"]["min_workload_percent"]


def get_exclude_keywords() -> list[str]:
    """Flatten all exclude keyword groups into a single list."""
    cfg = load_config()
    groups = cfg["filter"]["exclude_keywords"]
    result: list[str] = []
    for keywords in groups.values():
        result.extend(keywords)
    return result


def get_manual_exclude_titles() -> list[str]:
    cfg = load_config()
    return cfg["filter"]["manual_exclude_titles"]["titles"]


def get_include_keywords() -> list[str]:
    """Flatten all include keyword groups into a single list."""
    cfg = load_config()
    groups = cfg["filter"]["include_keywords"]
    result: list[str] = []
    for keywords in groups.values():
        result.extend(keywords)
    return result
