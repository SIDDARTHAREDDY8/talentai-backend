"""Analytics routes — GET /analytics"""

from fastapi import APIRouter, Depends
import asyncpg

from database import get_db
from auth_utils import get_current_user

router = APIRouter()


@router.get("/")
async def get_analytics(
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    sessions = await db.fetch(
        "SELECT role, avg_score, date FROM sessions WHERE user_id=$1 ORDER BY created_at",
        user["id"],
    )
    resume = await db.fetchrow(
        "SELECT extracted_skills, ats_score FROM resumes WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 1",
        user["id"],
    )
    gap = await db.fetchrow(
        "SELECT target_role, coverage FROM skill_gaps WHERE user_id=$1 ORDER BY created_at DESC LIMIT 1",
        user["id"],
    )

    session_list = [{"role": s["role"], "avgScore": s["avg_score"], "date": s["date"]} for s in sessions]
    avg = round(sum(s["avg_score"] for s in sessions) / len(sessions)) if sessions else 0
    best = max((s["avg_score"] for s in sessions), default=0)

    # Group by role
    role_map = {}
    for s in sessions:
        role_map.setdefault(s["role"], []).append(s["avg_score"])
    by_role = [{"role": r, "avg": round(sum(v)/len(v)), "count": len(v)} for r, v in role_map.items()]

    return {
        "sessions": session_list,
        "avgScore": avg,
        "bestScore": best,
        "totalSessions": len(sessions),
        "byRole": by_role,
        "skills": list(resume["extracted_skills"] or []) if resume else [],
        "atsScore": resume["ats_score"] if resume else None,
        "targetRole": gap["target_role"] if gap else user["target_role"],
        "coverage": gap["coverage"] if gap else None,
    }
