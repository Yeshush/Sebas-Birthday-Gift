"""
JobScraper.py
=============
Scrapt Stellenangebote von jobs.ch, filtert sie für einen Detailhandel-EFZ-Kandidaten
und generiert automatisch eine interaktive HTML-Seite mit den Ergebnissen.

Verwendung:
    python3 JobScraper.py [--location LOCATION] [--max-pages N]
                         [--output-dir DIR] [--filtered-dir DIR]
                         [--no-filter] [--quiet]
"""

import re
import csv
import json
import time
import math
import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


# ─── 1. SCRAPER CONFIG ────────────────────────────────────────────────────────

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

DELAY_BETWEEN_REQUESTS = 1.0   # Sekunden zwischen Requests
ITEMS_PER_PAGE         = 20    # jobs.ch zeigt ~20 Jobs pro Seite


# ─── 2. FILTER CONFIG ─────────────────────────────────────────────────────────

MIN_WORKLOAD_PERCENT = 80

EXCLUDE_KEYWORDS = [
    # Medizin & Pflege
    "arzt", "ärztin", "medizin", "pflege", "pflegefach", "spitex",
    "chirurgie", "radiologie", "neurochirurgie", "pädiatrie", "urologie",
    "facharzt", "oberarzt", "assistenzarzt", "ergotherap", "psycholog",
    "nachsorge", "sozialberatung",
    # Technik & Ingenieurwesen
    "ingenieur", "software", "entwickler", "programm",
    "cnc", "elektroniker", "elektroinstallateur",
    "polymechaniker", "polymech", "mechatroniker",
    "embedded", "firmware", "maschineningenieur",
    "produktionsmechaniker", "automatikmonteur", "automatiker",
    "metallbauer", "sanitärinstallateur",
    "zimmermann", "zimmerin", "montage-elektriker",
    "techniker / mechaniker für feinmechanische",
    # Chemie & Labor
    "chemiker", "laborant", " qc ", "compliance manager",
    # Finanzen & Recht
    "treuhänder", "buchhalter", "buchhal", "steuer",
    "anwalt", "jurist", "notar",
    "underwriter", "risk manager",
    # Bau & Architektur
    "architekt", "bauzeichner", "bauingenieur",
    "bauleiter", "bauleitende", "baupolier",
    # IT & Data
    "bi data", "data engineer", "rpa", "applikation", "erp consultant",
    "it perimeter", "ict infrastructure", "security consultant",
    "it allrounder", "it service",
    # Aus- & Weiterbildung
    "unterassistent", "berufsschullehrperson", "professor",
    # Behörde & Sicherheit
    "polizist", "polizei",
    # Recruiting & HR
    "recruiter", "recruiting consultant",
    # Planung
    "sanitärplan", "heizung", "haustechnik",
    "disponent strassentransport",
    # Kosmetik
    "kosmetiker",
    # Gastronomie-Führung
    "spezialkoch", "küchenchef", "leitung küche", "betriebsleiter",
    # Führungspositionen
    "teamleiter", "teamlead", "teamleader",
    "standortleiter", "gebietsverkaufsleiter",
    "verkaufsleiter", "abteilungsleiter", "produktionsleiter",
    "facility management",
    # Fahrzeuge
    "lkw-chauffeur", "chauffeur kat. c", "chauffeur/springer",
    # Fachberufe
    "gärtner efz", "maler",
    "schreiner", "zimmerer",
    "moto", "motorrad",
    # Wissenschaft
    "wissenschaftl",
    # Ausbildungsstellen
    "lehrstelle", "lernende", "lernender",
    # Praktika
    "praktikum", "praktikant",
    # Voluntariat
    "freiwillige",
    # Saisonal
    "sommersaison", "badangestellte",
    # Immobilien
    "immobilienmakler", "immobilienbewirtschafter",
]

INCLUDE_KEYWORDS = [
    # Detailhandel
    "detailhandel", "filial", "laden", "shop",
    "markt", "supermarkt", "lebensmittel",
    "migros", "coop", "volg", "otto",
    "kassierer", "kassier", "kassiererin",
    "warenbewirtschaft", "warenverräumer",
    # Verkauf & Kundenkontakt
    "verkauf", "verkäufer", "verkaufsmitarbeiter",
    "verkaufsberater", "verkaufsspezialist",
    "kundenberater", "kundendienst", "kundenbetreuung",
    "kundenservice", "kundendienstberater",
    "assistenz verkauf", "sales assistant",
    # Lager & Logistik
    "lager", "lagerist", "lagerplatz",
    "logistik", "logistiker",
    "magazin", "kommissionier",
    "auslieferung", "betriebsunterhalt",
    "kurierdienst", "postdienst",
    # Gastronomie & Service
    "gastro", "restaurant", "café", "cafe",
    "servicemitarbeiter", "servicefachangestellte",
    "bar", "crew",
    "küche", "koch", "köchin",
    # Hauswirtschaft & Reinigung
    "hauswirtschaft", "reinigung", "reiniger",
    # Einstiegsstellen
    "mitarbeiter", "mitarbeiterin",
    "hilfskraft", "aushilfe", "allrounder",
    "telemarketing", "frontoffice",
    # Quereinstieg
    "quereinstieg", "quereinsteiger",
]

MANUAL_EXCLUDE_TITLES = [
    "fachperson operationslagerung",
    "motorrad aufbereiter",
    "motorrad verkaufsberater",
    "autoersatzteileverkäufer",
    "kundendienstberater werkstatt",
    "detailhandelsfachperson efz, autoteile",
    "verkäufer ersatzteile",
    "fachberatung ausstellung sanitär",
    "verkäufer*in hlkks",
    "projektleiter elektro",
    "projektleiter/in privatkundenverkauf",
    "badplanung",
    "frischefachberatung",
    "kaufm. sachbearbeiter",
    "sachbearbeiter:in kundendienst",
    "sachbearbeiter kundendienst",
    "digitale kundenberatung mit pioniergeist – (senior)",
    "immobilienvermarkter",
    "it allrounder mit support",
    "werkstattmitarbeiter",
    "mitarbeiter:in facility",
    "mitarbeiter:in abgleich und löten",
    "produktionsplaner",
    "sachbearbeiter:in lieferantenqualit",
    "mitarbeiter/in treuhand",
    "kaufmännische:r mitarbeiter",
    "mitarbeiterin backoffice",
    "trading assistant",
    "abteilungsleiter sensorproduktion",
    "kkw-revisionsmitarbeiter",
    "mitarbeiter/in disposition",
    "vorarbeiter/-in holzkistenproduktion",
    "fachfrau:mann hotellerie-hauswirtschaft efz (fortsetzungslehre",
    "lernende:r detailhandelsfachmann",
    "lernende logistikerin",
    "lernende in systemgastronomie",
    "systemgastronomiepraktiker",
    "systemgastronomiefachfrau:mann",
    "detailhandelsfachfrau:mann efz «gestalten von einkaufserlebnissen»",
    "detailhandelsfachfrau:mann / -assistent",
    "lehrstelle als detailhandelsfachfrau",
    "fachperson hauswirtschaft efz 80%",
    "chauffeur / chauffeuse kat. c",
    "chauffeur kat. c/e",
    "lkw-chauffeur",
    "kassiererin (w/m/d)",
    "aushilfe an warentagen",
    "verkaufsberaterin non food (w/m/d)",
    "praktikum hauswirtschaft",
    "praktikum küche",
    "mitarbeiter*in hauswirtschaft 50",
    "fachfrau/-mann hauswirtschaft efz (60 - 80%)",
    "lagerist / chauffeur",
    "servicemitarbeiter/in sommersaison",
    "aushilfe badangestellte",
    "aushilfe reinigung / office",
    "aushilfe service",
    "aushilfe event",
    "fachkraft reinigung 100%",
    "aspirant",
    "security consultant",
]


# ─── 3. HTML-PARSER ───────────────────────────────────────────────────────────

def parse_total_count(soup: BeautifulSoup) -> int:
    """Liest die Gesamtanzahl der Stellen aus dem Seitentitel."""
    header = soup.find(attrs={"data-cy": "page-header"})
    if header:
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
        job_link = item.find(attrs={"data-cy": "job-link"})
        if not job_link:
            continue
        href = job_link.get("href", "")
        full_url = BASE_URL + href if href.startswith("/") else href
        uuid = href.rstrip("/").split("/")[-1]

        title_el = item.find("span", class_=lambda c: c and "c_purple" in c)
        title = title_el.get_text(strip=True) if title_el else ""

        paragraphs = [
            p.get_text(strip=True)
            for p in item.find_all("p", class_=lambda c: c and "textStyle_caption1" in c)
        ]

        published     = paragraphs[0] if len(paragraphs) > 0 else ""
        location      = paragraphs[1] if len(paragraphs) > 1 else ""
        workload      = paragraphs[2] if len(paragraphs) > 2 else ""
        contract_type = paragraphs[3] if len(paragraphs) > 3 else ""
        company       = paragraphs[4] if len(paragraphs) > 4 else ""

        is_promoted    = bool(item.find(attrs={"data-cy": "recommended"}))
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


# ─── 4. HTTP HELPER ───────────────────────────────────────────────────────────

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


# ─── 5. EXPORT ────────────────────────────────────────────────────────────────

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


# ─── 6. SCRAPER LOGIC ─────────────────────────────────────────────────────────

def scrape(location: str, max_pages: int | None = None,
           progress_fn=None) -> list[dict]:
    """
    Scrapet alle Jobs für die gegebene Location.

    Args:
        location:    Ortsname, z. B. "winterthur" oder "zurich"
        max_pages:   Maximale Seitenanzahl (None = alle Seiten)
        progress_fn: Optionaler Callback(event, **kwargs) für die Web-UI.
                     Wenn gesetzt, wird tqdm deaktiviert.

    Returns:
        Liste aller gescrapten Job-Dicts
    """
    all_jobs: list[dict] = []
    session = requests.Session()

    print(f"\n🔍 Starte Scraping für Location: «{location}»")
    print(f"   URL: {SEARCH_URL}?location={location}&term=\n")

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

    if progress_fn:
        progress_fn("found", total=total, total_pages=total_pages, location=location)

    jobs_p1 = parse_jobs(soup)
    all_jobs.extend(jobs_p1)

    if progress_fn:
        # Callback-Modus: kein tqdm, stattdessen progress_fn pro Seite
        for page in range(2, total_pages + 1):
            time.sleep(DELAY_BETWEEN_REQUESTS)
            progress_fn("page", page=page, total_pages=total_pages, jobs_so_far=len(all_jobs))
            soup = fetch_page(session, location, page)
            if soup is None:
                continue
            jobs = parse_jobs(soup)
            if not jobs:
                break
            all_jobs.extend(jobs)
    else:
        with tqdm(total=total_pages, desc="Seiten", unit="Seite", initial=1) as pbar:
            for page in range(2, total_pages + 1):
                time.sleep(DELAY_BETWEEN_REQUESTS)
                soup = fetch_page(session, location, page)
                if soup is None:
                    pbar.update(1)
                    continue

                jobs = parse_jobs(soup)
                if not jobs:
                    print(f"\nℹ️  Keine Jobs mehr auf Seite {page} – Scraping abgeschlossen.")
                    break

                all_jobs.extend(jobs)
                pbar.update(1)
                pbar.set_postfix({"Jobs": len(all_jobs)})

    seen = set()
    unique_jobs = []
    for job in all_jobs:
        if job["uuid"] not in seen:
            seen.add(job["uuid"])
            unique_jobs.append(job)

    print(f"\n✅ Scraping abgeschlossen: {len(unique_jobs):,} einzigartige Jobs gefunden")
    if progress_fn:
        progress_fn("scrape_done", jobs=len(unique_jobs))
    return unique_jobs


# ─── 7. FILTER FUNKTIONEN ─────────────────────────────────────────────────────

def parse_workload(workload_str: str) -> tuple[int, int]:
    """Parst Pensum-Strings wie '80 – 100%', '100%'. Gibt (min, max) zurück."""
    if not workload_str:
        return (0, 0)
    cleaned = workload_str.lower().replace('%', '').replace(' ', '')
    for sep in ['–', '-']:
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


def workload_ok(workload_str: str) -> bool:
    """Gibt True zurück wenn das maximale Pensum >= MIN_WORKLOAD_PERCENT."""
    _, max_w = parse_workload(workload_str)
    return max_w >= MIN_WORKLOAD_PERCENT


def is_excluded(title: str) -> tuple[bool, str]:
    """Prüft ob der Titel ein Ausschluss-Keyword enthält."""
    tl = title.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in tl:
            return True, f"Ausschluss-Keyword: '{kw}'"
    for manual in MANUAL_EXCLUDE_TITLES:
        if manual in tl:
            return True, f"Manueller Ausschluss: '{manual}'"
    return False, ""


def is_included(title: str) -> tuple[bool, str]:
    """Prüft ob der Titel ein Inklusions-Keyword enthält."""
    tl = title.lower()
    for kw in INCLUDE_KEYWORDS:
        if kw in tl:
            return True, f"Inklusions-Keyword: '{kw}'"
    return False, ""


def assign_category(title: str) -> str:
    """Weist einem Job einen kurzen Kategorie-Key zu basierend auf dem Titel."""
    tl = title.lower()
    if any(k in tl for k in ['detailhandel', 'filial', 'laden', 'markt', 'coop', 'migros',
                               'volg', 'food', 'non-food', 'kassi', 'crew', 'otto']):
        return 'retail'
    if any(k in tl for k in ['lager', 'logistik', 'magazin', 'auslieferung',
                               'betriebsunterhalt', 'kurier', 'postdienst']):
        return 'lager'
    if any(k in tl for k in ['verkauf', 'verkäufer', 'kundenberater', 'kundenberatung',
                               'kundendienst', 'beratung', 'sales', 'versicherung',
                               'telemarketing', 'frontoffice', 'assistenz']):
        return 'verkauf'
    if any(k in tl for k in ['service', 'gastro', 'restaurant', 'küche', 'bar',
                               'koch', 'köchin']):
        return 'gastro'
    return 'quereinstieg'


def fix_company(job: dict) -> str:
    """Bereinigt den Firmennamen (jobs.ch-Workaround für versteckte Firmen)."""
    company = job.get('company', '')
    if company == 'Is this job relevant to you?':
        ct = job.get('contract_type', '')
        standard = {'Permanent position', 'Festanstellung', 'Internship', 'Temporary', 'Temporär'}
        if ct and ct not in standard and len(ct) > 3:
            return ct
        return 'Unbekannt'
    return company


def filter_jobs(jobs: list[dict], verbose: bool = True,
                progress_fn=None) -> tuple[list[dict], dict]:
    """Filtert die Job-Liste und gibt (gefilterte_jobs, statistiken) zurück."""
    stats = {
        'total': len(jobs),
        'excluded_workload': 0,
        'excluded_keyword': 0,
        'excluded_no_match': 0,
        'duplicates_removed': 0,
        'kept': 0,
    }

    step1_workload = []
    step2_keywords = []
    step3_relevant = []

    # SCHRITT 1: Pensum-Filter
    for job in jobs:
        if workload_ok(job.get('workload', '')):
            step1_workload.append(job)
        else:
            stats['excluded_workload'] += 1
            if verbose:
                print(f"  [Pensum] Ausgeschlossen: {job['title'][:60]} ({job.get('workload','')})")

    if verbose:
        print(f"\n✓ Nach Pensum-Filter: {len(step1_workload)} verbleibend "
              f"({stats['excluded_workload']} ausgeschlossen)\n")
    if progress_fn:
        progress_fn("stage", stage="workload",
                    remaining=len(step1_workload), excluded=stats['excluded_workload'])

    # SCHRITT 2: Ausschluss-Keywords
    for job in step1_workload:
        excluded, grund = is_excluded(job.get('title', ''))
        if not excluded:
            step2_keywords.append(job)
        else:
            stats['excluded_keyword'] += 1
            if verbose:
                print(f"  [Keyword-Ausschluss] {job['title'][:60]} → {grund}")

    if verbose:
        print(f"\n✓ Nach Keyword-Ausschluss: {len(step2_keywords)} verbleibend "
              f"({stats['excluded_keyword']} ausgeschlossen)\n")
    if progress_fn:
        progress_fn("stage", stage="keywords",
                    remaining=len(step2_keywords), excluded=stats['excluded_keyword'])

    # SCHRITT 3: Relevanz-Check
    for job in step2_keywords:
        included, _ = is_included(job.get('title', ''))
        if included:
            step3_relevant.append(job)
        else:
            stats['excluded_no_match'] += 1
            if verbose:
                print(f"  [Kein Match] Ausgeschlossen: {job['title'][:60]}")

    if verbose:
        print(f"\n✓ Nach Relevanz-Check: {len(step3_relevant)} verbleibend "
              f"({stats['excluded_no_match']} ausgeschlossen)\n")
    if progress_fn:
        progress_fn("stage", stage="relevance",
                    remaining=len(step3_relevant), excluded=stats['excluded_no_match'])

    # SCHRITT 4: Deduplizierung (nach Titel)
    seen_titles: set[str] = set()
    deduplicated = []
    for job in step3_relevant:
        key = job.get('title', '').lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            job['company_clean'] = fix_company(job)
            job['category'] = assign_category(job.get('title', ''))
            deduplicated.append(job)
        else:
            stats['duplicates_removed'] += 1
            if verbose:
                print(f"  [Duplikat] Entfernt: {job['title'][:60]}")

    stats['kept'] = len(deduplicated)
    if progress_fn:
        progress_fn("stage", stage="dedup", kept=stats['kept'])
    return deduplicated, stats


_CAT_LABELS = {
    'retail':       'Retail & Detailhandel',
    'lager':        'Lager & Logistik',
    'verkauf':      'Verkauf & Kundenberatung',
    'gastro':       'Gastronomie & Service',
    'quereinstieg': 'Quereinstieg / Offen',
}


def print_summary(jobs: list[dict], stats: dict) -> None:
    """Gibt eine übersichtliche Zusammenfassung aus."""
    print("\n" + "═" * 60)
    print("  FILTER-RESULTAT")
    print("═" * 60)
    print(f"  Gesamte Jobs geprüft:      {stats['total']:>6}")
    print(f"  Pensum zu niedrig:         {stats['excluded_workload']:>6}")
    print(f"  Fachausbildung nötig:      {stats['excluded_keyword']:>6}")
    print(f"  Kein Relevanz-Match:       {stats['excluded_no_match']:>6}")
    print(f"  Duplikate entfernt:        {stats['duplicates_removed']:>6}")
    print(f"  {'─'*33}")
    print(f"  PASSENDE STELLEN:          {stats['kept']:>6}")
    print("═" * 60)

    cats = Counter(j['category'] for j in jobs)
    print("\n  NACH KATEGORIE:")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        label = _CAT_LABELS.get(cat, cat)
        print(f"    {label:<30} {count} Stelle{'n' if count != 1 else ''}")

    easy = sum(1 for j in jobs if j.get('easy_apply'))
    querei = sum(1 for j in jobs if 'quereinstieg' in j.get('title', '').lower())
    print(f"\n  Easy Apply verfügbar:      {easy}")
    print(f"  Quereinstieg explizit:     {querei}")
    print("═" * 60)

    print("\n  STELLEN-LISTE:")
    print("─" * 60)
    current_cat = None
    for job in sorted(jobs, key=lambda x: x['category']):
        if job['category'] != current_cat:
            current_cat = job['category']
            print(f"\n  [{_CAT_LABELS.get(current_cat, current_cat)}]")
        easy_tag = " ⚡" if job.get('easy_apply') else ""
        print(f"    • {job['title'][:50]}")
        print(f"      {job['company_clean']} | {job.get('workload','')} | {job.get('published','')}{easy_tag}")
        print(f"      {job.get('url','')}")


# ─── 8. HTML GENERATOR ────────────────────────────────────────────────────────

# NOTE: The sentinel /* %%JOBS_DATA%% */ is replaced at runtime by generate_html().
# Job data is embedded as a JSON literal (not injected into innerHTML directly).
# The JS escapeHtml() helper sanitizes all scraped strings before DOM insertion.
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stellen — Deine passenden Jobs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,700;0,9..144,900;1,9..144,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --cream: #F5F0E8; --ink: #1A1510; --rust: #C4502A; --sage: #5A7A5A;
    --gold: #C9974A; --sand: #E8DEC8; --mist: #D4CFC5; --card-bg: #FDFAF4;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--cream); color: var(--ink); font-family: 'DM Sans', sans-serif; font-weight: 300; min-height: 100vh; overflow-x: hidden; }
  body::before {
    content: ''; position: fixed; inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
    pointer-events: none; z-index: 999; opacity: 0.6;
  }
  header { padding: 4rem 5vw 3rem; border-bottom: 1px solid var(--mist); position: relative; overflow: hidden; }
  .header-eyebrow { font-size: 0.72rem; letter-spacing: 0.25em; text-transform: uppercase; color: var(--rust); font-weight: 500; margin-bottom: 1.2rem; opacity: 0; animation: fadeUp 0.6s ease forwards 0.1s; }
  h1 { font-family: 'Fraunces', serif; font-size: clamp(3rem, 8vw, 7rem); font-weight: 900; line-height: 0.95; letter-spacing: -0.03em; max-width: 14ch; opacity: 0; animation: fadeUp 0.7s ease forwards 0.2s; }
  h1 em { font-style: italic; font-weight: 300; color: var(--rust); }
  .header-meta { margin-top: 2.5rem; display: flex; gap: 2.5rem; align-items: center; flex-wrap: wrap; opacity: 0; animation: fadeUp 0.7s ease forwards 0.35s; }
  .meta-stat { display: flex; flex-direction: column; }
  .meta-stat strong { font-family: 'Fraunces', serif; font-size: 2.2rem; font-weight: 700; line-height: 1; color: var(--ink); }
  .meta-stat span { font-size: 0.75rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--rust); margin-top: 0.25rem; }
  .meta-divider { width: 1px; height: 3rem; background: var(--mist); }
  .filter-bar { padding: 1.5rem 5vw; background: var(--sand); border-bottom: 1px solid var(--mist); display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; opacity: 0; animation: fadeUp 0.6s ease forwards 0.5s; }
  .filter-label { font-size: 0.7rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--rust); font-weight: 500; margin-right: 0.5rem; }
  .filter-btn { padding: 0.45rem 1rem; border: 1px solid var(--mist); background: transparent; border-radius: 100px; font-family: 'DM Sans', sans-serif; font-size: 0.8rem; color: var(--ink); cursor: pointer; transition: all 0.2s ease; font-weight: 400; }
  .filter-btn:hover, .filter-btn.active { background: var(--ink); color: var(--cream); border-color: var(--ink); }
  main { padding: 3rem 5vw 6rem; }
  .jobs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 1.5rem; margin-bottom: 4rem; }
  .job-card { background: var(--card-bg); border: 1px solid var(--mist); border-radius: 4px; padding: 1.75rem; display: flex; flex-direction: column; gap: 1.1rem; position: relative; transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease; opacity: 0; animation: cardIn 0.5s ease forwards; }
  .job-card:hover { transform: translateY(-4px); box-shadow: 0 16px 40px rgba(26,21,16,0.1); border-color: var(--gold); }
  .card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
  .card-badges { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .badge { font-size: 0.62rem; letter-spacing: 0.12em; text-transform: uppercase; font-weight: 500; padding: 0.25rem 0.6rem; border-radius: 100px; white-space: nowrap; }
  .badge-easy         { background: #E8F5E9; color: #2E7D32; border: 1px solid #C8E6C9; }
  .badge-promoted     { background: #FFF8E1; color: #F57F17; border: 1px solid #FFE082; }
  .badge-quereinstieg { background: #EDE7F6; color: #4527A0; border: 1px solid #C5CAE9; }
  .badge-new          { background: #E3F2FD; color: #1565C0; border: 1px solid #BBDEFB; }
  .card-category-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 0.35rem; }
  .dot-retail { background: var(--rust); } .dot-lager { background: var(--gold); }
  .dot-verkauf { background: var(--sage); } .dot-gastro { background: #8B6E4E; }
  .dot-quereinstieg { background: #7B5EA7; }
  .card-title { font-family: 'Fraunces', serif; font-size: 1.15rem; font-weight: 700; line-height: 1.25; color: var(--ink); letter-spacing: -0.01em; }
  .card-company { font-size: 0.82rem; font-weight: 500; color: var(--rust); letter-spacing: 0.02em; }
  .card-details { display: flex; flex-direction: column; gap: 0.45rem; }
  .detail-row { display: flex; align-items: center; gap: 0.6rem; font-size: 0.8rem; color: #6B6155; }
  .detail-icon { font-size: 0.9rem; flex-shrink: 0; width: 1.1rem; text-align: center; }
  .card-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 1rem; border-top: 1px solid var(--sand); margin-top: auto; }
  .published-tag { font-size: 0.72rem; color: #9A8E82; letter-spacing: 0.05em; }
  .apply-btn { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.5rem 1.1rem; background: var(--ink); color: var(--cream); text-decoration: none; border-radius: 100px; font-size: 0.75rem; font-family: 'DM Sans', sans-serif; font-weight: 500; letter-spacing: 0.05em; transition: background 0.2s ease, transform 0.15s ease; }
  .apply-btn:hover { background: var(--rust); transform: scale(1.04); }
  .apply-btn .arrow { font-size: 0.7rem; transition: transform 0.2s ease; }
  .apply-btn:hover .arrow { transform: translateX(3px); }
  .category-section { margin-bottom: 3.5rem; }
  .category-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; }
  .category-dot-lg { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .category-title { font-family: 'Fraunces', serif; font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; }
  .category-subtitle { font-size: 0.75rem; color: #9A8E82; letter-spacing: 0.08em; text-transform: uppercase; margin-left: auto; }
  .job-card.featured { border-color: var(--gold); background: linear-gradient(135deg, #FDFAF4 0%, #FDF7EC 100%); }
  .job-card.featured::before { content: '\2605 Empfohlen'; position: absolute; top: -1px; left: 1.5rem; background: var(--gold); color: white; font-size: 0.6rem; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; padding: 0.2rem 0.6rem; border-radius: 0 0 4px 4px; }
  .empty-state { grid-column: 1/-1; text-align: center; padding: 4rem; color: var(--mist); font-family: 'Fraunces', serif; font-size: 1.5rem; font-style: italic; }
  footer { border-top: 1px solid var(--mist); padding: 2rem 5vw; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; background: var(--sand); }
  .footer-note { font-size: 0.75rem; color: #9A8E82; letter-spacing: 0.05em; }
  .footer-logo { font-family: 'Fraunces', serif; font-size: 1.1rem; font-weight: 700; color: var(--ink); font-style: italic; }
  .search-wrap { position: relative; flex: 1; max-width: 300px; }
  .search-input { width: 100%; padding: 0.5rem 1rem 0.5rem 2.2rem; border: 1px solid var(--mist); background: var(--cream); border-radius: 100px; font-family: 'DM Sans', sans-serif; font-size: 0.8rem; color: var(--ink); outline: none; transition: border-color 0.2s; }
  .search-input:focus { border-color: var(--rust); }
  .search-icon { position: absolute; left: 0.75rem; top: 50%; transform: translateY(-50%); font-size: 0.8rem; color: #9A8E82; }
  .stats-strip { background: var(--ink); color: var(--cream); padding: 1rem 5vw; display: flex; gap: 3rem; flex-wrap: wrap; opacity: 0; animation: fadeUp 0.6s ease forwards 0.6s; }
  .strip-stat { display: flex; align-items: center; gap: 0.5rem; font-size: 0.78rem; letter-spacing: 0.05em; }
  .strip-stat-num { font-family: 'Fraunces', serif; font-size: 1.3rem; font-weight: 700; color: var(--gold); }
  @keyframes fadeUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes cardIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
  @media (max-width: 600px) { h1 { font-size: 2.8rem; } .jobs-grid { grid-template-columns: 1fr; } .header-meta { gap: 1.5rem; } .meta-stat strong { font-size: 1.6rem; } .stats-strip { gap: 1.5rem; } }
</style>
</head>
<body>

<header>
  <div class="header-eyebrow" id="header-eyebrow">Jobsuche &middot; Detailhandel &amp; mehr</div>
  <h1>Deine <em>passenden</em><br>Stellen</h1>
  <div class="header-meta">
    <div class="meta-stat"><strong id="total-count">0</strong><span>Passende Stellen</span></div>
    <div class="meta-divider"></div>
    <div class="meta-stat"><strong id="stat-reviewed">&mdash;</strong><span>Gepr&uuml;ft</span></div>
    <div class="meta-divider"></div>
    <div class="meta-stat"><strong id="stat-location">&mdash;</strong><span>Region</span></div>
  </div>
</header>

<div class="stats-strip">
  <div class="strip-stat"><span class="strip-stat-num" id="stat-easy">&mdash;</span><span>Easy Apply m&ouml;glich</span></div>
  <div class="strip-stat"><span class="strip-stat-num">80&ndash;100%</span><span>Pensum</span></div>
  <div class="strip-stat"><span class="strip-stat-num" id="stat-cats">&mdash;</span><span>Kategorien</span></div>
  <div class="strip-stat"><span class="strip-stat-num" id="stat-querei">&mdash;</span><span>Expliziter Quereinstieg</span></div>
</div>

<div class="filter-bar">
  <span class="filter-label">Filter:</span>
  <button class="filter-btn active" onclick="filterJobs('all', this)">Alle</button>
  <button class="filter-btn" onclick="filterJobs('retail', this)">&#x1F6D2; Retail</button>
  <button class="filter-btn" onclick="filterJobs('lager', this)">&#x1F4E6; Lager &amp; Logistik</button>
  <button class="filter-btn" onclick="filterJobs('verkauf', this)">&#x1F91D; Verkauf &amp; Beratung</button>
  <button class="filter-btn" onclick="filterJobs('gastro', this)">&#x1F37D; Gastronomie</button>
  <button class="filter-btn" onclick="filterJobs('quereinstieg', this)">&#x1F504; Quereinstieg</button>
  <button class="filter-btn" onclick="filterJobs('easy', this)">&#x26A1; Easy Apply</button>
  <div class="search-wrap">
    <span class="search-icon">&#x1F50D;</span>
    <input class="search-input" type="text" placeholder="Stellenname suchen&hellip;" oninput="searchJobs(this.value)">
  </div>
</div>

<main id="main-content"></main>

<footer>
  <div class="footer-logo" id="footer-logo">Stellen</div>
  <div class="footer-note" id="footer-note">Gefiltert aus jobs.ch &middot; Detailhandel EFZ Profil</div>
</footer>

<script>
/* %%JOBS_DATA%% */

const CATEGORIES = [
  { key: 'retail',       label: '\u{1F6D2} Retail & Detailhandel',   dotClass: 'dot-retail' },
  { key: 'lager',        label: '\u{1F4E6} Lager & Logistik',         dotClass: 'dot-lager' },
  { key: 'verkauf',      label: '\u{1F91D} Verkauf & Kundenberatung', dotClass: 'dot-verkauf' },
  { key: 'gastro',       label: '\u{1F37D} Gastronomie & Service',    dotClass: 'dot-gastro' },
  { key: 'quereinstieg', label: '\u{1F504} Quereinstieg',             dotClass: 'dot-quereinstieg' },
];

const CAT_COLORS = {
  retail: '#C4502A', lager: '#C9974A', verkauf: '#5A7A5A',
  gastro: '#8B6E4E', quereinstieg: '#7B5EA7'
};

let currentFilter = 'all';
let searchQuery = '';

// Sanitize strings before DOM insertion to prevent XSS from scraped content
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function isNew(pub) {
  const newWords = ['Stunden', 'Gestern', 'Tage', 'yesterday', 'hours', 'today'];
  return newWords.some(w => pub.includes(w)) || pub === 'Last week'
    || pub.includes('5 Tage') || pub.includes('6 Tage');
}

function buildCard(job, idx, featured) {
  const delay = (idx % 6) * 0.06;
  const badges = [];
  if (job.easy_apply)                  badges.push('<span class="badge badge-easy">\u26A1 Easy Apply</span>');
  if (job.is_promoted)                 badges.push('<span class="badge badge-promoted">\u2605 Promoted</span>');
  if (job.category === 'quereinstieg') badges.push('<span class="badge badge-quereinstieg">\u{1F504} Quereinstieg</span>');
  if (isNew(job.published))            badges.push('<span class="badge badge-new">Neu</span>');

  const ct = job.contract_type || '';
  const contractLabel = (ct && ct !== 'Permanent position' && ct !== 'Festanstellung'
    && !ct.includes('AG') && !ct.includes('GmbH') && !ct.includes('SA') && !ct.includes('Sàrl'))
    ? escapeHtml(ct)
    : (ct === 'Temporär' ? '\u23F3 Temporär' : '\u{1F4CB} Festanstellung');

  const company = escapeHtml(job.company_clean || job.company || '—');
  const title   = escapeHtml(job.title);
  const loc     = escapeHtml(job.location);
  const wl      = escapeHtml(job.workload);
  const pub     = escapeHtml(job.published);
  // URL: only allow https:// links to prevent javascript: injection
  const url = (job.url && job.url.startsWith('https://')) ? job.url : '#';

  return `
    <div class="job-card${featured ? ' featured' : ''}"
         data-category="${job.category}"
         data-easy="${job.easy_apply}"
         data-title="${title.toLowerCase()}"
         data-company="${company.toLowerCase()}"
         style="animation-delay: ${delay}s">
      <div class="card-top">
        <div class="card-badges">${badges.join('')}</div>
        <div class="card-category-dot dot-${job.category}"></div>
      </div>
      <div>
        <div class="card-title">${title}</div>
        <div class="card-company">${company}</div>
      </div>
      <div class="card-details">
        <div class="detail-row"><span class="detail-icon">\u{1F4CD}</span>${loc}</div>
        <div class="detail-row"><span class="detail-icon">\u23F1</span>${wl} Pensum</div>
        <div class="detail-row"><span class="detail-icon">\u{1F4CB}</span>${contractLabel}</div>
      </div>
      <div class="card-footer">
        <span class="published-tag">Publiziert: ${pub}</span>
        <a href="${url}" target="_blank" rel="noopener noreferrer" class="apply-btn">Bewerben <span class="arrow">\u2192</span></a>
      </div>
    </div>`;
}

function renderAll() {
  const container = document.getElementById('main-content');
  let html = '';
  let totalVisible = 0;

  for (const cat of CATEGORIES) {
    const catJobs = JOBS.filter(j => j.category === cat.key);
    const visible = catJobs.filter(j => {
      const matchFilter = currentFilter === 'all'
        || currentFilter === cat.key
        || (currentFilter === 'easy' && j.easy_apply);
      const matchSearch = !searchQuery
        || (j.title && j.title.toLowerCase().includes(searchQuery))
        || (j.company_clean && j.company_clean.toLowerCase().includes(searchQuery));
      return matchFilter && matchSearch;
    });

    if (visible.length === 0) continue;
    totalVisible += visible.length;

    html += `<div class="category-section" data-cat="${cat.key}">
      <div class="category-header">
        <div class="category-dot-lg" style="background:${CAT_COLORS[cat.key]}"></div>
        <span class="category-title">${cat.label}</span>
        <span class="category-subtitle">${visible.length} Stelle${visible.length !== 1 ? 'n' : ''}</span>
      </div>
      <div class="jobs-grid">`;

    visible.forEach((job, idx) => {
      html += buildCard(job, idx, idx === 0 && currentFilter === 'all');
    });

    html += '</div></div>';
  }

  if (totalVisible === 0) {
    html = '<div class="empty-state">Keine Stellen gefunden f\u00fcr diese Auswahl.</div>';
  }

  container.innerHTML = html;
  document.getElementById('total-count').textContent = totalVisible;
}

function filterJobs(filter, btn) {
  currentFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderAll();
}

function searchJobs(val) {
  searchQuery = val.toLowerCase().trim();
  renderAll();
}

// ── Stats-DOM-Update (uses _STATS injected by generate_html) ─────────────────
document.title = 'Stellen ' + _STATS.location + ' \u2014 Deine passenden Jobs';
document.getElementById('header-eyebrow').textContent =
  'Jobsuche ' + _STATS.location + ' \u00b7 Detailhandel & mehr';
document.getElementById('stat-reviewed').textContent =
  _STATS.totalReviewed.toLocaleString('de-CH');
document.getElementById('stat-location').textContent = _STATS.location;
document.getElementById('stat-easy').textContent    = _STATS.easyCount;
document.getElementById('stat-cats').textContent    = _STATS.catCount;
document.getElementById('stat-querei').textContent  = _STATS.quereiCount;
document.getElementById('footer-logo').textContent  = 'Stellen ' + _STATS.location;
document.getElementById('footer-note').textContent  =
  'Gefiltert aus jobs.ch \u00b7 Stand ' + _STATS.generatedDate
  + ' \u00b7 Detailhandel EFZ Profil';

renderAll();
</script>
</body>
</html>"""

_DE_MONTHS = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]


def generate_html(jobs: list[dict], stats: dict, location: str, path: Path) -> None:
    """Generiert eine interaktive HTML-Seite mit den gefilterten Jobs."""
    now = datetime.now()
    generated_date = f"{now.day}. {_DE_MONTHS[now.month - 1]} {now.year}"

    easy_count   = sum(1 for j in jobs if j.get('easy_apply'))
    cat_count    = len({j['category'] for j in jobs})
    querei_count = sum(1 for j in jobs if 'quereinstieg' in j.get('title', '').lower())

    jobs_json = json.dumps(jobs, ensure_ascii=False, indent=2)
    # Prevent embedded JSON from breaking out of the <script> block
    jobs_json = jobs_json.replace('</script>', '<\\/script>')

    stats_js = (
        f"const _STATS = {{\n"
        f"  totalReviewed: {stats['total']},\n"
        f"  matchedCount:  {stats['kept']},\n"
        f"  easyCount:     {easy_count},\n"
        f"  catCount:      {cat_count},\n"
        f"  quereiCount:   {querei_count},\n"
        f"  location:      \"{location.capitalize()}\",\n"
        f"  generatedDate: \"{generated_date}\",\n"
        f"}};"
    )

    data_block = f"const JOBS = {jobs_json};\n\n{stats_js}\n"
    head, tail = HTML_TEMPLATE.split('/* %%JOBS_DATA%% */')
    path.write_text(head + data_block + tail, encoding='utf-8')
    print(f"✅ HTML gespeichert: {path}")


# ─── 9. CLI ENTRY POINT ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrapt jobs.ch, filtert für Detailhandel-EFZ-Profil und generiert HTML."
    )
    parser.add_argument("--location", "-l", default="winterthur",
                        help="Ort für die Jobsuche (Standard: winterthur)")
    parser.add_argument("--max-pages", "-m", type=int, default=None,
                        help="Maximale Anzahl Seiten (Standard: alle)")
    parser.add_argument("--output-dir", "-o", default="results",
                        help="Ausgabeverzeichnis für Roh-CSV/JSON (Standard: results/)")
    parser.add_argument("--filtered-dir", default="filtered_results",
                        help="Ausgabeverzeichnis für gefilterte JSON + HTML (Standard: filtered_results/)")
    parser.add_argument("--no-filter", action="store_true",
                        help="Nur scrapen, kein Filter und keine HTML-Generierung")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Filter-Verbose-Output unterdrücken")
    args = parser.parse_args()

    # ── 1. Scraping ───────────────────────────────────────────────────────────
    raw_jobs = scrape(location=args.location, max_pages=args.max_pages)

    if not raw_jobs:
        print("Keine Jobs gefunden.", file=sys.stderr)
        sys.exit(1)

    # ── 2. Roh-Export ─────────────────────────────────────────────────────────
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"jobs_{args.location}_{timestamp}"

    save_csv(raw_jobs,  output_dir / f"{stem}.csv")
    save_json(raw_jobs, output_dir / f"{stem}.json")

    # ── 3. Nur Vorschau wenn --no-filter ──────────────────────────────────────
    if args.no_filter:
        print(f"\n{'─'*80}")
        print(f"{'#':<4} {'Titel':<50} {'Firma':<30} {'Pensum':<10}")
        print(f"{'─'*80}")
        for i, job in enumerate(raw_jobs[:20], 1):
            print(f"{i:<4} {job['title'][:49]:<50} {job['company'][:29]:<30} {job['workload']:<10}")
        if len(raw_jobs) > 20:
            print(f"     ... und {len(raw_jobs) - 20} weitere Jobs (siehe CSV/JSON)")
        print(f"{'─'*80}\n")
        return

    # ── 4. Filtern ────────────────────────────────────────────────────────────
    filtered_jobs, stats = filter_jobs(raw_jobs, verbose=not args.quiet)

    # ── 5. Filter-Zusammenfassung ─────────────────────────────────────────────
    print_summary(filtered_jobs, stats)

    # ── 6. Gefilterter Export ─────────────────────────────────────────────────
    filtered_dir = Path(args.filtered_dir)
    filtered_dir.mkdir(parents=True, exist_ok=True)
    filtered_stem = f"jobs_{args.location}_{timestamp}_filtered"

    save_json(filtered_jobs, filtered_dir / f"{filtered_stem}.json")

    # ── 7. HTML generieren ────────────────────────────────────────────────────
    html_path = filtered_dir / f"jobs_{args.location}_{timestamp}.html"
    generate_html(filtered_jobs, stats, args.location, html_path)

    # ── 8. Ausgabe-Block ──────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print(f"  AUSGABE-DATEIEN")
    print(f"{'═'*60}")
    print(f"  Roh-CSV:        {output_dir / (stem + '.csv')}")
    print(f"  Roh-JSON:       {output_dir / (stem + '.json')}")
    print(f"  Gefiltert-JSON: {filtered_dir / (filtered_stem + '.json')}")
    print(f"  HTML:           {html_path}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
