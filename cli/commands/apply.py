"""
CLI commands for browser automation — apply, automate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from cli.commands.utils import _get_apply_urls, _get_parser, _get_storage, app, console


@app.command()
def apply(
    url: str = typer.Option(..., "--url", "-u", help="Job application URL"),
    cv_path: Path = typer.Option(
        ..., "--cv", "-c", help="Path to CV file", exists=True, readable=True
    ),
    cover_letter_path: Optional[Path] = typer.Option(
        None, "--cover-letter", "-l", help="Path to cover letter file", exists=True, readable=True
    ),
    headless: bool = typer.Option(True, "--headless/--headed", help="Run browser in headless mode"),
    human_review: bool = typer.Option(True, "--human-review/--auto", help="Enable human-in-the-loop"),
    timeout: int = typer.Option(30, "--timeout", help="Navigation timeout in seconds"),
):
    """Apply to a single job by URL using browser automation."""
    parser = _get_parser()
    with console.status("[bold green]Parsing CV..."):
        profile = parser.parse(cv_path)

    console.print(f"[bold]Applying to:[/] {url}")
    console.print(f"[dim]Profile:[/] {profile.full_name or 'Unknown'} | {len(profile.skills)} skills")
    console.print(f"[dim]Browser:[/] {'Headless' if headless else 'Headed'} | Review: {'Human' if human_review else 'Auto'}")

    from backend.services.browser_automation import BrowserAutomation

    cl_path = str(cover_letter_path) if cover_letter_path else ""
    automator = BrowserAutomation(
        profile=profile,
        cv_path=str(cv_path),
        cover_letter_path=cl_path,
        headless=headless,
        human_review=human_review,
    )

    try:
        with console.status("[bold green]Launching browser..."):
            automator.launch()

        result = automator.apply(url=url, use_ats_adapter=True)

        console.print()
        status_icon = {
            "submitted": "[green]\u2705[/]",
            "captcha_blocked": "[yellow]\U0001f512[/]",
            "error": "[red]\u274c[/]",
            "pending": "[dim]\u23f3[/]",
        }.get(result.status, "[dim]\u2753[/]")

        console.print(f"{status_icon} [bold]Result:[/] {result.status}")
        console.print(f"  ATS: [cyan]{result.ats}[/]")
        console.print(f"  Fields filled: {result.fields_filled}/{result.total_fields}")
        console.print(f"  File uploaded: {result.file_uploaded}")

        if result.captcha_detected:
            console.print(f"  [yellow]\u26a0 CAPTCHA detected[/]")

        if result.screenshot_path:
            console.print(f"  [dim]Screenshot:[/] {result.screenshot_path}")

        if result.error_message:
            console.print(f"  [red]Error:[/] {result.error_message}")

        from backend.database import storage
        storage.save_application({
            "job_url": url,
            "ats": result.ats,
            "status": result.status,
            "fields_filled": result.fields_filled,
            "total_fields": result.total_fields,
            "file_uploaded": result.file_uploaded,
            "captcha_detected": result.captcha_detected,
            "error_message": result.error_message,
            "submitted_at": result.submitted_at,
        })

        if result.status == "submitted":
            console.print(f"\n[green bold]\u2713 Application submitted successfully![/]")
        elif result.status == "captcha_blocked":
            console.print(f"\n[yellow bold]\u26a0 CAPTCHA blocked.[/] Check the screenshot and try headed mode.")
        elif result.status == "error":
            console.print(f"\n[red bold]\u2717 Application failed.[/] See error above.")

    except Exception as e:
        console.print(f"\n[red bold]\u2717 Automation error:[/] {e}")
        raise typer.Exit(code=1)
    finally:
        automator.close()


@app.command()
def automate(
    cv_path: Path = typer.Option(
        ..., "--cv", "-c", help="Path to CV file", exists=True, readable=True
    ),
    cover_letter_path: Optional[Path] = typer.Option(
        None, "--cover-letter", "-l", help="Path to cover letter file", exists=True, readable=True
    ),
    jobs_file: Optional[Path] = typer.Option(
        None, "--jobs-file", "-j", help="JSON file with job listings (omit to use stored jobs)"
    ),
    limit: int = typer.Option(5, "--limit", help="Max jobs to apply to"),
    headless: bool = typer.Option(True, "--headless/--headed", help="Run browser in headless mode"),
    human_review: bool = typer.Option(True, "--human-review/--auto", help="Enable human-in-the-loop"),
    discover_first: bool = typer.Option(False, "--discover", help="Discover jobs before applying"),
    role: str = typer.Option("Software Engineer", "--role", "-r", help="Job title to search for (with --discover)"),
    location: str = typer.Option("", "--location", "-l", help="Location filter (with --discover)"),
    remote: bool = typer.Option(False, "--remote", help="Remote-only (with --discover)"),
):
    """Automated pipeline: discover \u2192 match \u2192 apply to multiple jobs."""
    parser = _get_parser()
    with console.status("[bold green]Parsing CV..."):
        profile = parser.parse(cv_path)

    console.print(f"[bold cyan]Automated Job Application Pipeline[/]")
    console.print(f"[dim]Profile:[/] {profile.full_name or 'Unknown'} | {len(profile.skills)} skills")
    console.print()

    if discover_first:
        from backend.services.job_discovery import JobDiscovery, SearchParams

        params = SearchParams(
            role=role,
            location=location,
            remote=remote,
            max_results=limit,
        )
        with console.status(f"[bold green]Discovering '{role}' jobs..."):
            discovery = JobDiscovery()
            result = discovery.search_and_store(params)
        console.print(f"[green]\u2713[/] Found {len(result.jobs)} jobs from {len(result.source_counts)} sources")
    else:
        storage = _get_storage()
        raw_jobs = storage.get_jobs()
        console.print(f"[dim]Using {len(raw_jobs)} stored jobs[/]")

    jobs_to_apply = _get_apply_urls(jobs_file, limit)

    if not jobs_to_apply:
        console.print("[yellow]No jobs with URLs to apply to. Try [bold]job-agent discover[/] first.[/]")
        raise typer.Exit(0)

    console.print(f"\n[bold]Applying to {len(jobs_to_apply)} jobs...[/]\n")

    from backend.services.browser_automation import BrowserAutomation

    cl_path = str(cover_letter_path) if cover_letter_path else ""
    automator = BrowserAutomation(
        profile=profile,
        cv_path=str(cv_path),
        cover_letter_path=cl_path,
        headless=headless,
        human_review=human_review,
    )

    results = []
    try:
        automator.launch()

        for i, job_info in enumerate(jobs_to_apply, 1):
            title = job_info.get("title", "Unknown")
            company = job_info.get("company", "Unknown")
            url = job_info.get("url", "")

            if not url:
                console.print(f"  [dim]#{i} {title} @ {company} \u2014 no URL, skipping[/]")
                continue

            console.print(f"\n[bold cyan]#{i}/{len(jobs_to_apply)}[/] {title} @ {company}")
            console.print(f"  [dim]URL:[/] {url}")

            try:
                apply_result = automator.apply(url=url, use_ats_adapter=True)
                results.append({
                    "job_title": title,
                    "company": company,
                    "url": url,
                    "status": apply_result.status,
                    "ats": apply_result.ats,
                    "fields_filled": apply_result.fields_filled,
                    "error": apply_result.error_message,
                })

                status_icon = {
                    "submitted": "\u2705", "captcha_blocked": "\U0001f512",
                    "error": "\u274c", "pending": "\u23f3",
                }.get(apply_result.status, "\u2753")
                console.print(f"  {status_icon} [bold]{apply_result.status}[/] | ATS: {apply_result.ats} | Fields: {apply_result.fields_filled}")

                if apply_result.status == "captcha_blocked" and not human_review:
                    console.print("  [yellow]\u26a0 CAPTCHA \u2014 skipping remaining jobs[/]")
                    break

                if apply_result.status == "error":
                    console.print(f"  [dim]Error: {apply_result.error_message}[/]")

            except Exception as e:
                console.print(f"  [red]\u2717 Error:[/] {e}")
                results.append({
                    "job_title": title,
                    "company": company,
                    "url": url,
                    "status": "error",
                    "error": str(e),
                })
                if not human_review:
                    break

    finally:
        automator.close()

    console.print("\n" + "=" * 50)
    console.print("[bold]Session Summary[/]")
    submitted = sum(1 for r in results if r["status"] == "submitted")
    failed = sum(1 for r in results if r["status"] == "error")
    blocked = sum(1 for r in results if r["status"] == "captcha_blocked")

    console.print(f"  [green]\u2705 Submitted:[/] {submitted}")
    if failed:
        console.print(f"  [red]\u274c Failed:[/] {failed}")
    if blocked:
        console.print(f"  [yellow]\U0001f512 CAPTCHA blocked:[/] {blocked}")

    for r in results:
        icon = {"submitted": "\u2705", "error": "\u274c", "captcha_blocked": "\U0001f512", "pending": "\u23f3"}.get(r["status"], "\u2753")
        console.print(f"  {icon} {r['job_title']} [dim]@ {r['company']}[/] \u2014 {r['status']}")

    console.print()
