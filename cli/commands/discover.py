"""
CLI commands for job discovery — discover, search.
"""

from __future__ import annotations

import typer

from cli.commands.utils import app, console


@app.command()
def discover(
    role: str = typer.Option("Software Engineer", "--role", "-r", help="Job title / keywords"),
    location: str = typer.Option("", "--location", "-l", help="City or region"),
    remote: bool = typer.Option(False, "--remote", help="Remote-only positions"),
    limit: int = typer.Option(10, "--limit", help="Max results"),
    days: int = typer.Option(14, "--days", help="Only jobs posted within N days"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to storage"),
):
    """Discover jobs from multiple sources (Adzuna, LinkedIn, Indeed)."""
    from backend.services.job_discovery import JobDiscovery, SearchParams

    params = SearchParams(
        role=role,
        location=location,
        remote=remote,
        max_results=limit,
        days_old=days,
    )

    with console.status(f"[bold green]Searching for '{role}' jobs..."):
        discovery = JobDiscovery()
        if save:
            result = discovery.search_and_store(params)
        else:
            result = discovery.search(params)

    if result.errors:
        console.print(f"[yellow]Source errors:[/] {', '.join(result.errors)}")

    if not result.jobs:
        console.print(f"[yellow]No jobs found for '{role}'. Try broader keywords.[/]")
        raise typer.Exit(0)

    from rich.panel import Panel
    from rich.table import Table

    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="dim")
    summary.add_column()
    for src, count in result.source_counts.items():
        summary.add_row(f"  {src}", str(count))
    summary.add_row("  unique", f"[bold]{len(result.jobs)}[/]")

    console.print(Panel(summary, title="Job Discovery Results", border_style="cyan"))
    console.print()

    job_table = Table()
    job_table.add_column("#", style="dim")
    job_table.add_column("Title", style="cyan", max_width=30)
    job_table.add_column("Company", style="green", max_width=22)
    job_table.add_column("Location", style="dim", max_width=20)
    job_table.add_column("Source", style="dim")
    job_table.add_column("Seniority", style="yellow")

    for i, job in enumerate(result.jobs[:limit], 1):
        job_table.add_row(
            str(i),
            job.title[:30] if job.title else "?",
            job.company[:22] if job.company else "?",
            job.location[:20] if job.location else "\u2014",
            job.source,
            job.seniority.value.title(),
        )
    console.print(job_table)

    console.print(f"\n[dim]Run [bold]job-agent match <cv>[/] to score these jobs.[/]")


@app.command()
def search(
    role: str = typer.Option("", "--role", "-r", help="Job title / keywords"),
    location: str = typer.Option("", "--location", "-l", help="Location filter"),
    remote: bool = typer.Option(False, "--remote", help="Remote-only positions"),
    limit: int = typer.Option(10, "--limit", help="Max results"),
):
    """Alias for 'discover' \u2014 find jobs from multiple sources."""
    discover(role=role or "Software Engineer", location=location, remote=remote, limit=limit, save=True)
