"""
FastAPI entry point — Production Dashboard API for the Job Application Agent.

Routers:
  /api/profiles       — CV profile CRUD
  /api/jobs           — Job posting CRUD + discovery
  /api/applications   — Application tracking + stats
  /api/automation     — Match, apply triggers
  /api/dashboard      — Aggregated stats + health
  /dashboard          — Web dashboard frontend (static files)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import applications, ats_checker, automation, cover_letter, dashboard, jobs, live_jobs, notifications, persona, profiles, resume
from backend.config import settings
from backend.database import init_db

logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB connection, seed sample data. Shutdown: cleanup."""
    logger.info("Starting Job Agent API...")
    await init_db()
    logger.info("Database initialized")

    # Seed sample live jobs if cache is empty (so dashboard never starts blank)
    try:
        from backend.api.live_jobs import seed_sample_listings_if_empty
        await seed_sample_listings_if_empty()
    except Exception as e:
        logger.warning("Failed to seed sample live jobs: %s", e)

    # Start the live jobs scheduler (daily PM job refresh)
    from backend.tasks.live_jobs_scheduler import start_scheduler
    scheduler = start_scheduler()
    logger.info("Live jobs scheduler started")

    yield

    # Shut down scheduler
    from backend.tasks.live_jobs_scheduler import stop_scheduler
    stop_scheduler()
    logger.info("Scheduler stopped")

    logger.info("Shutting down Job Agent API...")


app = FastAPI(
    title="Job Application Agent API",
    version="0.4.0",
    description="AI-powered automated job application agent — Production Dashboard",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── Middleware ──────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.middleware.auth import setup_auth_middleware
setup_auth_middleware(app)


# ─── API Routers ────────────────────────────────────────────────────────────

app.include_router(profiles.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(automation.router)
app.include_router(cover_letter.router)
app.include_router(live_jobs.router)
app.include_router(notifications.router)
app.include_router(persona.router)
app.include_router(resume.router)
app.include_router(ats_checker.router)
app.include_router(dashboard.router)


# ─── Static Dashboard ───────────────────────────────────────────────────────

if DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
    logger.info("Dashboard static files mounted from %s", DASHBOARD_DIR)
else:
    logger.warning("Dashboard directory not found at %s", DASHBOARD_DIR)


# ─── Root ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "message": "Job Application Agent API",
        "version": "0.4.0",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/health")
async def health():
    """Health check — reports ok if storage is reachable (JSON or PG)."""
    from backend.storage.deps import get_backend
    from backend.storage.json_backend import JsonBackend
    storage_gen = get_backend()
    storage = await storage_gen.__anext__()
    try:
        db_ok = await storage.is_available()
    finally:
        await storage_gen.aclose()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "0.4.0",
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.now(UTC).isoformat(),
    }
