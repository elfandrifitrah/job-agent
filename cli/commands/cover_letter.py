"""
CLI command for cover letter generation — generate-cover-letter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel

from cli.commands.utils import _get_parser, _get_storage, app, console


@app.command()
def generate_cover_letter(
    cv_path: Path = typer.Argument(
        ..., help="Path to parsed CV file", exists=True, readable=True
    ),
    job_index: int = typer.Option(
        0, "--job-idx", "-j", help="Index of the job in the last match results (0 = top match)"
    ),
    tone: str = typer.Option(
        "professional", "--tone", "-t", help="Writing style: professional, startup, creative"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output directory for the cover letter file"
    ),
):
    """Generate a tailored cover letter for a matched job."""
    parser = _get_parser()
    with console.status("[bold green]Parsing CV..."):
        profile = parser.parse(cv_path)

    storage = _get_storage()
    apps = storage.get_applications()
    if not apps:
        console.print("[yellow]No match results found. Run [bold]job-agent match[/] first.[/]")
        raise typer.Exit(0)

    from backend.models.profile import JobPosting, MatchResult

    if job_index >= len(apps):
        console.print(f"[red]Job index {job_index} out of range (max: {len(apps) - 1}).[/]")
        raise typer.Exit(1)

    app_data = apps[job_index] if job_index < len(apps) else apps[-1]
    job = JobPosting(**app_data["job"])

    match = MatchResult(
        job=job,
        score=app_data.get("score", 0.5),
        skill_overlap=app_data.get("skill_overlap", []),
        skill_gaps=app_data.get("skill_gaps", []),
        passed_threshold=app_data.get("passed_threshold", False),
    )

    console.print(f"[dim]Generating cover letter for {job.title} @ {job.company} (tone: {tone})...[/]")

    from backend.services.cover_letter_generator import CoverLetterGenerator
    generator = CoverLetterGenerator()

    output_path = generator.generate_and_save(
        profile=profile,
        job=job,
        match=match,
        tone=tone,
        output_dir=output_dir,
    )

    letter_text = output_path.read_text()
    console.print(f"\n[green]\u2713[/] Cover letter saved: [bold]{output_path}[/]")
    console.print()
    console.print(Panel(letter_text[:600], title="Preview (first 600 chars)", border_style="green"))
