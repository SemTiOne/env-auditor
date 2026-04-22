import os

STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]


def verify_webhook(payload, signature):
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise ValueError("Missing STRIPE_WEBHOOK_SECRET")
    return True
