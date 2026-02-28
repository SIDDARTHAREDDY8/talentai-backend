"""
Authentication routes
POST /auth/register   — create account
POST /auth/login      — sign in, returns JWT
GET  /auth/me         — get current user profile
PATCH /auth/onboard   — complete onboarding
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
import asyncpg

from database import get_db
from auth_utils import hash_password, verify_password, create_token, get_current_user

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class OnboardRequest(BaseModel):
    recommendedRole: str | None = None
    dailyGoal: int = 3


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register")
async def register(body: RegisterRequest, db: asyncpg.Connection = Depends(get_db)):
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    existing = await db.fetchrow("SELECT id FROM users WHERE email = $1", body.email)
    if existing:
        raise HTTPException(400, "Email already registered")

    hashed = hash_password(body.password)
    user = await db.fetchrow(
        """INSERT INTO users (name, email, password)
           VALUES ($1, $2, $3)
           RETURNING id, name, email, plan, streak, daily_goal,
                     today_count, onboarded, target_role, level,
                     recommended_role, interviews_this_month""",
        body.name, body.email, hashed,
    )

    token = create_token(user["id"], user["email"])
    return {"token": token, **dict(user)}


@router.post("/login")
async def login(body: LoginRequest, db: asyncpg.Connection = Depends(get_db)):
    user = await db.fetchrow("SELECT * FROM users WHERE email = $1", body.email)
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(401, "Invalid email or password")

    token = create_token(user["id"], user["email"])
    return {
        "token": token,
        "id": user["id"], "name": user["name"], "email": user["email"],
        "plan": user["plan"], "streak": user["streak"],
        "daily_goal": user["daily_goal"], "today_count": user["today_count"],
        "onboarded": user["onboarded"], "target_role": user["target_role"],
        "level": user["level"], "recommended_role": user["recommended_role"],
        "interviews_this_month": user["interviews_this_month"],
    }


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {
        "id": user["id"], "name": user["name"], "email": user["email"],
        "plan": user["plan"], "streak": user["streak"],
        "daily_goal": user["daily_goal"], "today_count": user["today_count"],
        "onboarded": user["onboarded"], "target_role": user["target_role"],
        "level": user["level"], "recommended_role": user["recommended_role"],
        "interviews_this_month": user["interviews_this_month"],
        "cover_letters_generated": user["cover_letters_generated"],
        "jd_matches_run": user["jd_matches_run"],
    }


@router.patch("/onboard")
async def complete_onboarding(
    body: OnboardRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    await db.execute(
        """UPDATE users SET onboarded = TRUE,
           recommended_role = COALESCE($1, recommended_role),
           daily_goal = $2
           WHERE id = $3""",
        body.recommendedRole, body.dailyGoal, user["id"],
    )
    return {"success": True}
