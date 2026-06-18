"""
CLI commands for CV parsing — parse, profile, embed.
"""

from __future__ import annotations

from pathlib import Path

import typer

from cli.commands.utils import _get_parser, _get_storage, _print_profile, app, console, logger


@app.command()
def parse(
    cv_path: Path = typer.Argument(
        ..., help="Path to CV file (PDF, DOCX, TXT, HTML)", exists=True, readable=True
    ),
):
    """Parse a CV file and display the extracted profile."""
    parser = _get_parser()
    with console.status(f"[bold green]Parsing {cv_path.name}...[/]"):
        try:
            profile = parser.parse(cv_path)
        except Exception as e:
            console.print(f"[red bold]Error:[/] {e}")
            raise typer.Exit(code=1)

    storage = _get_storage()
    storage.save_profile(profile.model_dump(mode="json"))
    console.print("[dim]Profile saved to storage.[/]\n")
    _print_profile(profile)


@app.command()
def profile():
    """Show the most recently parsed CV profile."""
    storage = _get_storage()
    profiles = storage.get_profiles()
    if not profiles:
        console.print("[yellow]No parsed CV profiles found. Use [bold]parse[/] first.[/]")
        raise typer.Exit(0)

    latest = profiles[-1]
    from backend.models.profile import CandidateProfile
    _print_profile(CandidateProfile(**latest))


@app.command()
def embed(
    cv_path: Path = typer.Argument(
        ..., help="Path to CV file", exists=True, readable=True
    ),
):
    """Parse a CV and store its vector embedding in ChromaDB."""
    parser = _get_parser()
    with console.status("[bold green]Parsing CV...[/]"):
        profile = parser.parse(cv_path)

    with console.status("[bold green]Generating embedding..."):
        try:
            from backend.services.embedding import EmbeddingService
            emb = EmbeddingService()
            emb.initialize()
            emb.store_cv(
                profile_id=profile.full_name or "unknown",
                text=profile.raw_text,
                metadata={"name": profile.full_name, "skills": ",".join(profile.skill_names)},
            )
        except Exception as e:
            console.print(f"[red bold]Error:[/] {e}")
            raise typer.Exit(code=1)

    console.print(f"[green]\u2713[/] Embedding stored ({emb.count()} docs in collection)")
