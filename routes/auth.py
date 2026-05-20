"""
Authentication routes
POST /auth/register        — create account
POST /auth/login           — sign in, returns JWT
GET  /auth/me              — get current user profile
PATCH /auth/onboard        — complete onboarding
POST /auth/forgot-password — request password reset email
POST /auth/reset-password  — complete password reset with token
"""

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
import asyncpg
import httpx

from database import get_db
from auth_utils import hash_password, verify_password, create_token, get_current_user
from email_service import send_password_reset_email, send_welcome_email

router = APIRouter()
logger = logging.getLogger(__name__)

# OAuth credentials — set in .env, never exposed to the frontend
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GITHUB_CLIENT_ID     = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")


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

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    password: str

class OAuthCallbackRequest(BaseModel):
    code: str
    redirectUri: str


def _user_dict(user) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "plan": user["plan"],
        "streak": user["streak"],
        "daily_goal": user["daily_goal"],
        "today_count": user["today_count"],
        "onboarded": user["onboarded"],
        "target_role": user["target_role"],
        "level": user["level"],
        "recommended_role": user["recommended_role"],
        "interviews_this_month": user["interviews_this_month"],
        "cover_letters_generated": user["cover_letters_generated"],
        "jd_matches_run": user["jd_matches_run"],
        "subscription_status": user.get("subscription_status", "active"),
    }


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
           RETURNING *""",
        body.name, body.email, hashed,
    )

    try:
        send_welcome_email(user["email"], user["name"])
    except Exception:
        logger.warning("Failed to send welcome email", exc_info=True)

    token = create_token(user["id"], user["email"])
    return {"token": token, **_user_dict(user)}


@router.post("/login")
async def login(body: LoginRequest, db: asyncpg.Connection = Depends(get_db)):
    user = await db.fetchrow("SELECT * FROM users WHERE email = $1", body.email)
    if not user:
        raise HTTPException(401, "Invalid email or password")
    if not user["password"]:
        provider = user.get("oauth_provider") or "a social provider"
        raise HTTPException(401, f"This account was created with {provider.title()} sign-in. Please use that button to log in.")
    if not verify_password(body.password, user["password"]):
        raise HTTPException(401, "Invalid email or password")

    token = create_token(user["id"], user["email"])
    return {"token": token, **_user_dict(user)}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return _user_dict(user)


@router.patch("/onboard")
async def complete_onboarding(
    body: OnboardRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    await db.execute(
        """UPDATE users SET onboarded=TRUE,
           recommended_role=COALESCE($1, recommended_role),
           daily_goal=$2
           WHERE id=$3""",
        body.recommendedRole, body.dailyGoal, user["id"],
    )
    return {"success": True}


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: asyncpg.Connection = Depends(get_db)):
    user = await db.fetchrow("SELECT id, name, email FROM users WHERE email=$1", body.email)
    # Always return success to avoid leaking email existence
    if not user:
        return {"message": "If that email exists, a reset link has been sent."}

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    await db.execute(
        "UPDATE users SET password_reset_token=$1, password_reset_expires=$2 WHERE id=$3",
        token, expires, user["id"],
    )

    try:
        send_password_reset_email(user["email"], user["name"], token)
    except Exception:
        logger.warning("Failed to send reset email", exc_info=True)

    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: asyncpg.Connection = Depends(get_db)):
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    user = await db.fetchrow(
        """SELECT id FROM users
           WHERE password_reset_token=$1
           AND password_reset_expires > NOW()""",
        body.token,
    )
    if not user:
        raise HTTPException(400, "Invalid or expired reset link. Please request a new one.")

    hashed = hash_password(body.password)
    await db.execute(
        """UPDATE users
           SET password=$1, password_reset_token=NULL, password_reset_expires=NULL
           WHERE id=$2""",
        hashed, user["id"],
    )
    return {"message": "Password reset successfully. You can now sign in."}


# ──────────────────────────────────────────────────────────────────────────────
# OAuth helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _fetch_google_user(code: str, redirect_uri: str) -> dict:
    """Exchange Google auth code for user info."""
    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Exchange code for tokens
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  redirect_uri,
                "grant_type":    "authorization_code",
            },
        )
        tokens = resp.json()
        if resp.status_code != 200 or "error" in tokens:
            msg = tokens.get("error_description") or tokens.get("error") or resp.text[:200]
            logger.error(f"Google token exchange failed: {msg}")
            raise HTTPException(400, f"Google sign-in failed: {msg}")

        # 2. Fetch user profile
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if resp.status_code != 200:
            raise HTTPException(400, "Could not fetch Google profile")
        info = resp.json()

    email = info.get("email")
    if not email:
        raise HTTPException(400, "Google did not provide an email address")

    return {
        "provider":  "google",
        "oauth_id":  info["sub"],
        "email":     email,
        "name":      info.get("name") or email.split("@")[0],
    }


async def _fetch_github_user(code: str, redirect_uri: str) -> dict:
    """Exchange GitHub auth code for user info."""
    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Exchange code for access token
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id":     GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  redirect_uri,
            },
        )
        tokens = resp.json()
        if resp.status_code != 200 or "error" in tokens:
            msg = tokens.get("error_description") or tokens.get("error") or resp.text[:200]
            logger.error(f"GitHub token exchange failed: {msg}")
            raise HTTPException(400, f"GitHub sign-in failed: {msg}")

        access_token = tokens["access_token"]
        gh_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # 2. Fetch user profile
        resp = await client.get("https://api.github.com/user", headers=gh_headers)
        if resp.status_code != 200:
            raise HTTPException(400, "Could not fetch GitHub profile")
        info = resp.json()

        # 3. Fetch primary verified email (may be private on profile)
        email = info.get("email")
        if not email:
            resp = await client.get("https://api.github.com/user/emails", headers=gh_headers)
            if resp.status_code == 200:
                emails = resp.json()
                primary = next(
                    (e for e in emails if e.get("primary") and e.get("verified")), None
                )
                if primary:
                    email = primary["email"]

    if not email:
        raise HTTPException(
            400,
            "Could not retrieve your email from GitHub. "
            "Please make your primary email public in GitHub Settings → Emails and try again.",
        )

    return {
        "provider": "github",
        "oauth_id": str(info["id"]),
        "email":    email,
        "name":     info.get("name") or info.get("login") or "GitHub User",
    }


async def _oauth_upsert(db: asyncpg.Connection, info: dict):
    """
    Find or create a user from OAuth provider info.
    If an account with the same email exists, link the OAuth provider to it
    (lets users who registered with email/password also sign in via OAuth).
    """
    # Try by provider + oauth_id (returning user)
    user = await db.fetchrow(
        "SELECT * FROM users WHERE oauth_provider=$1 AND oauth_id=$2",
        info["provider"], info["oauth_id"],
    )
    if user:
        return user

    # Try by email — link OAuth to an existing account
    user = await db.fetchrow("SELECT * FROM users WHERE email=$1", info["email"])
    if user:
        user = await db.fetchrow(
            "UPDATE users SET oauth_provider=$1, oauth_id=$2 WHERE id=$3 RETURNING *",
            info["provider"], info["oauth_id"], user["id"],
        )
        return user

    # Create a brand-new account (no password for OAuth users)
    user = await db.fetchrow(
        """INSERT INTO users (name, email, oauth_provider, oauth_id)
           VALUES ($1, $2, $3, $4)
           RETURNING *""",
        info["name"], info["email"], info["provider"], info["oauth_id"],
    )
    return user


# ──────────────────────────────────────────────────────────────────────────────
# OAuth endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/google/callback")
async def google_oauth_callback(
    body: OAuthCallbackRequest,
    db: asyncpg.Connection = Depends(get_db),
):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(501, "Google OAuth is not configured on this server")

    provider_info = await _fetch_google_user(body.code, body.redirectUri)
    user  = await _oauth_upsert(db, provider_info)
    token = create_token(user["id"], user["email"])
    return {"token": token, **_user_dict(user)}


@router.post("/github/callback")
async def github_oauth_callback(
    body: OAuthCallbackRequest,
    db: asyncpg.Connection = Depends(get_db),
):
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(501, "GitHub OAuth is not configured on this server")

    provider_info = await _fetch_github_user(body.code, body.redirectUri)
    user  = await _oauth_upsert(db, provider_info)
    token = create_token(user["id"], user["email"])
    return {"token": token, **_user_dict(user)}
