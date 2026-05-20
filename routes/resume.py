"""
Resume routes
POST /resume/analyze       — NLP skill extraction + AI assessment
GET  /resume               — get current user's latest resume data
POST /resume/jd-match      — compare resume to job description
POST /resume/cover-letter  — generate cover letter
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import asyncpg

from database import get_db
from auth_utils import get_current_user
from nlp_engine import extract_skills, assess_resume_level, best_role_for_skills
from ai_client import ai_analyze_resume, ai_match_jd, ai_generate_cover_letter
from plan_guard import require_plan

router = APIRouter()
logger = logging.getLogger(__name__)


class AnalyzeRequest(BaseModel):
    text: str

class JDMatchRequest(BaseModel):
    jobDescription: str

class CoverLetterRequest(BaseModel):
    jobDescription: str
    company: Optional[str] = ""
    tone: str = "professional"


@router.post("/analyze")
async def analyze_resume(
    body: AnalyzeRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    if len(body.text.strip()) < 50:
        raise HTTPException(400, "Resume text too short")

    skills     = extract_skills(body.text)
    level      = assess_resume_level(skills, body.text)
    best_role  = best_role_for_skills(skills)
    ai_result  = await ai_analyze_resume(body.text)

    final_level = ai_result.get("level", level) if ai_result else level
    final_role  = ai_result.get("bestRole", best_role) if ai_result else best_role
    analysis    = ai_result or {}
    analysis_str = json.dumps(analysis)

    existing = await db.fetchrow("SELECT id FROM resumes WHERE user_id=$1", user["id"])
    if existing:
        await db.execute(
            """UPDATE resumes
               SET raw_text=$1, extracted_skills=$2, ats_score=$3,
                   recommended_role=$4, level=$5, analysis_json=$6, updated_at=NOW()
               WHERE user_id=$7""",
            body.text, skills, analysis.get("atsScore", 70),
            final_role, final_level, analysis_str, user["id"],
        )
    else:
        await db.execute(
            """INSERT INTO resumes (user_id, raw_text, extracted_skills, ats_score, recommended_role, level, analysis_json)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            user["id"], body.text, skills, analysis.get("atsScore", 70),
            final_role, final_level, analysis_str,
        )

    await db.execute(
        "UPDATE users SET recommended_role=$1, level=$2 WHERE id=$3",
        final_role, final_level, user["id"],
    )

    return {
        "skills": skills,
        "level": final_level,
        "bestRole": final_role,
        "atsScore": analysis.get("atsScore", 70),
        "atsIssues": analysis.get("atsIssues", []),
        "strengths": analysis.get("strengths", []),
        "improvements": analysis.get("improvements", []),
        "summary": analysis.get("summary", ""),
    }


@router.get("/")
async def get_resume(user=Depends(get_current_user), db: asyncpg.Connection = Depends(get_db)):
    row = await db.fetchrow(
        "SELECT extracted_skills, recommended_role, level FROM resumes WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1",
        user["id"],
    )
    if not row:
        return {"exists": False}
    return {
        "exists": True,
        "skills": list(row["extracted_skills"] or []),
        "recommendedRole": row["recommended_role"],
        "level": row["level"],
    }


@router.post("/jd-match")
async def jd_match(
    body: JDMatchRequest,
    user=Depends(get_current_user),   # TODO: re-enable plan guard when limits are finalised
    db: asyncpg.Connection = Depends(get_db),
):
    resume = await db.fetchrow(
        "SELECT raw_text FROM resumes WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1",
        user["id"],
    )
    if not resume:
        raise HTTPException(400, "No resume found. Please analyze your resume first.")

    result = await ai_match_jd(resume["raw_text"], body.jobDescription)
    if not result:
        raise HTTPException(500, "Analysis failed. Please try again.")

    await db.execute("UPDATE users SET jd_matches_run = jd_matches_run + 1 WHERE id=$1", user["id"])
    return result


@router.post("/cover-letter")
async def cover_letter(
    body: CoverLetterRequest,
    user=Depends(require_plan("cover_letters")),
    db: asyncpg.Connection = Depends(get_db),
):
    resume = await db.fetchrow(
        "SELECT raw_text FROM resumes WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1",
        user["id"],
    )
    if not resume:
        raise HTTPException(400, "No resume found. Please analyze your resume first.")

    letter = await ai_generate_cover_letter(
        resume["raw_text"], body.jobDescription, body.company, body.tone,
    )
    await db.execute("UPDATE users SET cover_letters_generated = cover_letters_generated + 1 WHERE id=$1", user["id"])
    return {"letter": letter}
