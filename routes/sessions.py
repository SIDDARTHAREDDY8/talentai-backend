"""
Sessions routes
POST /sessions         — save completed interview session
GET  /sessions         — get all sessions for current user
GET  /sessions/:id     — get single session with question detail
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import asyncpg
from datetime import date

from database import get_db
from auth_utils import get_current_user

router = APIRouter()


class QuestionResult(BaseModel):
    question: str
    userAnswer: str
    score: int
    feedback: Optional[str] = ""
    idealAnswer: Optional[str] = ""
    missed: Optional[str] = ""


class SaveSessionRequest(BaseModel):
    role: str
    avgScore: int
    questions: int
    scores: List[QuestionResult]


@router.post("/")
async def save_session(
    body: SaveSessionRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    today_str = date.today().strftime("%m/%d/%Y")

    # Insert session row
    session = await db.fetchrow(
        """INSERT INTO sessions (user_id, role, avg_score, questions, date)
           VALUES ($1, $2, $3, $4, $5) RETURNING id""",
        user["id"], body.role, body.avgScore, body.questions, today_str,
    )
    session_id = session["id"]

    # Insert each question result
    for q in body.scores:
        await db.execute(
            """INSERT INTO session_questions
               (session_id, question, user_answer, score, feedback, ideal_answer, missed)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            session_id, q.question, q.userAnswer, q.score,
            q.feedback, q.idealAnswer, q.missed,
        )

    # Update user streak and monthly interview count
    today_iso = date.today().isoformat()
    u = await db.fetchrow(
        "SELECT streak, last_practice_date, interviews_this_month, month_key FROM users WHERE id=$1",
        user["id"],
    )

    from datetime import date as dt, timedelta
    yesterday = (dt.today() - timedelta(days=1)).isoformat()
    current_month = f"{dt.today().year}-{dt.today().month}"

    new_streak = u["streak"]
    if u["last_practice_date"] == yesterday:
        new_streak = (u["streak"] or 0) + 1
    elif u["last_practice_date"] != today_iso:
        new_streak = 1

    # Reset monthly counter if new month
    interviews_month = u["interviews_this_month"] or 0
    if u["month_key"] != current_month:
        interviews_month = 1
    else:
        interviews_month += 1

    await db.execute(
        """UPDATE users SET
           streak=$1, last_practice_date=$2,
           interviews_this_month=$3, month_key=$4
           WHERE id=$5""",
        new_streak, today_iso, interviews_month, current_month, user["id"],
    )

    return {
        "id": session_id,
        "role": body.role,
        "avgScore": body.avgScore,
        "questions": body.questions,
        "date": today_str,
        "streak": new_streak,
        "interviewsThisMonth": interviews_month,
    }


@router.get("/")
async def get_sessions(
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    rows = await db.fetch(
        """SELECT id, role, avg_score, questions, date
           FROM sessions WHERE user_id=$1 ORDER BY created_at ASC""",
        user["id"],
    )
    return {
        "sessions": [
            {
                "id": r["id"],
                "role": r["role"],
                "avgScore": r["avg_score"],
                "questions": r["questions"],
                "date": r["date"],
            }
            for r in rows
        ]
    }


@router.get("/{session_id}")
async def get_session_detail(
    session_id: int,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    session = await db.fetchrow(
        "SELECT * FROM sessions WHERE id=$1 AND user_id=$2",
        session_id, user["id"],
    )
    if not session:
        raise HTTPException(404, "Session not found")

    questions = await db.fetch(
        "SELECT * FROM session_questions WHERE session_id=$1 ORDER BY id",
        session_id,
    )

    return {
        "id": session["id"],
        "role": session["role"],
        "avgScore": session["avg_score"],
        "date": session["date"],
        "scores": [
            {
                "q": q["question"],
                "score": q["score"],
                "feedback": q["feedback"],
                "ideal": q["ideal_answer"],
                "missed": q["missed"],
                "userAnswer": q["user_answer"],
            }
            for q in questions
        ],
    }
