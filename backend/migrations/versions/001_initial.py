"""Initial migration — create all core tables.

Revision ID: 001
Revises: None
Create Date: 2025-06-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── profiles ───────────────────────────────────────────────────────────
    op.create_table(
        "profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("full_name", sa.String(255), default=""),
        sa.Column("email", sa.String(255), default=""),
        sa.Column("phone", sa.String(50), default=""),
        sa.Column("location", sa.String(255), default=""),
        sa.Column("linkedin_url", sa.String(500), default=""),
        sa.Column("github_url", sa.String(500), default=""),
        sa.Column("portfolio_url", sa.String(500), default=""),
        sa.Column("years_of_experience", sa.Float, default=0.0),
        sa.Column("seniority", sa.String(20), default="unknown"),
        sa.Column("remote_preferred", sa.Boolean, default=False),
        sa.Column("target_roles", postgresql.JSON, default=list),
        sa.Column("preferred_locations", postgresql.JSON, default=list),
        sa.Column("raw_text", sa.Text, default=""),
        sa.Column("skills", postgresql.JSON, default=list),
        sa.Column("experiences", postgresql.JSON, default=list),
        sa.Column("education", postgresql.JSON, default=list),
        sa.Column("source_file", sa.String(500), default=""),
        sa.Column("parsed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    # ─── jobs ───────────────────────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("external_id", sa.String(50), default="", index=True),
        sa.Column("title", sa.String(255), default=""),
        sa.Column("company", sa.String(255), default=""),
        sa.Column("location", sa.String(255), default=""),
        sa.Column("description", sa.Text, default=""),
        sa.Column("url", sa.String(1000), default=""),
        sa.Column("source", sa.String(50), default=""),
        sa.Column("salary_range", sa.String(100), nullable=True),
        sa.Column("remote", sa.Boolean, default=False),
        sa.Column("posted_date", sa.String(50), nullable=True),
        sa.Column("skills_required", postgresql.JSON, default=list),
        sa.Column("seniority", sa.String(20), default="unknown"),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("external_id", "source", name="uq_job_source"),
    )

    # ─── applications ───────────────────────────────────────────────────────
    op.create_table(
        "applications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("profiles.id"), nullable=False, index=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False, index=True),
        sa.Column("match_score", sa.Float, default=0.0),
        sa.Column("status", sa.String(20), default="pending", index=True),
        sa.Column("skill_overlap", postgresql.JSON, default=list),
        sa.Column("skill_gaps", postgresql.JSON, default=list),
        sa.Column("cover_letter_path", sa.String(500), nullable=True),
        sa.Column("screenshot_path", sa.String(500), nullable=True),
        sa.Column("ats_name", sa.String(50), default=""),
        sa.Column("fields_filled", sa.Integer, default=0),
        sa.Column("total_fields", sa.Integer, default=0),
        sa.Column("submitted_at", sa.DateTime, nullable=True),
        sa.Column("response_received_at", sa.DateTime, nullable=True),
        sa.Column("notes", sa.Text, default=""),
        sa.Column("error_log", sa.Text, default=""),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    # ─── sessions ───────────────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("profiles.id"), nullable=True, index=True),
        sa.Column("status", sa.String(20), default="running"),
        sa.Column("total_jobs", sa.Integer, default=0),
        sa.Column("submitted", sa.Integer, default=0),
        sa.Column("failed", sa.Integer, default=0),
        sa.Column("blocked", sa.Integer, default=0),
        sa.Column("skipped", sa.Integer, default=0),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("error_log", sa.Text, default=""),
    )


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("applications")
    op.drop_table("jobs")
    op.drop_table("profiles")
