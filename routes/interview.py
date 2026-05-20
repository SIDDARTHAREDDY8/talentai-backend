"""
Interview routes
POST /interview/evaluate  — score a single answer
POST /interview/coach     — AI career coach message
POST /interview/gaps      — skill gap learning plan
"""

import logging
from typing import Literal, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import asyncpg

from database import get_db
from auth_utils import get_current_user
from nlp_engine import compute_answer_score
from ai_client import ai_evaluate_answer, ai_learning_plan, ai_coach_reply
from plan_guard import require_plan

router = APIRouter()
logger = logging.getLogger(__name__)


class EvaluateRequest(BaseModel):
    question: str
    userAnswer: str
    referenceAnswer: str


class CoachMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CoachRequest(BaseModel):
    messages: List[CoachMessage]
    skills: List[str] = []
    level: Optional[str] = None
    targetRole: Optional[str] = None


class GapsRequest(BaseModel):
    role: str
    missingSkills: List[str]


@router.post("/evaluate")
async def evaluate_answer(
    body: EvaluateRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Two-layer answer evaluation:
    Layer 1 — scikit-learn TF-IDF cosine similarity
    Layer 2 — AI qualitative evaluation
    Final score = AI score * 0.7 + NLP similarity * 0.3
    """
    sim_score, tfidf_raw, jaccard_raw = compute_answer_score(body.userAnswer, body.referenceAnswer)
    ai_result = await ai_evaluate_answer(body.question, body.userAnswer, body.referenceAnswer)

    if ai_result:
        final_score = round(ai_result["score"] * 0.7 + sim_score * 0.3)
        final_score = max(5, min(100, final_score))
        feedback    = ai_result.get("feedback", "")
        ideal       = ai_result.get("ideal") or body.referenceAnswer
        missed      = ai_result.get("missed", "")
    else:
        final_score = sim_score
        feedback    = "Score based on keyword and semantic similarity analysis."
        ideal       = body.referenceAnswer
        missed      = ""

    await db.execute("UPDATE users SET today_count = today_count + 1 WHERE id=$1", user["id"])

    return {
        "score": final_score,
        "feedback": feedback,
        "ideal": ideal,
        "missed": missed,
        "tfidfSimilarity": round(tfidf_raw * 100, 1),
        "jaccardSimilarity": round(jaccard_raw * 100, 1),
    }


@router.post("/coach")
async def career_coach(body: CoachRequest, user=Depends(get_current_user)):
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    reply = await ai_coach_reply(messages, body.skills, body.level, body.targetRole)
    return {"reply": reply}


@router.post("/gaps")
async def skill_gaps_plan(
    body: GapsRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    plan = await ai_learning_plan(body.role, body.missingSkills)

    resume = await db.fetchrow(
        "SELECT extracted_skills FROM resumes WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1",
        user["id"],
    )
    present = list(resume["extracted_skills"] or []) if resume else []

    ROLE_SKILLS = {
        "Software Engineer":  ["Python", "JavaScript", "React", "Node.js", "SQL", "Git", "Docker", "System Design", "Algorithms"],
        "Data Scientist":     ["Python", "Machine Learning", "Statistics", "Pandas", "NumPy", "scikit-learn", "TensorFlow", "SQL"],
        "Data Engineer":      ["Python", "SQL", "Apache Spark", "Kafka", "Airflow", "AWS", "ETL", "Docker"],
        "ML Engineer":        ["Python", "TensorFlow", "PyTorch", "MLOps", "Docker", "Kubernetes", "scikit-learn"],
        "Frontend Developer": ["JavaScript", "TypeScript", "React", "CSS", "HTML", "Git", "Webpack"],
    }
    req = ROLE_SKILLS.get(body.role, [])
    present_set = {s.lower() for s in present}
    present_req = [s for s in req if s.lower() in present_set]
    coverage = round(len(present_req) / len(req) * 100) if req else 0

    import json as _json
    try:
        await db.execute(
            """INSERT INTO skill_gaps (user_id, target_role, coverage, present_skills, missing_skills, learning_plan)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            user["id"], body.role, coverage, present_req, body.missingSkills, _json.dumps(plan or {}),
        )
        await db.execute("UPDATE users SET target_role=$1 WHERE id=$2", body.role, user["id"])
    except Exception as exc:
        logger.warning(f"skill_gaps DB write failed (non-fatal): {exc}")

    result = plan or {}
    result["coverage"] = coverage
    result["presentSkills"] = present_req
    return result
