from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from gaaia.memory.store import MemoryStore
from gaaia.server.dependencies import get_current_user, get_memory
from gaaia.memory.models import User
from gaaia.services import stripe_service

router = APIRouter()

_APP_URL = os.environ.get("APP_URL", "http://localhost:3000")


@router.get("/plans")
def list_plans(memory: MemoryStore = Depends(get_memory)) -> list[dict]:
    plans = memory.list_plans()
    return [
        {
            "id": p.id,
            "name": p.name,
            "price_monthly_cents": p.price_monthly_cents,
            "price_yearly_cents": p.price_yearly_cents,
            "max_seats": p.max_seats,
            "features": p.features or [],
        }
        for p in plans
    ]


@router.get("/subscription")
def get_subscription(
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    sub = memory.get_active_subscription(current_user.id)
    return {
        "tier": current_user.subscription_tier,
        "status": sub.status if sub else "free",
        "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
        "stripe_customer_id": current_user.stripe_customer_id,
    }


class CheckoutBody(BaseModel):
    price_id: str
    interval: str = "month"


@router.post("/checkout")
def create_checkout(
    body: CheckoutBody,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    """Create a Stripe Checkout session and return the redirect URL."""
    if not os.environ.get("STRIPE_SECRET_KEY"):
        raise HTTPException(status_code=503, detail="Billing is not configured.")

    # Ensure the user has a Stripe customer record
    customer_id = current_user.stripe_customer_id
    if not customer_id:
        customer_id = stripe_service.create_customer(
            current_user.email, current_user.display_name
        )
        memory.update_stripe_customer(current_user.id, customer_id)

    url = stripe_service.create_checkout_session(
        customer_id=customer_id,
        price_id=body.price_id,
        success_url=f"{_APP_URL}/billing?success=1",
        cancel_url=f"{_APP_URL}/billing?canceled=1",
    )
    return {"url": url}


@router.post("/portal")
def billing_portal(
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found.")
    url = stripe_service.create_portal_session(
        customer_id=current_user.stripe_customer_id,
        return_url=f"{_APP_URL}/billing",
    )
    return {"url": url}


@router.post("/webhook")
async def stripe_webhook(request: Request, memory: MemoryStore = Depends(get_memory)) -> dict:
    """Receive and process Stripe webhook events."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe_service.construct_webhook_event(payload, sig)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    info = stripe_service.parse_subscription_event(event)
    if not info:
        return {"received": True}

    # Find the user by Stripe customer ID
    from sqlalchemy import select
    from gaaia.memory.models import User as UserModel

    user_id: str | None = None
    with memory._auth_sess() as db:
        u = db.scalar(
            select(UserModel).where(UserModel.stripe_customer_id == info["stripe_customer_id"])
        )
        user_id = u.id if u else None

    if not user_id:
        return {"received": True}

    plan_id = stripe_service.price_id_to_plan(info["stripe_price_id"])

    if info["status"] in ("canceled", "unpaid"):
        memory.cancel_subscription(user_id)
    else:
        memory.upsert_subscription(
            user_id=user_id,
            plan_id=plan_id,
            stripe_subscription_id=info["stripe_subscription_id"],
            status=info["status"],
            interval=info["interval"],
            current_period_end=info["current_period_end"],
            cancel_at_period_end=info["cancel_at_period_end"],
        )

    return {"received": True}
