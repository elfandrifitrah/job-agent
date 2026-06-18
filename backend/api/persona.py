"""
API router for AI Persona — onboarding Q&A, voice analysis, persona CRUD.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import storage as json_storage
from backend.models.profile import Persona
from backend.services.persona_builder import build_persona, get_onboarding_questions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/persona", tags=["persona"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class QuestionsResponse(BaseModel):
    questions: list[str]


class AnswerItem(BaseModel):
    question: str
    answer: str


class SubmitAnswersRequest(BaseModel):
    profile_id: str
    answers: list[AnswerItem]


class BuildPersonaRequest(BaseModel):
    name: str = ""
    raw_text: str = ""
    skills: list[str] = []
    experiences: list[dict] = []
    education: list[dict] = []
    years_experience: float = 0
    seniority: str = "mid"
    answers: list[AnswerItem]


class PersonaResponse(BaseModel):
    profile_id: str
    communication_style: str = "professional"
    key_messages: list[str] = []
    tone_description: str = ""
    voice_sample: str = ""
    screening_answers: dict[str, str] = {}
    onboarded: bool = False


# ─── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/questions", response_model=QuestionsResponse)
async def get_questions():
    """Return the list of onboarding questions."""
    return QuestionsResponse(questions=get_onboarding_questions())


@router.post("/build", response_model=PersonaResponse)
async def build_persona_stateless(req: BuildPersonaRequest):
    """Build persona from raw text + answers — stateless, nothing stored."""
    from backend.models.profile import CandidateProfile, SeniorityLevel

    skills_models = [{"name": s, "category": "general"} for s in req.skills]
    exp_models = [
        {"title": e.get("title", ""), "company": e.get("company", ""),
         "description": e.get("description", ""), "start_date": e.get("start_date"),
         "end_date": e.get("end_date")}
        for e in req.experiences
    ]
    edu_models = [
        {"institution": e.get("institution", ""), "degree": e.get("degree", ""),
         "field": e.get("field", "")}
        for e in req.education
    ]

    profile = CandidateProfile(
        raw_text=req.raw_text,
        full_name=req.name,
        skills=skills_models,
        experiences=exp_models,
        education=edu_models,
        years_of_experience=req.years_experience,
        seniority=SeniorityLevel(req.seniority if req.seniority in [e.value for e in SeniorityLevel] else "unknown"),
    )

    answers_dict = {a.question: a.answer for a in req.answers}
    persona = build_persona(profile, answers_dict)
    if not persona:
        raise HTTPException(
            status_code=502,
            detail="Persona analysis failed. Check LLM API keys are configured.",
        )

    return PersonaResponse(
        profile_id="local",
        communication_style=persona.communication_style,
        key_messages=persona.key_messages,
        tone_description=persona.tone_description,
        voice_sample=persona.voice_sample,
        screening_answers=persona.screening_answers,
        onboarded=persona.onboarded,
    )


@router.post("/submit-answers", response_model=PersonaResponse)
async def submit_answers(req: SubmitAnswersRequest):
    """Submit Q&A answers, build persona via LLM, and persist."""
    # Find the profile
    profiles = json_storage.get_profiles()
    profile_data = None
    for p in profiles:
        if p.get("id") == req.profile_id:
            profile_data = p
            break

    if not profile_data:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Deserialize to CandidateProfile
    from backend.models.profile import CandidateProfile
    profile = CandidateProfile(**profile_data)

    # Convert answers to dict
    answers_dict = {a.question: a.answer for a in req.answers}

    # Build persona
    persona = build_persona(profile, answers_dict)
    if not persona:
        raise HTTPException(
            status_code=502,
            detail="Persona analysis failed. Check LLM API keys are configured.",
        )

    # Persist persona into the stored profile
    data = json_storage._data
    stored_profiles = data.get("profiles", [])
    for i, p in enumerate(stored_profiles):
        if p.get("id") == req.profile_id:
            stored_profiles[i]["persona"] = persona.model_dump(mode="json")
            data["profiles"] = stored_profiles
            json_storage._save()
            break

    return PersonaResponse(
        profile_id=req.profile_id,
        communication_style=persona.communication_style,
        key_messages=persona.key_messages,
        tone_description=persona.tone_description,
        voice_sample=persona.voice_sample,
        screening_answers=persona.screening_answers,
        onboarded=persona.onboarded,
    )


@router.get("/{profile_id}", response_model=PersonaResponse)
async def get_persona(profile_id: str):
    """Get the persona for a given profile."""
    profiles = json_storage.get_profiles()
    for p in profiles:
        if p.get("id") == profile_id:
            persona_data = p.get("persona")
            if not persona_data:
                raise HTTPException(status_code=404, detail="No persona found for this profile. Submit answers first.")
            persona = Persona(**persona_data)
            return PersonaResponse(
                profile_id=profile_id,
                communication_style=persona.communication_style,
                key_messages=persona.key_messages,
                tone_description=persona.tone_description,
                voice_sample=persona.voice_sample,
                screening_answers=persona.screening_answers,
                onboarded=persona.onboarded,
            )

    raise HTTPException(status_code=404, detail="Profile not found")


@router.post("/rebuild/{profile_id}", response_model=PersonaResponse)
async def rebuild_persona(profile_id: str):
    """Re-analyze persona from existing Q&A answers."""
    profiles = json_storage.get_profiles()
    profile_data = None
    for p in profiles:
        if p.get("id") == profile_id:
            profile_data = p
            break

    if not profile_data:
        raise HTTPException(status_code=404, detail="Profile not found")

    from backend.models.profile import CandidateProfile
    profile = CandidateProfile(**profile_data)

    existing_persona = profile_data.get("persona")
    if not existing_persona or not existing_persona.get("screening_answers"):
        raise HTTPException(status_code=400, detail="No existing Q&A answers to rebuild from. Submit answers first.")

    persona = build_persona(profile, existing_persona["screening_answers"])
    if not persona:
        raise HTTPException(status_code=502, detail="Persona rebuild failed.")

    data = json_storage._data
    stored_profiles = data.get("profiles", [])
    for i, p in enumerate(stored_profiles):
        if p.get("id") == profile_id:
            stored_profiles[i]["persona"] = persona.model_dump(mode="json")
            data["profiles"] = stored_profiles
            json_storage._save()
            break

    return PersonaResponse(
        profile_id=profile_id,
        communication_style=persona.communication_style,
        key_messages=persona.key_messages,
        tone_description=persona.tone_description,
        voice_sample=persona.voice_sample,
        screening_answers=persona.screening_answers,
        onboarded=persona.onboarded,
    )
