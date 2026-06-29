"""Stripe billing — checkout sessions, webhooks, customer portal."""
import logging
import stripe
from config import settings

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

PLANS = {
    "starter": {
        "name": "Starter",
        "price": 49,
        "price_id": settings.STRIPE_PRICE_STARTER,
        "leads": 100,
        "calls": 50,
        "features": [
            "100 leads", "50 AI calls/month", "SMS & email follow-ups",
            "1 campaign", "Lead finder (scraper)", "AI script generation",
        ],
    },
    "pro": {
        "name": "Pro",
        "price": 99,
        "price_id": settings.STRIPE_PRICE_PRO,
        "leads": 500,
        "calls": 250,
        "features": [
            "500 leads", "250 AI calls/month", "SMS & email follow-ups",
            "Unlimited campaigns", "Priority lead finder", "AI script generation",
            "Call recordings", "Lead scoring",
        ],
    },
    "agency": {
        "name": "Agency",
        "price": 199,
        "price_id": settings.STRIPE_PRICE_AGENCY,
        "leads": -1,
        "calls": -1,
        "features": [
            "Unlimited leads", "Unlimited AI calls", "SMS & email follow-ups",
            "Unlimited campaigns", "Bulk lead import", "AI script generation",
            "Call recordings & transcripts", "Advanced analytics",
            "Priority support",
        ],
    },
}


def create_checkout_session(user_id: int, email: str, plan: str, success_url: str, cancel_url: str) -> str:
    """Create a Stripe Checkout session and return the redirect URL."""
    plan_data = PLANS.get(plan)
    if not plan_data or not plan_data["price_id"]:
        raise ValueError(f"Invalid plan or Stripe price not configured: {plan}")

    session = stripe.checkout.Session.create(
        customer_email=email,
        payment_method_types=["card"],
        line_items=[{"price": plan_data["price_id"], "quantity": 1}],
        mode="subscription",
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"user_id": str(user_id), "plan": plan},
        subscription_data={
            "trial_period_days": settings.TRIAL_DAYS,
            "metadata": {"user_id": str(user_id), "plan": plan},
        },
    )
    return session.url


def create_portal_session(stripe_customer_id: str, return_url: str) -> str:
    """Create a Stripe Customer Portal session for self-serve plan management."""
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url,
    )
    return session.url


def handle_webhook(payload: bytes, signature: str = "") -> dict:
    """Parse and verify a Stripe webhook event."""
    from config import settings as _s
    webhook_secret = getattr(_s, "STRIPE_WEBHOOK_SECRET", "")
    if webhook_secret and signature:
        try:
            event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
            return event
        except stripe.error.SignatureVerificationError:
            raise ValueError("Invalid Stripe webhook signature")
    import json
    return json.loads(payload)


def get_subscription(subscription_id: str) -> dict:
    """Fetch a Stripe subscription by ID."""
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        return {"status": sub.status, "plan": sub.metadata.get("plan", "starter")}
    except Exception as e:
        logger.error(f"Failed to fetch subscription {subscription_id}: {e}")
        return {}
