import re
import csv
import json
import time
import math
import argparse
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


# ─── Konfiguration ────────────────────────────────────────────────────────────

BASE_URL   = "https://www.jobs.ch"
SEARCH_URL = f"{BASE_URL}/en/vacancies/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.jobs.ch/",
}

DELAY_BETWEEN_REQUESTS = 1.0   # Sekunden zwischen Requests (höfliches Scraping)
ITEMS_PER_PAGE         = 20    # jobs.ch zeigt ~20 Jobs pro Seite


# ─── HTML-Parser ──────────────────────────────────────────────────────────────

def parse_total_count(soup: BeautifulSoup) -> int:
    """Liest die Gesamtanzahl der Stellen aus dem Seitentitel."""
    header = soup.find(attrs={"data-cy": "page-header"})
    if header:
        # z. B. "1 487 jobs in Winterthur" → 1487
        text = header.get_text(strip=True)
        numbers = re.findall(r"[\d\s']+(?=\s*jobs)", text)
        if numbers:
            clean = re.sub(r"[\s']", "", numbers[0])
            return int(clean)
    return 0


def parse_jobs(soup: BeautifulSoup) -> list[dict]:
    """Extrahiert alle Job-Karten einer Seite."""
    jobs = []
    items = soup.find_all(attrs={"data-cy": "serp-item"})

    for item in items:
        # ── Link & UUID ──────────────────────────────────────────────────
        job_link = item.find(attrs={"data-cy": "job-link"})
        if not job_link:
            continue
        href = job_link.get("href", "")
        full_url = BASE_URL + href if href.startswith("/") else href
        uuid = href.rstrip("/").split("/")[-1]

        # ── Titel ────────────────────────────────────────────────────────
        title_el = item.find("span", class_=lambda c: c and "c_purple" in c)
        title = title_el.get_text(strip=True) if title_el else ""

        # ── Alle caption-Paragraphen  ─────────────────────────────────────
        # Reihenfolge: published, location, workload, contract_type, company
        paragraphs = [
            p.get_text(strip=True)
            for p in item.find_all("p", class_=lambda c: c and "textStyle_caption1" in c)
        ]

        published     = paragraphs[0] if len(paragraphs) > 0 else ""
        location      = paragraphs[1] if len(paragraphs) > 1 else ""
        workload      = paragraphs[2] if len(paragraphs) > 2 else ""
        contract_type = paragraphs[3] if len(paragraphs) > 3 else ""
        company       = paragraphs[4] if len(paragraphs) > 4 else ""

        # ── Flags ────────────────────────────────────────────────────────
        is_promoted  = bool(item.find(attrs={"data-cy": "recommended"}))
        has_easy_apply = bool(item.find(attrs={"data-cy": "quick-apply"}))

        jobs.append({
            "uuid":          uuid,
            "title":         title,
            "company":       company,
            "location":      location,
            "workload":      workload,
            "contract_type": contract_type,
            "published":     published,
            "is_promoted":   is_promoted,
            "easy_apply":    has_easy_apply,
            "url":           full_url,
        })

    return jobs


# ─── HTTP-Helper ──────────────────────────────────────────────────────────────

def fetch_page(session: requests.Session, location: str, page: int) -> BeautifulSoup | None:
    """Lädt eine Suchergebnisseite und gibt ein BeautifulSoup-Objekt zurück."""
    params = {"location": location, "term": "", "page": page}
    try:
        response = session.get(SEARCH_URL, params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"\n⚠️  Fehler auf Seite {page}: {e}", file=sys.stderr)
        return None


# ─── Export ───────────────────────────────────────────────────────────────────

def save_csv(jobs: list[dict], path: Path) -> None:
    """Speichert die Jobs als CSV-Datei."""
    if not jobs:
        return
    fieldnames = list(jobs[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(jobs)
    print(f"✅ CSV gespeichert: {path}")


def save_json(jobs: list[dict], path: Path) -> None:
    """Speichert die Jobs als JSON-Datei."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON gespeichert: {path}")


# ─── Hauptlogik ───────────────────────────────────────────────────────────────

def scrape(location: str, max_pages: int | None = None) -> list[dict]:
    """
    Scrapet alle Jobs für die gegebene Location.

    Args:
        location:  Ortsname, z. B. "winterthur" oder "zurich"
        max_pages: Maximale Seitenanzahl (None = alle Seiten)

    Returns:
        Liste aller gescrapten Job-Dicts
    """
    all_jobs: list[dict] = []
    session = requests.Session()

    print(f"\n🔍 Starte Scraping für Location: «{location}»")
    print(f"   URL: {SEARCH_URL}?location={location}&term=\n")

    # ── Seite 1 laden, um Gesamtanzahl zu ermitteln ──────────────────────────
    soup = fetch_page(session, location, page=1)
    if soup is None:
        print("❌ Seite 1 konnte nicht geladen werden.", file=sys.stderr)
        return []

    total = parse_total_count(soup)
    if total == 0:
        print("⚠️  Keine Jobs gefunden oder Anzahl nicht lesbar.")
        return []

    total_pages = math.ceil(total / ITEMS_PER_PAGE)
    if max_pages:
        total_pages = min(total_pages, max_pages)

    print(f"📊 Gefunden: {total:,} Jobs auf ca. {total_pages} Seiten\n")

    # ── Seite 1 parsen ───────────────────────────────────────────────────────
    jobs_p1 = parse_jobs(soup)
    all_jobs.extend(jobs_p1)

    # ── Seiten 2 bis N laden ─────────────────────────────────────────────────
    with tqdm(total=total_pages, desc="Seiten", unit="Seite", initial=1) as pbar:
        for page in range(2, total_pages + 1):
            time.sleep(DELAY_BETWEEN_REQUESTS)
            soup = fetch_page(session, location, page)
            if soup is None:
                pbar.update(1)
                continue

            jobs = parse_jobs(soup)
            if not jobs:
                # Keine weiteren Jobs → vorzeitig abbrechen
                print(f"\nℹ️  Keine Jobs mehr auf Seite {page} – Scraping abgeschlossen.")
                break

            all_jobs.extend(jobs)
            pbar.update(1)
            pbar.set_postfix({"Jobs": len(all_jobs)})

    # Duplikate nach UUID entfernen (Sponsored-Jobs können doppelt vorkommen)
    seen = set()
    unique_jobs = []
    for job in all_jobs:
        if job["uuid"] not in seen:
            seen.add(job["uuid"])
            unique_jobs.append(job)

    print(f"\n✅ Scraping abgeschlossen: {len(unique_jobs):,} einzigartige Jobs gefunden")
    return unique_jobs


# ─── CLI-Einstiegspunkt ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrapet Stellenangebote von jobs.ch für eine bestimmte Location."
    )
    parser.add_argument(
        "--location", "-l",
        default="winterthur",
        help="Ort für die Jobsuche (Standard: winterthur)"
    )
    parser.add_argument(
        "--max-pages", "-m",
        type=int,
        default=None,
        help="Maximale Anzahl Seiten (Standard: alle)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=".",
        help="Ausgabeverzeichnis für CSV/JSON (Standard: aktuelles Verzeichnis)"
    )
    args = parser.parse_args()

    jobs = scrape(location=args.location, max_pages=args.max_pages)

    if not jobs:
        print("Keine Jobs zum Speichern.", file=sys.stderr)
        sys.exit(1)

    # ── Ausgabepfade ─────────────────────────────────────────────────────────
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir  = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem        = f"jobs_{args.location}_{timestamp}"

    save_csv(jobs,  output_dir / f"{stem}.csv")
    save_json(jobs, output_dir / f"{stem}.json")

    # ── Vorschau ─────────────────────────────────────────────────────────────
    print(f"\n{'─'*80}")
    print(f"{'#':<4} {'Titel':<50} {'Firma':<30} {'Pensum':<10}")
    print(f"{'─'*80}")
    for i, job in enumerate(jobs[:20], 1):
        print(f"{i:<4} {job['title'][:49]:<50} {job['company'][:29]:<30} {job['workload']:<10}")
    if len(jobs) > 20:
        print(f"     ... und {len(jobs) - 20} weitere Jobs (siehe CSV/JSON)")
    print(f"{'─'*80}\n")


if __name__ == "__main__":
    main()