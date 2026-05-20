"""
Billing routes — Stripe integration
POST /billing/create-checkout  — create Stripe Checkout session
POST /billing/portal           — create Stripe Customer Portal session
POST /billing/webhook          — Stripe webhook handler
GET  /billing/status           — current subscription status
"""

import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
import asyncpg

from database import get_db
from auth_utils import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY    = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET       = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PRO_PRICE_ID         = os.getenv("STRIPE_PRO_PRICE_ID", "")
TEAM_PRICE_ID        = os.getenv("STRIPE_TEAM_PRICE_ID", "")
FRONTEND_URL         = os.getenv("FRONTEND_URL", "http://localhost:3000")


def _stripe():
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "Billing is not configured yet.")
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


class CheckoutRequest(BaseModel):
    plan: str  # "pro" | "team"


@router.post("/create-checkout")
async def create_checkout(
    body: CheckoutRequest,
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    if body.plan not in ("pro", "team"):
        raise HTTPException(400, "Invalid plan")

    stripe = _stripe()
    price_id = PRO_PRICE_ID if body.plan == "pro" else TEAM_PRICE_ID
    if not price_id:
        raise HTTPException(503, "Plan price not configured.")

    # Get or create Stripe customer
    customer_id = user["stripe_customer_id"]
    if not customer_id:
        customer = stripe.Customer.create(email=user["email"], name=user["name"])
        customer_id = customer.id
        await db.execute("UPDATE users SET stripe_customer_id=$1 WHERE id=$2", customer_id, user["id"])

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{FRONTEND_URL}/billing?success=1",
        cancel_url=f"{FRONTEND_URL}/billing",
        metadata={"user_id": str(user["id"]), "plan": body.plan},
    )
    return {"url": session.url}


@router.post("/portal")
async def customer_portal(
    user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    stripe = _stripe()
    if not user["stripe_customer_id"]:
        raise HTTPException(400, "No billing account found. Please subscribe first.")

    session = stripe.billing_portal.Session.create(
        customer=user["stripe_customer_id"],
        return_url=f"{FRONTEND_URL}/billing",
    )
    return {"url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: asyncpg.Connection = Depends(get_db)):
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    body = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(body, sig, WEBHOOK_SECRET)
    except Exception as e:
        logger.warning(f"Stripe webhook signature failed: {e}")
        raise HTTPException(400, "Invalid webhook signature")

    etype = event["type"]
    data  = event["data"]["object"]

    if etype == "checkout.session.completed":
        user_id = int(data.get("metadata", {}).get("user_id", 0))
        plan    = data.get("metadata", {}).get("plan", "pro")
        sub_id  = data.get("subscription")
        if user_id and sub_id:
            await db.execute(
                """UPDATE users
                   SET plan=$1, stripe_subscription_id=$2, subscription_status='active'
                   WHERE id=$3""",
                plan, sub_id, user_id,
            )
            logger.info(f"User {user_id} upgraded to {plan}")

    elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub_id = data["id"]
        status = data["status"]
        if status in ("canceled", "incomplete_expired", "unpaid"):
            await db.execute(
                "UPDATE users SET plan='free', subscription_status=$1 WHERE stripe_subscription_id=$2",
                status, sub_id,
            )
            logger.info(f"Subscription {sub_id} downgraded: {status}")
        else:
            await db.execute(
                "UPDATE users SET subscription_status=$1 WHERE stripe_subscription_id=$2",
                status, sub_id,
            )

    return {"received": True}


@router.get("/status")
async def billing_status(user=Depends(get_current_user)):
    return {
        "plan": user["plan"],
        "subscription_status": user.get("subscription_status", "active"),
        "stripe_subscription_id": user.get("stripe_subscription_id"),
    }
