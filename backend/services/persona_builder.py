"""
Persona Builder — learns the candidate's voice, style, and screening answers.

Pipeline:
  1. Generate onboarding questions tailored to the CV
  2. Store candidate's answers
  3. Analyze CV + answers via LLM to produce persona (style, tone, key messages)
  4. Persist persona alongside the candidate profile
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from backend.config import settings
from backend.models.profile import CandidateProfile, Persona

logger = logging.getLogger(__name__)

ONBOARDING_QUESTIONS = [
    "Describe your management or leadership style in 3-4 sentences.",
    "What is the single biggest achievement in your career so far? Quantify the impact.",
    "Why do you want to leave (or have you left) your current role?",
    "Describe a time you failed at work and what you learned from it.",
    "How do you approach stakeholder management and cross-functional collaboration?",
    "What kind of company culture do you thrive in?",
    "Where do you see yourself professionally in 3-5 years?",
    "What makes you uniquely qualified for a product management role, compared to other candidates?",
    "Describe a situation where you had to make a hard trade-off decision with limited data.",
    "What is your approach to setting and tracking OKRs or KPIs?",
]

PERSONA_ANALYSIS_PROMPT = """\
You are an expert career coach and communication analyst. Your task is to analyze a \
candidate's CV and their answers to onboarding questions, then produce a structured \
persona profile that captures their unique voice, communication style, and key selling points.

CANDIDATE PROFILE
=================
Name: {name}
Most recent role: {title} @ {company}
Years of experience: {years_exp}
Seniority: {seniority}
Key skills: {skills}

Recent experience:
{experience}

Education:
{education}

ONBOARDING Q&A
==============
{qa_text}

INSTRUCTIONS
============
Analyze the above and return a JSON object (ONLY valid JSON, no other text) with these fields:
1. "communication_style": one word — "casual", "professional", "technical", "direct", "enthusiastic", or "analytical"
2. "tone_description": one sentence describing the candidate's natural tone (e.g. "Data-driven, concise, slightly formal")
3. "key_messages": an array of exactly 3-5 short punchy sentences that represent the candidate's strongest selling points
4. "voice_sample": a 3-4 sentence paragraph ABOUT THE CANDIDATE written in the candidate's natural voice, as if they are describing themselves for a cover letter

Example output:
{{
  "communication_style": "analytical",
  "tone_description": "Precise, data-driven, with a collaborative edge",
  "key_messages": [
    "Led 3 product launches from 0-to-1, each exceeding revenue targets by 20%+",
    "Built and mentored a team of 5 PMs across two continents",
    "Specialize in B2B SaaS platforms with $10M+ ARR"
  ],
  "voice_sample": "I bring a data-driven approach to product management, having led three successful 0-to-1 launches that each exceeded revenue targets by over 20%. My strength lies in bridging the gap between technical complexity and business strategy, ensuring every feature ships with clear customer impact."
}}
"""


def _format_experience(profile: CandidateProfile) -> str:
    lines = []
    for exp in profile.experiences[:3]:
        lines.append(f"- {exp.title} @ {exp.company} ({exp.start_date} - {exp.end_date or 'Present'})")
        if exp.description:
            lines.append(f"  {exp.description[:200]}")
    return "\n".join(lines) if lines else "N/A"


def _format_education(profile: CandidateProfile) -> str:
    lines = []
    for edu in profile.education:
        parts = [edu.degree, edu.field, edu.institution]
        lines.append(" - ".join(p for p in parts if p))
    return "\n".join(lines) if lines else "N/A"


def _format_qa(answers: dict[str, str]) -> str:
    lines = []
    for q, a in answers.items():
        lines.append(f"Q: {q}\nA: {a[:300]}\n")
    return "\n".join(lines) if lines else "N/A"


def _call_llm(prompt: str, system_prompt: str = "") -> str | None:
    """Call Claude API (primary) or OpenAI (fallback). Returns the response text."""
    if settings.claude_api_key:
        try:
            import httpx
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.claude_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "system": system_prompt or "You are a career coach and communication analyst.",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]
        except Exception as e:
            logger.warning("Claude API call failed: %s", e)

    if settings.openai_api_key:
        try:
            import httpx
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o",
                    "max_tokens": 2000,
                    "messages": [
                        {"role": "system", "content": system_prompt or "You are a career coach and communication analyst."},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("OpenAI API call failed: %s", e)

    logger.warning("No LLM API key configured — persona analysis unavailable")
    return None


def build_persona(profile: CandidateProfile, answers: dict[str, str]) -> Persona | None:
    """Analyze CV + Q&A answers via LLM and return a structured Persona."""
    qa_text = _format_qa(answers)
    if not qa_text.strip():
        logger.warning("No Q&A answers provided — cannot build persona")
        return None

    prompt = PERSONA_ANALYSIS_PROMPT.format(
        name=profile.full_name or "Candidate",
        title=profile.experiences[0].title if profile.experiences else "N/A",
        company=profile.experiences[0].company if profile.experiences else "N/A",
        years_exp=profile.years_of_experience,
        seniority=profile.seniority.value if profile.seniority else "unknown",
        skills=", ".join(profile.skill_names[:15]),
        experience=_format_experience(profile),
        education=_format_education(profile),
        qa_text=qa_text,
    )

    response = _call_llm(prompt)
    if not response:
        return None

    try:
        # Extract JSON from response (handle markdown-wrapped JSON)
        json_str = response.strip()
        if json_str.startswith("```"):
            json_str = json_str.split("\n", 1)[-1]
            json_str = json_str.rsplit("```", 1)[0]
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        data = json.loads(json_str.strip())

        return Persona(
            communication_style=data.get("communication_style", "professional"),
            key_messages=data.get("key_messages", []),
            screening_answers=answers,
            tone_description=data.get("tone_description", ""),
            voice_sample=data.get("voice_sample", ""),
            onboarded=True,
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse persona from LLM response: %s\nRaw: %s", e, response[:500])
        return None


def get_onboarding_questions() -> list[str]:
    """Return the list of onboarding questions for the frontend."""
    return ONBOARDING_QUESTIONS
