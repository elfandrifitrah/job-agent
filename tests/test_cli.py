"""
Smoke tests for the CLI interface — verifies all commands are registered
and help text is generated correctly.

Since Typer auto-generates help from docstrings, these tests ensure
the commands exist and the help output is reasonable.
"""

from __future__ import annotations

from typer.testing import CliRunner

from cli.run import app

runner = CliRunner()


class TestCLIHelp:
    """Verify that all expected CLI commands appear in --help."""

    def test_help_contains_all_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

        # Core commands
        assert "parse" in result.output
        assert "profile" in result.output
        assert "discover" in result.output
        assert "match" in result.output
        assert "analyze" in result.output
        assert "apply" in result.output
        assert "automate" in result.output
        assert "generate-cover-letter" in result.output
        assert "status" in result.output
        assert "init" in result.output
        assert "embed" in result.output
        assert "search" in result.output

    def test_analyze_help_shows_new_flags(self):
        """Verify the enhanced analyze command shows the --apply flag."""
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "--apply" in result.output or "-a" in result.output
        assert "--threshold" in result.output or "-t" in result.output
        assert "--max" in result.output or "-m" in result.output
        assert "--headless" in result.output or "--headed" in result.output

    def test_match_help(self):
        result = runner.invoke(app, ["match", "--help"])
        assert result.exit_code == 0
        assert "--threshold" in result.output or "-t" in result.output

    def test_apply_help(self):
        result = runner.invoke(app, ["apply", "--help"])
        assert result.exit_code == 0
        assert "--url" in result.output or "-u" in result.output
        assert "--cv" in result.output or "-c" in result.output

    def test_automate_help(self):
        result = runner.invoke(app, ["automate", "--help"])
        assert result.exit_code == 0
        assert "--discover" in result.output
        assert "--limit" in result.output

    def test_discover_help(self):
        result = runner.invoke(app, ["discover", "--help"])
        assert result.exit_code == 0
        assert "--role" in result.output or "-r" in result.output
        assert "--location" in result.output or "-l" in result.output
