"""
Application configuration loaded from environment variables.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ─── API Auth ───
    api_key: str = ""

    # ─── LLM API Keys ───
    claude_api_key: str = ""
    openai_api_key: str = ""

    # ─── Database ───
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/job_agent"
    redis_url: str = "redis://localhost:6379/0"

    # ─── Vector Store ───
    chroma_persist_dir: str = "./data/chroma"

    # ─── Firecrawl Web Scraper ──
    firecrawl_api_key: str = ""

    # ─── Job Discovery ───
    linkedin_email: str = ""
    linkedin_password: str = ""
    serpapi_key: str = ""
    adzuna_app_id: str = ""
    adzuna_api_key: str = ""

    # ─── Email ───
    gmail_email: str = ""
    gmail_app_password: str = ""

    # ─── Browser Automation ───
    browser_headless: bool = True
    browser_headed_debug: bool = False
    screenshots_dir: str = "./data/screenshots"
    apply_timeout_ms: int = 30000

    # ─── Agent Behaviour ───
    match_threshold: float = 0.65
    max_applications_per_day: int = 20
    human_review_mode: bool = True
    auto_answer_screening: bool = False

    # ─── Paths ───
    data_dir: Path = Path("./data")
    chroma_dir: Path = Path("./data/chroma")
    cv_storage_dir: Path = Path("./data/cvs")
    cover_letter_dir: Path = Path("./data/cover_letters")

    def model_post_init(self, __context) -> None:
        """Ensure data directories exist."""
        for d in [self.data_dir, self.chroma_dir, self.cv_storage_dir, self.cover_letter_dir]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
