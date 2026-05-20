"""
Settings routes — PATCH /settings
Plan changes are handled exclusively via Stripe webhooks (routes/billing.py).
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import asyncpg

from database import get_db
from auth_utils import get_current_user

router = APIRouter()


class UpdateSettingsRequest(BaseModel):
    dailyGoal: Optional[int] = None


@router.patch("/")
async def update_settings(
    body: UpdateSettingsRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    if body.dailyGoal is not None:
        goal = max(1, min(10, body.dailyGoal))
        await db.execute("UPDATE users SET daily_goal=$1 WHERE id=$2", goal, user["id"])
    return {"success": True}
