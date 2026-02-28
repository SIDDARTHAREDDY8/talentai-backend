"""
Resume routes - with robust error handling
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncpg
import traceback

from database import get_db
from auth_utils import get_current_user

router = APIRouter()


class AnalyzeRequest(BaseModel):
    text: str
    apiKey: Optional[str] = None

class JDMatchRequest(BaseModel):
    jobDescription: str
    apiKey: Optional[str] = None

class CoverLetterRequest(BaseModel):
    jobDescription: str
    company: Optional[str] = ""
    tone: str = "professional"
    apiKey: Optional[str] = None


@router.post("/analyze")
async def analyze_resume(
    body: AnalyzeRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    if len(body.text.strip()) < 20:
        raise HTTPException(400, "Resume text too short")

    try:
        # Step 1 — NLP skill extraction
        from nlp_engine import extract_skills, assess_resume_level, best_role_for_skills
        skills = extract_skills(body.text)
        level = assess_resume_level(skills, body.text)
        best_role = best_role_for_skills(skills)
    except Exception as e:
        print(f"NLP error: {e}")
        traceback.print_exc()
        # Fallback if spaCy fails
        skills = []
        level = "Mid"
        best_role = "Software Engineer"

    try:
        # Step 2 — AI assessment (optional — works without it)
        from ai_client import ai_analyze_resume
        ai_result = await ai_analyze_resume(body.text, body.apiKey)
    except Exception as e:
        print(f"AI error (non-fatal): {e}")
        ai_result = None

    final_level = (ai_result.get("level") or level) if ai_result else level
    final_role  = (ai_result.get("bestRole") or best_role) if ai_result else best_role
    analysis_json = ai_result or {}

    try:
        existing = await db.fetchrow("SELECT id FROM resumes WHERE user_id = $1", user["id"])
        if existing:
            await db.execute(
                """UPDATE resumes
                   SET raw_text=$1, extracted_skills=$2, ats_score=$3,
                       recommended_role=$4, level=$5, analysis_json=$6, updated_at=NOW()
                   WHERE user_id=$7""",
                body.text, skills,
                analysis_json.get("atsScore", 70),
                final_role, final_level,
                json.dumps(analysis_json),
                user["id"],
            )
        else:
            await db.execute(
                """INSERT INTO resumes
                   (user_id, raw_text, extracted_skills, ats_score, recommended_role, level, analysis_json)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                user["id"], body.text, skills,
                analysis_json.get("atsScore", 70),
                final_role, final_level,
                json.dumps(analysis_json),
            )

        await db.execute(
            "UPDATE users SET recommended_role=$1, level=$2 WHERE id=$3",
            final_role, final_level, user["id"],
        )
    except Exception as e:
        print(f"DB error: {e}")
        traceback.print_exc()

    return {
        "skills": skills,
        "level": final_level,
        "bestRole": final_role,
        "atsScore": analysis_json.get("atsScore", 70),
        "atsIssues": analysis_json.get("atsIssues", []),
        "strengths": analysis_json.get("strengths", []),
        "improvements": analysis_json.get("improvements", []),
        "summary": analysis_json.get("summary", ""),
    }


@router.get("/")
async def get_resume(
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    try:
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
    except Exception as e:
        print(f"Get resume error: {e}")
        return {"exists": False}


@router.post("/jd-match")
async def jd_match(
    body: JDMatchRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    resume = await db.fetchrow(
        "SELECT raw_text FROM resumes WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1",
        user["id"],
    )
    if not resume:
        raise HTTPException(400, "No resume found. Please analyze your resume first.")

    try:
        from ai_client import ai_match_jd
        result = await ai_match_jd(resume["raw_text"], body.jobDescription, body.apiKey)
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")

    if not result:
        raise HTTPException(500, "Analysis failed. Please try again.")

    await db.execute(
        "UPDATE users SET jd_matches_run = jd_matches_run + 1 WHERE id=$1",
        user["id"],
    )
    return result


@router.post("/cover-letter")
async def cover_letter(
    body: CoverLetterRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    resume = await db.fetchrow(
        "SELECT raw_text FROM resumes WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1",
        user["id"],
    )
    if not resume:
        raise HTTPException(400, "No resume found. Please analyze your resume first.")

    try:
        from ai_client import ai_generate_cover_letter
        letter = await ai_generate_cover_letter(
            resume["raw_text"], body.jobDescription,
            body.company, body.tone, body.apiKey,
        )
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {str(e)}")

    await db.execute(
        "UPDATE users SET cover_letters_generated = cover_letters_generated + 1 WHERE id=$1",
        user["id"],
    )
    return {"letter": letter}
