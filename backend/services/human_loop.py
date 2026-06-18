"""
Human-in-the-loop — interactive CLI fallback for when automation hits obstacles.

Capabilities:
  - CAPTCHA resolution: pause and ask human to solve CAPTCHA
  - Field verification: let human review and correct filled fields
  - Non-standard form handling: prompt human for guidance on unknown fields
  - Multi-step wizard navigation: pause between steps for approval
  - Error recovery: present errors and get human decision

Uses Rich for interactive CLI prompts (maintained in-band).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from backend.models.profile import CandidateProfile

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class HumanDecision:
    """Result of a human-in-the-loop interaction."""
    action: str = ""                 # continue, retry, skip, abort, manual
    notes: str = ""
    manual_values: dict[str, str] = field(default_factory=dict)
    form_submitted: bool = False


class HumanLoop:
    """
    Interactive human-in-the-loop UI for the job application agent.

    Pops up interactive prompts in the CLI when the automation hits obstacles
    that require human judgement (CAPTCHAs, unknown fields, errors).
    """

    def __init__(self, profile: CandidateProfile, verbose: bool = True):
        self.profile = profile
        self.verbose = verbose

    # ─── CAPTCHA Handling ───────────────────────────────────────────────────

    def handle_captcha(
        self,
        captcha_type: str,
        screenshot_path: Optional[str] = None,
        url: str = "",
    ) -> HumanDecision:
        """Ask the human to solve a CAPTCHA and proceed."""
        console.print()
        console.print("[bold yellow]╔══════════════════════════════════════════════╗[/]")
        console.print("[bold yellow]║         CAPTCHA DETECTED                    ║[/]")
        console.print("[bold yellow]╚══════════════════════════════════════════════╝[/]")
        console.print(f"[yellow]Type:[/] {captcha_type}")
        if url:
            console.print(f"[yellow]URL:[/] {url}")
        if screenshot_path:
            ss_path = Path(screenshot_path)
            if ss_path.exists():
                console.print(f"[yellow]Screenshot:[/] {ss_path.resolve()}")

        console.print()
        console.print("[dim]Options:[/]")
        console.print("  1. [green]Solve CAPTCHA[/] — I'll solve it and you continue")
        console.print("  2. [yellow]Skip[/] — Skip this job and move to the next")
        console.print("  3. [red]Abort[/] — Stop this application session")

        choice = input("\nYour choice (1-3): ").strip()

        if choice == "1":
            console.print("[green]CAPTCHA solved! Continuing...[/]")
            return HumanDecision(action="continue")
        elif choice == "2":
            console.print("[yellow]Skipping this job.[/]")
            return HumanDecision(action="skip")
        else:
            console.print("[red]Aborting application session.[/]")
            return HumanDecision(action="abort")

    # ─── Field Verification ─────────────────────────────────────────────────

    def verify_fields(
        self,
        field_values: dict[str, str],
        url: str = "",
    ) -> HumanDecision:
        """Show the human what fields were filled and let them make corrections."""
        console.print()
        console.print("[bold cyan]╔══════════════════════════════════════════════╗[/]")
        console.print("[bold cyan]║       FIELD VERIFICATION REQUIRED           ║[/]")
        console.print("[bold cyan]╚══════════════════════════════════════════════╝[/]")
        if url:
            console.print(f"[dim]Page:[/] {url}")
        console.print()

        corrections = {}

        for i, (field, value) in enumerate(field_values.items(), 1):
            console.print(f"[dim]{i}.[/] {field}: [green]{value[:60]}[/]")
            change = input(f"   Change value? (Enter to keep, type new value, 'x' to clear): ").strip()
            if change:
                if change.lower() == "x":
                    corrections[field] = ""
                else:
                    corrections[field] = change

        console.print()
        console.print("Proceed with submission?")
        console.print("  1. [green]Submit[/] — Confirm and submit")
        console.print("  2. [yellow]Edit More[/] — I'll fill the form manually")
        console.print("  3. [red]Skip[/] — Skip this job")

        choice = input("Your choice (1-3): ").strip()

        if choice == "1":
            return HumanDecision(action="continue", manual_values=corrections)
        elif choice == "2":
            return HumanDecision(
                action="manual",
                manual_values=corrections,
                notes="Human will fill the form manually"
            )
        else:
            return HumanDecision(action="skip")

    # ─── Unknown Field Handling ─────────────────────────────────────────────

    def handle_unknown_fields(
        self,
        fields: list[dict[str, Any]],
        url: str = "",
    ) -> HumanDecision:
        """Ask the human about fields the automation couldn't fill."""
        console.print()
        console.print("[bold yellow]╔══════════════════════════════════════════════╗[/]")
        console.print("[bold yellow]║       UNKNOWN FORM FIELDS DETECTED          ║[/]")
        console.print("[bold yellow]╚══════════════════════════════════════════════╝[/]")
        if url:
            console.print(f"[dim]Page:[/] {url}")
        console.print()

        manual_values = {}

        for i, field in enumerate(fields, 1):
            label = field.get("label") or field.get("name") or f"Field #{i}"
            field_type = field.get("field_type", "unknown")
            required = field.get("required", False)
            req_mark = "[red]*[/]" if required else ""
            console.print(f"  {i}. {label} {req_mark} [dim]({field_type})[/]")

            value = input(f"     Enter value (or press Enter to skip): ").strip()
            if value:
                manual_values[field.get("selector", "")] = value

        if manual_values:
            console.print(f"[green]Captured {len(manual_values)} manual values.[/]")
            return HumanDecision(action="continue", manual_values=manual_values)

        console.print("[yellow]No values provided. Skipping unfilled fields.[/]")
        return HumanDecision(action="continue")

    # ─── Error Recovery ─────────────────────────────────────────────────────

    def handle_error(
        self,
        error_message: str,
        url: str = "",
        screenshot_path: Optional[str] = None,
    ) -> HumanDecision:
        """Present an error to the human and ask how to proceed."""
        console.print()
        console.print("[bold red]╔══════════════════════════════════════════════╗[/]")
        console.print("[bold red]║          APPLICATION ERROR                    ║[/]")
        console.print("[bold red]╚══════════════════════════════════════════════╝[/]")
        console.print(f"[red]Error:[/] {error_message}")
        if url:
            console.print(f"[dim]URL:[/] {url}")
        if screenshot_path:
            ss_path = Path(screenshot_path)
            if ss_path.exists():
                console.print(f"[dim]Screenshot:[/] {ss_path.resolve()}")
        console.print()

        console.print("How would you like to proceed?")
        console.print("  1. [green]Retry[/] — Try again")
        console.print("  2. [yellow]Skip[/] — Skip this job")
        console.print("  3. [blue]Manual[/] — I'll handle this one manually")
        console.print("  4. [red]Abort[/] — Stop all applications")

        choice = input("Your choice (1-4): ").strip()

        actions = {"1": "retry", "2": "skip", "3": "manual", "4": "abort"}
        return HumanDecision(action=actions.get(choice, "skip"), notes=error_message)

    # ─── Submission Confirmation ────────────────────────────────────────────

    def confirm_submission(
        self,
        job_title: str,
        company: str,
        fields_filled: int,
        total_fields: int,
        url: str = "",
    ) -> bool:
        """Ask the human to confirm before final submission."""
        console.print()
        console.print("[bold cyan]╔══════════════════════════════════════════════╗[/]")
        console.print("[bold cyan]║     READY TO SUBMIT APPLICATION             ║[/]")
        console.print("[bold cyan]╚══════════════════════════════════════════════╝[/]")
        console.print(f"  [bold]Position:[/] {job_title} @ {company}")
        console.print(f"  [bold]Fields filled:[/] {fields_filled}/{total_fields}")
        if url:
            console.print(f"  [bold]URL:[/] {url}")
        console.print()

        console.print("  1. [green]Submit[/] — Send the application")
        console.print("  2. [yellow]Review[/] — Preview and edit fields")
        console.print("  3. [red]Skip[/] — Don't apply to this one")

        choice = input("Your choice (1-3): ").strip()
        return choice == "1"

    # ─── Session Summary ────────────────────────────────────────────────────

    def show_session_summary(self, results: list[dict[str, Any]]) -> None:
        """Display a summary of the automation session."""
        console.print()
        console.print("[bold green]╔══════════════════════════════════════════════╗[/]")
        console.print("[bold green]║        APPLICATION SESSION SUMMARY           ║[/]")
        console.print("[bold green]╚══════════════════════════════════════════════╝[/]")

        submitted = sum(1 for r in results if r.get("status") == "submitted")
        failed = sum(1 for r in results if r.get("status") == "error")
        blocked = sum(1 for r in results if r.get("status") == "captcha_blocked")
        skipped = sum(1 for r in results if r.get("status") in ("skipped", "human_intervention"))

        console.print(f"  Total attempted: [bold]{len(results)}[/]")
        console.print(f"  [green]✓ Submitted:[/] {submitted}")
        if failed:
            console.print(f"  [red]✗ Failed:[/] {failed}")
        if blocked:
            console.print(f"  [yellow]⚠ CAPTCHA blocked:[/] {blocked}")
        if skipped:
            console.print(f"  [dim]Skipped:[/] {skipped}")
        console.print()

        for r in results:
            job = r.get("job_title", "Unknown")
            company = r.get("company", "Unknown")
            status = r.get("status", "unknown")
            icons = {"submitted": "✅", "error": "❌", "captcha_blocked": "🔒", "skipped": "⏭️"}
            console.print(f"  {icons.get(status, '❓')} {job} [dim]@ {company}[/] — [bold]{status}[/]")

        console.print()


# ─── Convenience: CAPTCHA Handler (used by browser_automation) ─────────────

class CaptchaHandler:
    """Simplified CAPTCHA handling wrapper for the browser automation engine."""

    def __init__(self, profile: CandidateProfile):
        self.profile = profile
        self.human_loop = HumanLoop(profile)

    def handle_captcha(
        self,
        page,
        captcha_result,
        screenshot_path: Optional[str] = None,
    ) -> bool:
        """
        Handle a detected CAPTCHA by asking the human to solve it.

        Returns True if the CAPTCHA was resolved and we can continue.
        """
        from backend.services.captcha_detector import CaptchaType

        captcha_type = captcha_result.captcha_type
        console.print(f"\n[bold yellow]🔒 CAPTCHA Detected:[/] {captcha_type.value}")

        if screenshot_path:
            console.print(f"  [dim]Screenshot:[/] {screenshot_path}")

        # Take a screenshot if not already done
        if not screenshot_path:
            try:
                ss_path = f"/tmp/captcha_{captcha_type.value}.png"
                page.screenshot(path=ss_path)
                console.print(f"  [dim]Screenshot:[/] {ss_path}")
            except Exception:
                pass

        console.print("\n[dim]Please solve the CAPTCHA in your browser, then press Enter.[/]")
        console.print("[dim](Type 'skip' to skip this job, 'abort' to stop)[/]")

        user_input = input("→ ").strip().lower()

        if user_input == "abort":
            return False
        elif user_input == "skip":
            return False
        else:
            # Give the page a moment after CAPTCHA solving
            import time
            time.sleep(1)
            return True
