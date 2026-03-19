# JobScraper

A CLI and web-based scraper for [jobs.ch](https://www.jobs.ch) (Swiss job board). Scrapes job listings by location, filters them for a **Detailhandel EFZ** (retail apprenticeship) profile, and exports results to CSV, JSON, and an interactive HTML page.

---

## Features

- Scrapes all job pages for any Swiss location on jobs.ch
- **3-stage filter pipeline**: workload threshold → keyword exclusion → keyword inclusion
- Deduplication by UUID (sponsored jobs can appear on multiple pages)
- Exports: raw CSV + JSON, filtered JSON, and a self-contained interactive HTML page
- Two interfaces: **CLI** (`JobScraper.py`) and **web UI** (`server.py`)
- Polite scraping: 1-second delay between requests

---

## Requirements

- Python 3.13+
- External packages: `requests`, `beautifulsoup4`, `tqdm`
- For the web UI additionally: `flask`

---

## Setup

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install requests beautifulsoup4 tqdm

# For the web UI
pip install flask
```

---

## Usage

### CLI

```bash
source .venv/bin/activate

# Basic usage — scrapes Winterthur, all pages, saves to ./results and ./filtered_results
python3 JobScraper.py

# Specify a location
python3 JobScraper.py --location zurich

# Limit pages (useful for testing — each page adds ~1 second)
python3 JobScraper.py --location bern --max-pages 5

# Custom output directories
python3 JobScraper.py --output-dir ./raw --filtered-dir ./filtered

# Scrape only, skip filtering and HTML generation
python3 JobScraper.py --no-filter

# Suppress per-job filter log output
python3 JobScraper.py --quiet
```

#### All CLI flags

| Flag | Short | Default | Description |
|---|---|---|---|
| `--location` | `-l` | `winterthur` | City/region to search |
| `--max-pages` | `-m` | all pages | Maximum pages to scrape |
| `--output-dir` | `-o` | `results/` | Directory for raw CSV + JSON |
| `--filtered-dir` | | `filtered_results/` | Directory for filtered JSON + HTML |
| `--no-filter` | | off | Scrape only, no filtering or HTML |
| `--quiet` | `-q` | off | Suppress verbose filter output |

---

### Web UI

```bash
source .venv/bin/activate
python3 server.py
```

Opens `http://localhost:5001` in your browser automatically. From there:

1. Enter a location (e.g. `winterthur`, `zurich`, `bern`)
2. Optionally set a page limit
3. Click **Stellen suchen** — a live progress bar tracks scraping and filtering in real time
4. When done, click **Stellen ansehen** to open the generated HTML results page

Only one scrape job can run at a time. Press **Ctrl+C** in the terminal to stop the server.

---

## Output Files

After each run the following files are created (all filenames include a timestamp):

| File | Location | Contents |
|---|---|---|
| `jobs_{location}_{timestamp}.csv` | `results/` | Raw scraped jobs |
| `jobs_{location}_{timestamp}.json` | `results/` | Raw scraped jobs |
| `jobs_{location}_{timestamp}_filtered.json` | `filtered_results/` | Filtered jobs |
| `jobs_{location}_{timestamp}.html` | `filtered_results/` | Interactive results page |

Open the `.html` file directly in any browser — no server needed.

---

## Filter Pipeline

The filter runs automatically after scraping (unless `--no-filter` is passed):

1. **Workload filter** — keeps only jobs with a maximum workload ≥ 80%
2. **Keyword exclusion** — removes jobs whose title contains any of the configured `EXCLUDE_KEYWORDS` (medical, engineering, IT, management roles, apprenticeships, internships, etc.)
3. **Relevance check** — keeps only jobs whose title contains at least one `INCLUDE_KEYWORD` (retail, warehouse/logistics, sales, gastronomy, housekeeping, entry-level)
4. **Deduplication** — removes title-level duplicates from the filtered set

The filter configuration is at the top of `JobScraper.py` (lines 50–215) and can be customised by editing `EXCLUDE_KEYWORDS`, `INCLUDE_KEYWORDS`, and `MANUAL_EXCLUDE_TITLES`.

---

## Job Categories

Filtered jobs are automatically assigned one of five categories:

| Category | Jobs included |
|---|---|
| Retail & Detailhandel | Supermarkets, cashiers, store staff (Migros, Coop, Volg…) |
| Lager & Logistik | Warehouse, logistics, courier, postal |
| Verkauf & Kundenberatung | Sales advisors, customer service, front office |
| Gastronomie & Service | Restaurants, cafés, kitchen staff, bar |
| Quereinstieg / Offen | Career changers and general entry-level positions |

---

## Interactive HTML Page

The generated HTML file is fully self-contained and works offline. It includes:

- **Category filter buttons** — show only one category at a time
- **Easy Apply filter** — show only jobs with a one-click application option
- **Live search** — filter by job title or company name
- **Job cards** with title, company, location, workload, contract type, and a direct link to jobs.ch
- Stats strip: total reviewed, Easy Apply count, category count, explicit Quereinstieg count

---

## Project Structure

```
JobScraper.py        Main scraper, filter, HTML generator, and CLI entry point
server.py            Flask web UI with Server-Sent Events progress tracking
results/             Raw CSV + JSON output (created on first run)
filtered_results/    Filtered JSON + HTML output (created on first run)
.venv/               Python virtual environment (not committed)
```

---

## Notes

- jobs.ch displays approximately 20 jobs per page.
- Winterthur typically has ~70–80 pages (~1,400–1,600 jobs).
- The scraper uses a 1-second delay between page requests to be polite to the server.
- No `.gitignore` is present — avoid committing the `.venv/` directory or output files.
