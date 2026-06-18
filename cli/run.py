"""
CLI entry point for the Automated Job Application Agent.

Usage:
    job-agent parse ./path/to/resume.pdf
    job-agent profile
    job-agent embed ./path/to/resume.pdf
    job-agent discover --role "Software Engineer" --location "Remote"
    job-agent match ./path/to/resume.pdf [jobs.json]
    job-agent generate-cover-letter ./path/to/resume.pdf --job-id <id>
    job-agent analyze ./path/to/resume.pdf --job-id <id>
    job-agent apply --url <job-url> --cv ./resume.pdf --cover-letter ./letter.txt
    job-agent automate --cv ./resume.pdf --discover --limit 5
    job-agent status
    job-agent init
"""

# The app, console, and logger are defined in cli/commands/utils.py.
# Importing the command modules registers their @app.command() decorators.
# Order matters: utils must be loaded first because it creates the app.

from cli.commands import utils  # noqa: E402  — defines app, console, logger

# Import all command modules so their decorators register on the app.
# The leading underscore avoids "unused import" warnings.
from cli.commands import apply as _apply  # noqa: F401, E402
from cli.commands import cover_letter as _cover_letter  # noqa: F401, E402
from cli.commands import discover as _discover  # noqa: F401, E402
from cli.commands import match as _match  # noqa: F401, E402
from cli.commands import parse as _parse  # noqa: F401, E402

from cli.commands.utils import app, console  # noqa: E402

if __name__ == "__main__":
    app()
