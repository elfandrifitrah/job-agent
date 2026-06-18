"""
CLI commands for matching and analysis — match, analyze.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from cli.commands.utils import (
    _get_parser,
    _get_storage,
    _print_analysis_results,
    _print_match_results,
    app,
    console,
)


@app.command()
def match(
    cv_path: Path = typer.Argument(
        ..., help="Path to CV file", exists=True, readable=True
    ),
    jobs_file: Optional[Path] = typer.Argument(
        None, help="Path to JSON file with job listings (omit to use stored jobs)"
    ),
    threshold: float = typer.Option(0.65, "--threshold", "-t", help="Minimum match score [0\u20131]"),
    top_k: int = typer.Option(20, "--top", help="Number of top results to show"),
):
    """Match a CV against job listings using semantic scoring."""
    parser = _get_parser()
    with console.status("[bold green]Parsing CV...[/]"):
        profile = parser.parse(cv_path)

    if jobs_file:
        with open(jobs_file) as f:
            raw_jobs = json.load(f)
    else:
        storage = _get_storage()
        raw_jobs = storage.get_jobs()
        if not raw_jobs:
            console.print("[yellow]No stored jobs. Use [bold]discover[/] first or provide a jobs.json file.[/]")
            raise typer.Exit(0)

    if not raw_jobs:
        console.print("[yellow]No jobs to match against.[/]")
        raise typer.Exit(0)

    from backend.models.profile import JobPosting
    jobs = [JobPosting(**j) for j in raw_jobs]

    console.print(f"[dim]Matching {profile.full_name or 'CV'} against {len(jobs)} jobs...[/]\n")

    from backend.services.matcher import SemanticMatcher
    matcher = SemanticMatcher(threshold=threshold)
    results = matcher.rank(profile, jobs, top_k=top_k)

    _print_match_results(results)

    passed = sum(1 for r in results if r.passed_threshold)
    console.print(f"\n[dim]{passed}/{len(results)} jobs passed the {threshold:.0%} threshold.[/]")

    from datetime import UTC, datetime
    from backend.database import storage

    existing_apps = storage.get_applications()
    existing_job_ids: set[str] = set()
    for app_record in existing_apps:
        job_data = app_record.get("job", app_record)
        jid = job_data.get("external_id", "") or job_data.get("id", "")
        if jid:
            existing_job_ids.add(jid)

    saved_count = 0
    skipped_count = 0
    for r in results:
        jid = r.job.id or ""
        if jid and jid in existing_job_ids:
            skipped_count += 1
            continue
        job_dict = r.job.model_dump(mode="json")
        storage.save_application({
            # Flat fields for API/dashboard compatibility
            "job_id": r.job.id or "",
            "job_title": r.job.title or "",
            "company": r.job.company or "",
            "match_score": r.score,
            "status": "matched" if r.passed_threshold else "pending",
            # Nested job data for backward compatibility
            "job": job_dict,
            "score": r.score,
            "passed_threshold": r.passed_threshold,
            "skill_overlap": r.skill_overlap,
            "skill_gaps": r.skill_gaps,
            "matched_at": datetime.now(UTC).isoformat(),
        })
        saved_count += 1

    if skipped_count:
        console.print(f"[dim]{skipped_count} already-matched jobs skipped.[/]")
    if saved_count:
        console.print(f"[dim]{saved_count} new matches saved to storage.[/]")
    else:
        console.print("[yellow]No new matches to save \u2014 all jobs already matched before.[/]")


@app.command()
def analyze(
    cv_path: Path = typer.Argument(
        ..., help="Path to CV file", exists=True, readable=True
    ),
    job_id: str = typer.Option("", "--job-id", "-j", help="Specific job ID to analyze"),
    threshold: float = typer.Option(0.60, "--threshold", "-t", help="Minimum match score [0\u20131]"),
    auto_apply: bool = typer.Option(False, "--apply", "-a", help="Auto-apply to eligible jobs (\u2265threshold)"),
    max_apps: int = typer.Option(5, "--max", "-m", help="Max jobs to apply to (with --apply)"),
    headless: bool = typer.Option(True, "--headless/--headed", help="Run browser in headless mode"),
):
    """
    Full analysis: parse CV, match against stored jobs, show skill fit.

    Use --apply to auto-apply to jobs that meet the threshold.
    """
    from backend.services.analyzer import JobAnalyzer

    analyzer = JobAnalyzer(
        threshold=threshold,
        headless=headless,
        human_review=auto_apply,
    )

    with console.status("[bold green]Parsing CV..."):
        profile = analyzer.parse_cv(cv_path)

    if job_id:
        jobs = analyzer.load_jobs_from_storage()
        jobs = [j for j in jobs if j.id == job_id]
        if not jobs:
            console.print(f"[red]Job ID '{job_id}' not found.[/]")
            raise typer.Exit(1)
    else:
        jobs = None

    if auto_apply:
        console.print(f"[bold cyan]\U0001f50d Analyzing & Applying: {profile.full_name or 'Candidate'}[/]")
        console.print(f"  Threshold: [yellow]{threshold:.0%}[/] | Max apps: {max_apps}")
        console.print()

        with console.status("[bold green]Running full analysis pipeline..."):
            result = analyzer.analyze_and_apply(
                profile=profile,
                cv_path=cv_path,
                jobs=jobs,
                max_applications=max_apps,
            )

        _print_analysis_results(result)

        console.print()
        console.print("[bold]Pipeline Summary[/]")
        console.print(f"  \U0001f4ca Jobs scored:  [cyan]{result.total_scored}[/]")
        console.print(f"  \u2705 Eligible:     [green]{result.eligible}[/] (\u2265{threshold:.0%})")
        console.print(f"  \U0001f916 Applied:      [bold]{result.applied}[/]")
        console.print()

        for item in result.items:
            if not item.eligible:
                continue
            icon = {
                "submitted": "\u2705",
                "captcha_blocked": "\U0001f512",
                "error": "\u274c",
                "skipped": "\u23ed\ufe0f",
            }.get(item.apply_status, "\u2753")
            console.print(f"  {icon} {item.job.title} [dim]@ {item.job.company}[/] \u2014 {item.apply_status}")
            if item.apply_error:
                console.print(f"     [dim]Error: {item.apply_error}[/]")

    else:
        with console.status("[bold green]Analyzing against stored jobs..."):
            result = analyzer.analyze(profile, jobs)

        _print_analysis_results(result)

        passed = result.eligible
        console.print(f"\n[dim]Summary: {passed}/{result.total_scored} passed threshold ({threshold:.0%})[/]")
        if passed:
            console.print(f"[dim]Run [bold]job-agent analyze {cv_path} --apply[/] to auto-apply.[/]")
