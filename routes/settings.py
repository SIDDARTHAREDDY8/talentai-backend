"""Settings routes — PATCH /settings"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
import asyncpg

from database import get_db
from auth_utils import get_current_user

router = APIRouter()


class UpdateSettingsRequest(BaseModel):
    dailyGoal: Optional[int] = None
    plan: Optional[str] = None


@router.patch("/")
async def update_settings(
    body: UpdateSettingsRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    if body.dailyGoal is not None:
        await db.execute(
            "UPDATE users SET daily_goal=$1 WHERE id=$2",
            body.dailyGoal, user["id"],
        )
    if body.plan in ("free", "pro", "team"):
        await db.execute(
            "UPDATE users SET plan=$1 WHERE id=$2",
            body.plan, user["id"],
        )
    return {"success": True}
