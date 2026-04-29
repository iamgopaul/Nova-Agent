from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _stripe():
    import stripe as _s
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured.")
    _s.api_key = key
    return _s


def create_customer(email: str, display_name: str) -> str:
    """Create a Stripe customer and return the customer ID."""
    s = _stripe()
    customer = s.Customer.create(email=email, name=display_name)
    return customer["id"]


def create_checkout_session(
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Return a Stripe Checkout session URL for the given price."""
    s = _stripe()
    session = s.checkout.Session.create(
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
    )
    return session["url"]


def create_portal_session(customer_id: str, return_url: str) -> str:
    """Return a Stripe Customer Portal URL for self-service billing management."""
    s = _stripe()
    session = s.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session["url"]


def construct_webhook_event(payload: bytes, sig_header: str) -> dict:
    s = _stripe()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured.")
    return s.Webhook.construct_event(payload, sig_header, secret)


def parse_subscription_event(event: dict) -> dict | None:
    """
    Extract subscription info from a Stripe webhook event.
    Returns a dict with {stripe_subscription_id, stripe_customer_id, status,
    plan_id, interval, current_period_end, cancel_at_period_end} or None.
    """
    relevant = {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }
    if event.get("type") not in relevant:
        return None

    sub = event["data"]["object"]
    item = (sub.get("items", {}).get("data") or [{}])[0]
    price = item.get("price", {})
    period_end = sub.get("current_period_end")

    return {
        "stripe_subscription_id": sub["id"],
        "stripe_customer_id": sub["customer"],
        "status": sub["status"],
        "stripe_price_id": price.get("id", ""),
        "interval": price.get("recurring", {}).get("interval", "month"),
        "current_period_end": datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None,
        "cancel_at_period_end": sub.get("cancel_at_period_end", False),
    }


def price_id_to_plan(price_id: str) -> str:
    """Map a Stripe Price ID to our internal plan ID (free/pro/teams)."""
    pro_ids = {
        os.environ.get("STRIPE_PRO_MONTHLY_PRICE_ID", ""),
        os.environ.get("STRIPE_PRO_YEARLY_PRICE_ID", ""),
    }
    teams_ids = {
        os.environ.get("STRIPE_TEAMS_MONTHLY_PRICE_ID", ""),
        os.environ.get("STRIPE_TEAMS_YEARLY_PRICE_ID", ""),
    }
    if price_id in pro_ids - {""}:
        return "pro"
    if price_id in teams_ids - {""}:
        return "teams"
    return "free"
