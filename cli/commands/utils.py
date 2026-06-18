"""
Shared utilities for CLI command modules.

Defines the Typer app, console, logger, and helper functions
used by all command modules. Also contains the status and init commands.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

# ─── App ────────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="job-agent",
    help="AI-powered automated job application agent",
    add_completion=False,
)

console = Console()

# ─── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False)],
)
logger = logging.getLogger("job-agent")


# ─── Shared helpers ─────────────────────────────────────────────────────────


def _get_parser():
    from backend.services.cv_parser import CVParser
    return CVParser()


def _get_storage():
    from backend.database import storage
    return storage


def _print_profile(profile) -> None:
    """Pretty-print a CandidateProfile to the console."""
    console.print(Panel(f"[bold cyan]{profile.full_name or 'Unknown'}[/]", title="Candidate Profile"))

    contact = Table.grid(padding=(0, 2))
    contact.add_column(style="dim")
    contact.add_column()
    if profile.email:
        contact.add_row("Email", profile.email)
    if profile.phone:
        contact.add_row("Phone", profile.phone)
    if profile.linkedin_url:
        contact.add_row("LinkedIn", profile.linkedin_url)
    if profile.github_url:
        contact.add_row("GitHub", profile.github_url)
    if profile.years_of_experience:
        contact.add_row("Experience", f"{profile.years_of_experience} years")
    contact.add_row("Seniority", profile.seniority.value.title())
    console.print(contact)
    console.print()

    if profile.skills:
        skill_tree = Tree("Skills", guide_style="dim")
        categories: dict[str, list[str]] = {}
        for s in profile.skills[:25]:
            categories.setdefault(s.category, []).append(f"{s.name} (x{s.mentions})")
        for cat, items in categories.items():
            branch = skill_tree.add(f"[bold]{cat.title()}[/]")
            for item in items[:8]:
                branch.add(item)
        console.print(skill_tree)
        console.print()

    if profile.experiences:
        exp_table = Table(title="Experience", title_style="bold", show_header=True)
        exp_table.add_column("Company", style="cyan")
        exp_table.add_column("Title", style="green")
        exp_table.add_column("Description", style="dim", max_width=60, no_wrap=False)
        for exp in profile.experiences[:5]:
            desc = exp.description[:80] + "..." if len(exp.description) > 80 else exp.description
            exp_table.add_row(exp.company or "?", exp.title or "?", desc)
        console.print(exp_table)
        console.print()

    if profile.target_roles:
        console.print("[bold]Detected Target Roles[/]")
        for r in profile.target_roles[:5]:
            console.print(f"  \u2022 {r}")


def _print_match_results(results: list) -> None:
    """Display a ranked table of match results."""
    if not results:
        console.print("[yellow]No match results to display.[/]")
        return

    table = Table(title="Ranked Match Results", title_style="bold")
    table.add_column("#", style="dim")
    table.add_column("Role", style="cyan", max_width=35)
    table.add_column("Company", style="green", max_width=25)
    table.add_column("Score", style="yellow")
    table.add_column("Skills \u2713", style="green")
    table.add_column("Skills \u2717", style="red")
    table.add_column("Threshold", style="dim")

    for i, r in enumerate(results, 1):
        passed = "\u2705" if r.passed_threshold else "\u2014"
        table.add_row(
            str(i),
            r.job.title[:35] if r.job.title else "?",
            r.job.company[:25] if r.job.company else "?",
            f"{r.score:.0%}",
            str(len(r.skill_overlap)),
            str(len(r.skill_gaps)),
            passed,
        )
    console.print(table)

    top = results[0]
    if top.skill_overlap:
        console.print(f"\n[bold green]Top:[/] {top.job.title} @ {top.job.company}")
        console.print(f"  Score: [yellow]{top.score:.0%}[/] | {top.reasoning}")
        console.print(f"  [green]Overlapping:[/] {', '.join(top.skill_overlap[:8])}")
    if top.skill_gaps:
        console.print(f"  [red]Gaps:[/] {', '.join(top.skill_gaps[:8])}")


def _print_analysis_results(result) -> None:
    """Pretty-print an AnalysisResult from the analyzer service."""
    from rich.panel import Panel as RichPanel

    if not result.items:
        console.print("[yellow]No jobs to analyze.[/]")
        return

    console.print(
        RichPanel(
            f"[bold cyan]Jobs Scored:[/] {result.total_scored}  "
            f"[green]Eligible:[/] {result.eligible}  "
            f"[yellow]Threshold:[/] {result.threshold:.0%}",
            border_style="dim",
        )
    )

    table = Table(title="Match Analysis", title_style="bold")
    table.add_column("#", style="dim")
    table.add_column("Status", style="dim")
    table.add_column("Role", style="cyan", max_width=32)
    table.add_column("Company", style="green", max_width=22)
    table.add_column("Score", style="yellow")
    table.add_column("Skills \u2713", style="green")
    table.add_column("Skills \u2717", style="red")
    table.add_column("Eligible", style="bold")

    for i, item in enumerate(result.items, 1):
        status = item.apply_status if item.apply_status != "skipped" else ""
        status_icon = {
            "submitted": "\u2705",
            "captcha_blocked": "\U0001f512",
            "error": "\u274c",
            "": "",
        }.get(status, "\u23f3")
        eligible = "\u2705" if item.eligible else "\u2014"
        table.add_row(
            str(i),
            status_icon,
            item.job.title[:32] if item.job.title else "?",
            item.job.company[:22] if item.job.company else "?",
            f"{item.match.score:.0%}",
            str(len(item.match.skill_overlap)),
            str(len(item.match.skill_gaps)),
            eligible,
        )
    console.print(table)

    top_eligible = [it for it in result.items if it.eligible][:3]
    if top_eligible:
        console.print("\n[bold green]Top Eligible Jobs:[/]")
        for item in top_eligible:
            console.print(f"  [green]\u2022[/] {item.job.title} @ {item.job.company}")
            console.print(f"    Score: [yellow]{item.match.score:.0%}[/] \u2014 {item.match.reasoning}")
            if item.match.skill_overlap:
                console.print(f"    [green]\u2713 Overlap:[/] {', '.join(item.match.skill_overlap[:6])}")
            if item.match.skill_gaps:
                console.print(f"    [red]\u2717 Gaps:[/] {', '.join(item.match.skill_gaps[:6])}")


def _get_apply_urls(jobs_file: Optional[Path], limit: int) -> list[dict]:
    """Get job URLs from a file or storage for batch applying."""
    from backend.models.profile import JobPosting

    if jobs_file:
        with open(jobs_file) as f:
            raw_jobs = json.load(f)
    else:
        storage = _get_storage()
        raw_jobs = storage.get_jobs()

    if not raw_jobs:
        console.print("[yellow]No jobs found. Use [bold]discover[/] first or provide a jobs.json file.[/]")
        raise typer.Exit(0)

    jobs = [JobPosting(**j) for j in raw_jobs]
    return [
        {"title": j.title, "company": j.company, "url": j.url}
        for j in jobs[:limit] if j.url
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Commands: status & init
# ═══════════════════════════════════════════════════════════════════════════════


@app.command()
def status():
    """Show the agent's current state and storage stats."""
    storage = _get_storage()
    profiles = storage.get_profiles()
    applications = storage.get_applications()
    jobs_list = storage.get_jobs()

    console.print(Panel.fit("[bold cyan]Job Agent Status[/]", border_style="cyan"))
    table = Table(show_header=False)
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="white")
    table.add_row("Profiles parsed", str(len(profiles)))
    table.add_row("Applications tracked", str(len(applications)))
    table.add_row("Jobs discovered", str(len(jobs_list)))
    table.add_row("Data store", str(storage.db_path))

    try:
        from backend.services.embedding import EmbeddingService
        emb = EmbeddingService()
        doc_count = emb.count()
        table.add_row("Vector embeddings", str(doc_count))
    except Exception:
        table.add_row("Vector embeddings", "N/A")

    console.print(table)


@app.command()
def init():
    """Initialize the project \u2014 create data directories and verify dependencies."""
    console.print("[bold cyan]Initializing Job Agent...[/]\n")

    from backend.config import settings
    dirs = [
        settings.data_dir,
        settings.chroma_dir,
        settings.cv_storage_dir,
        settings.cover_letter_dir,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        console.print(f"  [green]\u2713[/] {d}")

    console.print()
    imports = [
        ("pdfplumber", "PDF parsing"),
        ("docx", "DOCX parsing"),
        ("spacy", "NER extraction"),
        ("chromadb", "Vector database"),
        ("playwright", "Browser automation"),
        ("httpx", "API calls"),
        ("jinja2", "Cover letter templates"),
    ]
    for mod_name, purpose in imports:
        try:
            __import__(mod_name)
            console.print(f"  [green]\u2713[/] {mod_name} \u2014 {purpose}")
        except ImportError:
            console.print(f"  [yellow]\u26a0[/] {mod_name} \u2014 {purpose} [dim](not installed)[/]")

    console.print(f"\n[green bold]Ready![/] Run [bold]job-agent parse <cv-file>[/] to get started.")
