# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JobScraper is a CLI web scraper for [jobs.ch](https://www.jobs.ch) (a Swiss job board). It scrapes job listings by location, extracts structured data, and exports results to CSV and JSON.

## Running the Scraper

```bash
# Activate virtual environment first
source .venv/bin/activate

# Basic usage (defaults to winterthur, all pages, current directory output)
python3 JobScraper.py

# With options
python3 JobScraper.py --location zurich --max-pages 5 --output-dir ./results

# Short flags
python3 JobScraper.py -l bern -m 3 -o ./output
```

## Dependencies

Dependencies are not tracked in a requirements file. The venv at `.venv/` uses Python 3.13. External packages required:
- `requests` — HTTP client
- `beautifulsoup4` — HTML parsing
- `tqdm` — progress bars

Install with: `pip install requests beautifulsoup4 tqdm`

## Architecture

Single-file application (`JobScraper.py`) organized into logical sections:

- **Configuration (lines 16–33):** Constants for base URL, headers, delay, and items-per-page.
- **HTML Parsers (lines 36–99):** `parse_total_count()` extracts total job count; `parse_jobs()` extracts individual job cards. Uses `data-cy` attributes as primary selectors (stable testing hooks).
- **HTTP Helper (lines 102–113):** `fetch_page()` wraps requests with error handling, returns a BeautifulSoup object or None.
- **Export (lines 116–134):** `save_csv()` and `save_json()` write timestamped output files.
- **Scraper (lines 139–205):** `scrape()` orchestrates pagination, deduplication by UUID (sponsored jobs repeat), and polite 1-second delays.
- **CLI (lines 210–245):** `main()` via argparse; prints a preview table of the first 20 results.

## Key Implementation Notes

- Selectors use `data-cy` attributes (e.g., `[data-cy="serp-item"]`, `[data-cy="job-link"]`) — prefer these when updating parsers.
- Deduplication is UUID-based; sponsored/promoted jobs can appear on multiple pages.
- Output filenames are timestamped: `jobs_{location}_{YYYYMMDD_HHMMSS}.{csv,json}`.
- No `.gitignore` exists — avoid committing venv or output files.
