"""
Plan guard — FastAPI dependencies that enforce per-plan usage limits.
Inject via `user=Depends(require_plan("feature"))` in route handlers.
"""

from fastapi import Depends, HTTPException
from auth_utils import get_current_user

LIMITS = {
    "free": {"interviews": 3,   "cover_letters": 5,   "jd_matches": 5},
    "pro":  {"interviews": 9999, "cover_letters": 9999, "jd_matches": 9999},
    "team": {"interviews": 9999, "cover_letters": 9999, "jd_matches": 9999},
}

MESSAGES = {
    "interviews":    "Free plan allows 3 mock interviews per month.",
    "cover_letters": "Free plan allows 5 cover letters per month.",
    "jd_matches":    "Free plan allows 5 JD matches per month.",
}


def require_plan(feature: str):
    """Returns a dependency that raises 403 when the user exceeds their plan limit."""

    async def _guard(user=Depends(get_current_user)):
        plan = user["plan"] or "free"
        limits = LIMITS.get(plan, LIMITS["free"])

        if feature == "interviews":
            if (user["interviews_this_month"] or 0) >= limits["interviews"]:
                raise HTTPException(403, f"{MESSAGES['interviews']} Upgrade to Pro for unlimited access.")

        elif feature == "cover_letters":
            if (user["cover_letters_generated"] or 0) >= limits["cover_letters"]:
                raise HTTPException(403, f"{MESSAGES['cover_letters']} Upgrade to Pro.")

        elif feature == "jd_matches":
            if (user["jd_matches_run"] or 0) >= limits["jd_matches"]:
                raise HTTPException(403, f"{MESSAGES['jd_matches']} Upgrade to Pro.")

        return user

    return _guard
