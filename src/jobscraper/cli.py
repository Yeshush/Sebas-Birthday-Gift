"""Typer CLI entry point for JobScraper."""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table
from rich import print as rprint

from .export import generate_html, save_csv, save_json, _CAT_LABELS
from .filters import filter_jobs
from .log import configure_logging
from .scraper import scrape

app     = typer.Typer(help="Scrapt jobs.ch für Detailhandel-EFZ-Profil und generiert HTML-Reports.")
console = Console()


def _print_summary(jobs, stats) -> None:
    """Print a rich summary table to the console."""
    # Stats table
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style="bold")
    t.add_column(justify="right")
    t.add_row("Gesamte Jobs geprüft:",   str(stats.total))
    t.add_row("Pensum zu niedrig:",       str(stats.excluded_workload))
    t.add_row("Fachausbildung nötig:",    str(stats.excluded_keyword))
    t.add_row("Kein Relevanz-Match:",     str(stats.excluded_no_match))
    t.add_row("Duplikate entfernt:",      str(stats.duplicates_removed))
    t.add_row("─" * 28,                  "──────")
    t.add_row("[bold green]PASSENDE STELLEN:[/bold green]", f"[bold green]{stats.kept}[/bold green]")
    console.print(Panel(t, title="[bold]Filter-Resultat[/bold]", border_style="dim"))

    # Category breakdown
    cats = Counter(j.category for j in jobs)
    ct = Table(show_header=False, box=None, padding=(0, 2))
    ct.add_column(style="bold")
    ct.add_column(justify="right")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        ct.add_row(_CAT_LABELS.get(cat, cat), str(count))
    console.print(Panel(ct, title="[bold]Nach Kategorie[/bold]", border_style="dim"))

    easy   = sum(1 for j in jobs if j.easy_apply)
    querei = sum(1 for j in jobs if "quereinstieg" in j.title.lower())
    console.print(f"  ⚡ Easy Apply verfügbar:  [bold]{easy}[/bold]")
    console.print(f"  🔄 Quereinstieg explizit: [bold]{querei}[/bold]\n")


@app.command()
def main(
    location: Annotated[str, typer.Option("--location", "-l",
        help="Ort für die Jobsuche")] = "winterthur",
    max_pages: Annotated[int | None, typer.Option("--max-pages", "-m",
        help="Maximale Anzahl Seiten (Standard: alle)", min=1)] = None,
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o",
        help="Ausgabeverzeichnis für Roh-CSV/JSON")] = Path("results"),
    filtered_dir: Annotated[Path, typer.Option("--filtered-dir",
        help="Ausgabeverzeichnis für gefilterte JSON + HTML")] = Path("filtered_results"),
    no_filter: Annotated[bool, typer.Option("--no-filter",
        help="Nur scrapen, kein Filter")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q",
        help="Filter-Verbose-Output unterdrücken")] = False,
    log_file: Annotated[Path | None, typer.Option("--log-file",
        help="Optionale Log-Datei")] = None,
) -> None:
    configure_logging(log_file=log_file, level="WARNING" if quiet else "INFO")

    console.print(f"\n[bold blue]🔍 JobScraper[/bold blue] — Location: [bold]{location}[/bold]\n")

    # ── 1. Scraping ────────────────────────────────────────────────────────────
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scraping...", total=None)
        raw_jobs = scrape(location=location, max_pages=max_pages)
        progress.update(task, completed=True, total=1)

    if not raw_jobs:
        console.print("[bold red]❌ Keine Jobs gefunden.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"✅ [bold]{len(raw_jobs):,}[/bold] Jobs gescrapt\n")

    # ── 2. Raw export ──────────────────────────────────────────────────────────
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"jobs_{location}_{timestamp}"

    save_csv(raw_jobs,  output_dir / f"{stem}.csv")
    save_json(raw_jobs, output_dir / f"{stem}.json")

    # ── 3. Preview only if --no-filter ────────────────────────────────────────
    if no_filter:
        t = Table(title="Vorschau (erste 20 Jobs)", show_lines=False)
        t.add_column("#",      style="dim", width=4)
        t.add_column("Titel",  max_width=50)
        t.add_column("Firma",  max_width=30)
        t.add_column("Pensum", max_width=12)
        for i, job in enumerate(raw_jobs[:20], 1):
            t.add_row(str(i), job.title[:49], job.company[:29], job.workload)
        if len(raw_jobs) > 20:
            t.add_row("...", f"und {len(raw_jobs)-20} weitere (siehe CSV/JSON)", "", "")
        console.print(t)
        return

    # ── 4. Filter ─────────────────────────────────────────────────────────────
    console.print("[bold]Filtere Jobs...[/bold]")
    filtered_jobs, stats = filter_jobs(raw_jobs, verbose=not quiet)

    _print_summary(filtered_jobs, stats)

    # ── 5. Filtered export ────────────────────────────────────────────────────
    filtered_dir.mkdir(parents=True, exist_ok=True)
    filtered_stem = f"jobs_{location}_{timestamp}_filtered"

    save_json(filtered_jobs, filtered_dir / f"{filtered_stem}.json")

    html_path = filtered_dir / f"jobs_{location}_{timestamp}.html"
    generate_html(filtered_jobs, stats, location, html_path)

    # ── 6. Output summary ─────────────────────────────────────────────────────
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style="bold dim")
    t.add_column()
    t.add_row("Roh-CSV:",        str(output_dir / f"{stem}.csv"))
    t.add_row("Roh-JSON:",       str(output_dir / f"{stem}.json"))
    t.add_row("Gefiltert-JSON:", str(filtered_dir / f"{filtered_stem}.json"))
    t.add_row("HTML:",           str(html_path))
    console.print(Panel(t, title="[bold]Ausgabe-Dateien[/bold]", border_style="green"))
