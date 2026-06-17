"""Stripe billing endpoints — plans, checkout, webhooks, customer portal."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import User
from core.auth import get_current_user
from core.billing import PLANS, create_checkout_session, create_portal_session, handle_webhook
from config import settings

router = APIRouter(prefix="/billing", tags=["billing"])
logger = logging.getLogger(__name__)


class CheckoutRequest(BaseModel):
    plan: str


@router.get("/plans")
def get_plans():
    """Return all available subscription plans (public endpoint)."""
    return {
        k: {
            "name": v["name"],
            "price": v["price"],
            "leads": v["leads"],
            "calls": v["calls"],
            "features": v["features"],
        }
        for k, v in PLANS.items()
    }


@router.post("/checkout")
def create_checkout(
    data: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout session and return the redirect URL."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(503, "Stripe not configured. Add STRIPE_SECRET_KEY to .env")

    try:
        url = create_checkout_session(
            user_id=current_user.id,
            email=current_user.email,
            plan=data.plan,
            success_url=f"{settings.BASE_URL}/billing/success",
            cancel_url=f"{settings.BASE_URL}/pricing",
        )
        return {"checkout_url": url}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Checkout failed: {e}")
        raise HTTPException(500, "Failed to create checkout session")


@router.get("/portal")
def customer_portal(
    current_user: User = Depends(get_current_user),
):
    """Redirect to Stripe Customer Portal for plan management / cancellation."""
    if not current_user.stripe_customer_id:
        raise HTTPException(400, "No active subscription found. Please subscribe first.")
    try:
        url = create_portal_session(
            stripe_customer_id=current_user.stripe_customer_id,
            return_url=f"{settings.BASE_URL}/dashboard",
        )
        return {"portal_url": url}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhook events — update subscription status in DB."""
    payload = await request.body()

    try:
        event = handle_webhook(payload)
    except Exception as e:
        raise HTTPException(400, str(e))

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(obj, db)

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        _handle_subscription_update(obj, db)

    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(obj, db)

    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(obj, db)

    return Response(status_code=200)


# ── Webhook handlers ──────────────────────────────────────────────────────────

def _handle_checkout_completed(session: dict, db: Session):
    user_id = session.get("metadata", {}).get("user_id")
    plan = session.get("metadata", {}).get("plan", "starter")
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")

    if not user_id:
        return

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user:
        user.stripe_customer_id = customer_id
        user.stripe_subscription_id = subscription_id
        user.plan = plan
        user.status = "active"
        db.commit()
        logger.info(f"User {user_id} subscribed to {plan}")


def _handle_subscription_update(sub: dict, db: Session):
    subscription_id = sub.get("id")
    status = sub.get("status")
    plan = sub.get("metadata", {}).get("plan", "starter")
    customer_id = sub.get("customer")

    user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
    if not user and customer_id:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if user:
        user.status = "active" if status in ("active", "trialing") else status
        user.plan = plan
        db.commit()


def _handle_subscription_deleted(sub: dict, db: Session):
    subscription_id = sub.get("id")
    user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
    if user:
        user.status = "cancelled"
        db.commit()
        logger.info(f"Subscription cancelled for user {user.id}")


def _handle_payment_failed(invoice: dict, db: Session):
    customer_id = invoice.get("customer")
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if user:
        user.status = "past_due"
        db.commit()
        logger.warning(f"Payment failed for user {user.id}")
