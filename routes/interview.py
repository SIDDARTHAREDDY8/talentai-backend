"""
Interview routes
POST /interview/evaluate   — score a single answer (NLP + AI blend)
POST /interview/coach      — AI career coach chat message
POST /interview/gaps       — skill gap learning plan
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
import asyncpg

from database import get_db
from auth_utils import get_current_user
from nlp_engine import compute_answer_score
from ai_client import ai_evaluate_answer, ai_learning_plan

router = APIRouter()


class EvaluateRequest(BaseModel):
    question: str
    userAnswer: str
    referenceAnswer: str
    apiKey: Optional[str] = None


class CoachMessage(BaseModel):
    content: str

class CoachRequest(BaseModel):
    messages: List[CoachMessage]
    skills: List[str] = []
    level: Optional[str] = None
    targetRole: Optional[str] = None
    apiKey: Optional[str] = None


class GapsRequest(BaseModel):
    role: str
    missingSkills: List[str]
    apiKey: Optional[str] = None


@router.post("/evaluate")
async def evaluate_answer(
    body: EvaluateRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Two-layer answer evaluation:
    Layer 1 — scikit-learn TF-IDF cosine similarity (fast, ML-based)
    Layer 2 — AI qualitative evaluation (feedback, ideal answer)
    Final score = AI score * 0.7 + similarity score * 0.3
    """
    # Layer 1: scikit-learn similarity
    sim_score, tfidf_raw, jaccard_raw = compute_answer_score(
        body.userAnswer, body.referenceAnswer
    )

    # Layer 2: AI evaluation
    ai_result = await ai_evaluate_answer(
        body.question, body.userAnswer, body.referenceAnswer, body.apiKey
    )

    if ai_result:
        # Blend AI score (70%) with NLP similarity (30%)
        final_score = round(ai_result["score"] * 0.7 + sim_score * 0.3)
        final_score = max(5, min(100, final_score))
        feedback    = ai_result.get("feedback", "")
        ideal       = ai_result.get("ideal") or body.referenceAnswer
        missed      = ai_result.get("missed", "")
    else:
        # Fallback: use NLP score only + always show reference as ideal
        final_score = sim_score
        feedback    = "Score based on keyword and semantic similarity analysis."
        ideal       = body.referenceAnswer
        missed      = ""

    # Update today_count
    await db.execute(
        "UPDATE users SET today_count = today_count + 1 WHERE id=$1",
        user["id"],
    )

    return {
        "score": final_score,
        "feedback": feedback,
        "ideal": ideal,
        "missed": missed,
        "tfidfSimilarity": round(tfidf_raw * 100, 1),
        "jaccardSimilarity": round(jaccard_raw * 100, 1),
    }


@router.post("/coach")
async def career_coach(
    body: CoachRequest,
    user=Depends(get_current_user),
):
    """
    Stateless AI career coach — receives full conversation history
    and returns next assistant message.
    """
    import httpx, os, json

    key = body.apiKey or os.getenv("AI_API_KEY", "")
    if not key:
        return {"reply": "AI API key not configured. Add your key in Settings."}

    system = f"""You are an expert AI career coach for tech professionals.
User profile: Skills: {', '.join(body.skills[:20]) or 'not provided'}.
Level: {body.level or 'unknown'}. Target role: {body.targetRole or 'not specified'}.
Be practical, specific, and encouraging. Keep responses under 200 words unless depth is genuinely needed."""

    messages = [{"role": m.content.split(":")[0] if ":" in m.content else "user",
                  "content": m.content} for m in body.messages]
    # Actually use the messages as-is from the frontend
    messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": m.content}
                for i, m in enumerate(body.messages)]

    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 600,
        "system": system,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=payload,
        )
        data = resp.json()
        reply = data.get("content", [{}])[0].get("text", "Sorry, I couldn't respond.")

    return {"reply": reply}


@router.post("/gaps")
async def skill_gaps_plan(
    body: GapsRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """Generate AI learning plan for missing skills and save gap analysis."""
    plan = await ai_learning_plan(body.role, body.missingSkills, body.apiKey)

    # Save to DB
    resume = await db.fetchrow(
        "SELECT extracted_skills FROM resumes WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1",
        user["id"],
    )
    present = list(resume["extracted_skills"] or []) if resume else []

    # Compute coverage
    from nlp_engine import SKILLS
    ROLE_SKILLS = {
        "Software Engineer":  ["Python","JavaScript","React","Node.js","SQL","Git","Docker","System Design","Algorithms"],
        "Data Scientist":     ["Python","Machine Learning","Statistics","Pandas","NumPy","scikit-learn","TensorFlow","SQL"],
        "Data Engineer":      ["Python","SQL","Apache Spark","Kafka","Airflow","AWS","ETL","Docker"],
        "ML Engineer":        ["Python","TensorFlow","PyTorch","MLOps","Docker","Kubernetes","scikit-learn"],
        "Frontend Developer": ["JavaScript","TypeScript","React","CSS","HTML","Git","Webpack"],
    }
    req = ROLE_SKILLS.get(body.role, [])
    present_set = {s.lower() for s in present}
    present_req = [s for s in req if s.lower() in present_set]
    coverage = round(len(present_req) / len(req) * 100) if req else 0

    import json as _json
    await db.execute(
        """INSERT INTO skill_gaps (user_id, target_role, coverage, present_skills, missing_skills, learning_plan)
           VALUES ($1, $2, $3, $4, $5, $6)""",
        user["id"], body.role, coverage, present_req, body.missingSkills, _json.dumps(plan or {}),
    )

    await db.execute(
        "UPDATE users SET target_role=$1 WHERE id=$2",
        body.role, user["id"],
    )

    # Return plan fields directly so frontend can access plan.priority, plan.timeline etc
    result = plan or {}
    result["coverage"] = coverage
    result["presentSkills"] = present_req
    return result
