"""
Run this ONCE to create Stripe products + prices and update your .env automatically.
Usage: python stripe_setup.py
"""
import stripe
import os
import re
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env"


def load_env() -> dict:
    env = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def update_env(key: str, value: str):
    content = ENV_FILE.read_text()
    if re.search(rf"^{key}=", content, re.MULTILINE):
        content = re.sub(rf"^{key}=.*$", f"{key}={value}", content, flags=re.MULTILINE)
    else:
        content += f"\n{key}={value}"
    ENV_FILE.write_text(content)
    print(f"  OK {key}={value}")


def main():
    env = load_env()
    secret_key = env.get("STRIPE_SECRET_KEY", "")

    if not secret_key or secret_key.startswith("sk_live_...") or not secret_key.startswith("sk_"):
        print("ERROR: STRIPE_SECRET_KEY is not set in .env")
        print("  Get it from: https://dashboard.stripe.com/apikeys")
        return

    stripe.api_key = secret_key
    mode = "LIVE" if secret_key.startswith("sk_live_") else "TEST"
    print(f"\n{'='*50}")
    print(f"  SalesAI Pro — Stripe Setup ({mode} MODE)")
    print(f"{'='*50}\n")

    plans = [
        {"key": "STRIPE_PRICE_STARTER", "name": "SalesAI Pro — Starter",  "amount": 4900,  "nickname": "starter"},
        {"key": "STRIPE_PRICE_PRO",     "name": "SalesAI Pro — Pro",      "amount": 9900,  "nickname": "pro"},
        {"key": "STRIPE_PRICE_AGENCY",  "name": "SalesAI Pro — Agency",   "amount": 19900, "nickname": "agency"},
    ]

    print("Creating Stripe products and prices...\n")
    for plan in plans:
        current = env.get(plan["key"], "")
        # Skip if already a real price ID
        if current.startswith("price_"):
            print(f"  OK {plan['key']} already set: {current}")
            continue

        try:
            # Check if product already exists
            products = stripe.Product.list(limit=100)
            existing = next((p for p in products.data if p.name == plan["name"]), None)

            if existing:
                product = existing
                print(f"  -> Product already exists: {plan['name']}")
            else:
                product = stripe.Product.create(
                    name=plan["name"],
                    description=f"SalesAI Pro {plan['nickname'].title()} subscription",
                    metadata={"plan": plan["nickname"]},
                )
                print(f"  -> Created product: {plan['name']} ({product.id})")

            # Create price
            price = stripe.Price.create(
                product=product.id,
                unit_amount=plan["amount"],
                currency="usd",
                recurring={"interval": "month"},
                nickname=plan["nickname"],
                metadata={"plan": plan["nickname"]},
            )
            print(f"  -> Created price: ${plan['amount']//100}/mo ({price.id})")
            update_env(plan["key"], price.id)

        except stripe.error.AuthenticationError:
            print(f"\nERROR: Invalid Stripe API key. Check STRIPE_SECRET_KEY in .env")
            return
        except Exception as e:
            print(f"\nERROR creating {plan['name']}: {e}")
            return

    print(f"\n{'='*50}")
    print("  Setup complete! Your .env has been updated.")
    print("  Restart start.bat to apply the changes.")
    print(f"{'='*50}\n")

    # Verify
    print("Verifying prices...\n")
    env2 = load_env()
    for plan in plans:
        pid = env2.get(plan["key"], "")
        if pid.startswith("price_"):
            try:
                p = stripe.Price.retrieve(pid)
                print(f"  OK {plan['nickname'].upper()}: ${p.unit_amount//100}/mo — {pid}")
            except Exception as e:
                print(f"  FAIL {plan['key']}: {e}")
        else:
            print(f"  FAIL {plan['key']}: not set correctly ({pid})")

    print("\nNext step: Restart start.bat — subscriptions are live!\n")


if __name__ == "__main__":
    main()
