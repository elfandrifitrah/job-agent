---
title: Job Agent
emoji: 🤖
colorFrom: gray
colorTo: gray
sdk: docker
pinned: false
---

# Job Application Agent 🤖

> **Built 100% Vibe Coding by Elfandri Fitrah ❤️**

An AI-powered automated job application agent that parses CVs, semantically matches candidates to job listings, generates tailored cover letters, and submits applications — all through a brutalist-warm web dashboard.

---

## What does it do?

This project automates the tedious parts of the job search process. Instead of manually applying to each job one-by-one, you upload your CV once and let the agent scan, match, and apply to relevant positions on your behalf.

It connects to multiple job aggregator APIs to discover live listings, scores them against your profile using semantic AI matching, generates personalized cover letters, and submits applications through browser automation — all tracked in a real-time dashboard.

---

## Specific questions this project answers

| Question | Answer |
|---|---|
| "Which jobs match my skills?" | The semantic AI engine compares your CV against every discovered job and returns a match score (0–100%). |
| "Where should I focus my applications?" | The dashboard shows which jobs scored highest, which skills overlap, and where gaps exist — so you know which applications are worth pursuing. |
| "How do I write a cover letter fast?" | One click generates a tailored cover letter for any matched job, using your actual skills and experience. |
| "Am I making progress?" | The dashboard tracks total profiles, jobs discovered, applications submitted, match scores, and daily application limits. |
| "What jobs are out there right now?" | Live job discovery pulls from Jobicy, Adzuna, and other sources in real-time — no manual searching required. |
| "Did my application go through?" | Every application is logged with status (submitted, matched, error, CAPTCHA blocked) so you know exactly what happened. |

---

## How it works

```
Upload CV → AI Parse → Semantic Match → Cover Letter Gen → Auto-Apply
```

1. **Upload your CV** — Drag & drop PDF, DOCX, or TXT. The AI extracts skills, experience, education, and seniority level.
2. **Discover jobs** — The agent fetches live job listings from multiple sources based on your profile.
3. **Semantic matching** — Every job is scored against your skills using vector embeddings. Jobs above threshold are flagged as eligible.
4. **Cover letter generation** — AI writes a tailored cover letter for any matched job, referencing your actual experience.
5. **Auto-apply** — The browser automation engine fills and submits applications for eligible jobs (CLI mode).
6. **Monitor** — The dashboard shows live stats, application history, source breakdowns, and system health.

---

## How to use it

### Via the web dashboard (easiest)

Visit the live dashboard at your deployed instance:

```
https://your-deployment/dashboard/
```

1. Upload your CV in the upload section
2. Click **Parse CV & Extract Profile**
3. Review your parsed profile (skills, experience, education)
4. Click **Discover Jobs** to find relevant listings
5. Click **Match Jobs** to score them against your profile
6. Click **Analyze & Apply** to see eligible matches and auto-apply

### Via the CLI

```bash
# Install
pip install -r requirements.txt

# Parse a CV
job-agent parse ./my-cv.pdf

# Match against jobs
job-agent match ./my-cv.pdf

# Full pipeline with auto-apply
job-agent analyze ./my-cv.pdf --apply --threshold 0.6
```

### Via the API

```
GET  /health              — System health check
GET  /api/dashboard/stats — Dashboard statistics
POST /api/profiles/parse  — Upload and parse a CV
POST /api/automation/match — Score profile against jobs
POST /api/automation/analyze — Full skills analysis with auto-apply
POST /api/cover-letter/generate — Generate a cover letter
```

Full API documentation at `/docs` when the server is running.

---

## Benefits

- **Save hours per week** — No more manual job scrolling, form filling, or cover letter writing
- **Higher quality applications** — Semantic matching ensures you only apply where you're a strong fit
- **Never miss a deadline** — Automated discovery catches jobs you'd otherwise miss
- **Data-driven decisions** — Know your match scores, skill gaps, and application success rates
- **One CV, infinite applications** — Upload once, apply to hundreds of jobs with zero repetition
- **Transparent process** — Every action is logged and visible in the dashboard

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | HTML/CSS/JS dashboard (brutalist warm theme) |
| Backend | Python FastAPI |
| AI matching | Semantic embeddings + vector similarity |
| Browser automation | Playwright |
| Storage | JSON file backend (default) or PostgreSQL |
| Job sources | Jobicy, Adzuna, custom scrape pipelines |
| Deployment | Docker, Hugging Face Spaces |

---

## Live demo

Deployed on Hugging Face Spaces:
➡ [elfandrifitrah-job-agent-dashboard.hf.space](https://elfandrifitrah-job-agent-dashboard.hf.space)
