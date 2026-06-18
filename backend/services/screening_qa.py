"""
Screening Q&A Auto-Answer — detects screening questions and fills them
using the persona's stored answers or LLM-generated on-the-fly.

Pipeline:
  1. Receive raw screening question text from form detection
  2. Vector-match against stored persona.screening_answers keys
  3. If close match found → return stored answer
  4. If no match → generate answer via LLM using persona context
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from backend.config import settings
from backend.models.profile import CandidateProfile, Persona

logger = logging.getLogger(__name__)

SCREENING_PROMPT = """\
You are helping a job candidate answer a screening question on an job application form.
The answer should be in the candidate's own voice, 2-4 sentences, professional yet authentic.

CANDIDATE PROFILE
=================
Name: {name}
Most recent role: {title} @ {company}
Years of experience: {years_exp}
Seniority: {seniority}
Key skills: {skills}
Background: {experience}

PERSONA
=======
Communication style: {comm_style}
Tone: {tone}
Key messages: {messages}

INSTRUCTIONS
============
Answer the following screening question in the candidate's voice.
Use the persona's communication style and tone.
Be specific, reference actual experience if possible.
Keep it to 2-4 sentences.
Do NOT use markdown or formatting — just plain text.

SCREENING QUESTION: {question}

ANSWER:
"""


def _call_llm(prompt: str) -> str | None:
    """Call Claude API (primary) or OpenAI (fallback)."""
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
                    "max_tokens": 800,
                    "system": "You are a career coach helping a candidate answer job screening questions.",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=45,
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
                    "max_tokens": 800,
                    "messages": [
                        {"role": "system", "content": "You are a career coach helping a candidate answer job screening questions."},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=45,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("OpenAI API call failed: %s", e)

    logger.warning("No LLM API key configured — cannot generate screening answer")
    return None


def is_screening_field(field_hints: list[str]) -> bool:
    """Detect if a form field is a screening question needing auto-answer.

    Returns True if the field hints suggest a screening/open-ended question.
    """
    screening_keywords = [
        "why", "tell us", "describe", "explain", "reason", "interest",
        "additional info", "anything else", "cover letter", "message",
        "share", "elaborate", "how would you", "what is your",
        "why should we", "why are you", "briefly",
    ]
    hints_str = " ".join(field.hints).lower()
    return any(kw in hints_str for kw in screening_keywords)


def answer_question(
    question_text: str,
    profile: CandidateProfile,
    persona: Persona | None,
) -> str | None:
    """Answer a screening question. Returns the answer text or None."""
    if not question_text or not question_text.strip():
        return None

    # Step 1: Try to match against stored screening answers
    if persona and persona.screening_answers:
        stored = persona.screening_answers
        question_lower = question_text.lower().strip()

        # Exact match first
        for q, a in stored.items():
            if q.lower().strip() == question_lower:
                logger.info("Screening QA: exact match found for '%s'", question_text[:60])
                return a

        # Keyword overlap match
        best_match = None
        best_score = 0
        question_words = set(question_lower.split())
        for q, a in stored.items():
            q_words = set(q.lower().split())
            overlap = len(question_words & q_words)
            if overlap > best_score:
                best_score = overlap
                best_match = a

        if best_score >= 3 and best_match:
            logger.info("Screening QA: keyword match (score=%d) for '%s'", best_score, question_text[:60])
            return best_match

    # Step 2: No stored match — generate via LLM
    logger.info("Screening QA: generating answer for '%s'", question_text[:60])

    # Format experience
    exp_lines = []
    for e in profile.experiences[:3]:
        exp_lines.append(f"{e.title} @ {e.company} ({e.start_date} – {e.end_date or 'Present'})")
    experience_text = "; ".join(exp_lines) or "N/A"

    messages_text = " | ".join(persona.key_messages) if persona and persona.key_messages else "N/A"
    comm_style = persona.communication_style if persona else "professional"
    tone = persona.tone_description if persona else "professional"

    prompt = SCREENING_PROMPT.format(
        name=profile.full_name or "Candidate",
        title=profile.experiences[0].title if profile.experiences else "N/A",
        company=profile.experiences[0].company if profile.experiences else "N/A",
        years_exp=profile.years_of_experience,
        seniority=profile.seniority.value if profile.seniority else "unknown",
        skills=", ".join(profile.skill_names[:10]),
        experience=experience_text,
        comm_style=comm_style,
        tone=tone,
        messages=messages_text,
        question=question_text,
    )

    return _call_llm(prompt)
