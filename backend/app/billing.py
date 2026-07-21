import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app import models


ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}
SUPPORTED_PLANS = {"student_pro", "professional"}


class BillingError(RuntimeError):
    pass


def _stripe():
    try:
        import stripe
    except ImportError as error:
        raise BillingError("Stripe support is not installed") from error

    secret = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not secret:
        raise BillingError("Stripe billing is not configured")
    stripe.api_key = secret
    return stripe


def _price_ids() -> dict[str, str]:
    return {
        "student_pro": (os.getenv("STRIPE_PRICE_STUDENT_PRO") or "").strip(),
        "professional": (
            os.getenv("STRIPE_PRICE_PROFESSIONAL") or ""
        ).strip(),
    }


def _allowed_plan(user: models.User) -> str:
    return "professional" if user.account_type == "professional" else "student_pro"


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    return dict(value or {})


def _unix_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _subscription_for_user(db: Session, user_id: int) -> models.Subscription:
    subscription = db.query(models.Subscription).filter_by(user_id=user_id).first()
    if subscription is None:
        subscription = models.Subscription(user_id=user_id)
        db.add(subscription)
        db.flush()
    return subscription


def create_checkout_url(db: Session, user: models.User, plan: str) -> str:
    if plan not in SUPPORTED_PLANS or plan != _allowed_plan(user):
        raise BillingError("That subscription is not available for this account mode")

    price_id = _price_ids().get(plan, "")
    if not price_id:
        raise BillingError(f"The {plan} Stripe price is not configured")

    subscription = _subscription_for_user(db, user.id)
    if subscription.status in ACTIVE_SUBSCRIPTION_STATUSES:
        raise BillingError("This account already has an active subscription")

    frontend_url = (os.getenv("FRONTEND_URL") or "http://localhost:5173").rstrip("/")
    stripe = _stripe()
    parameters = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{frontend_url}/?billing=success",
        "cancel_url": f"{frontend_url}/?billing=cancelled",
        "client_reference_id": str(user.id),
        "metadata": {"user_id": str(user.id), "plan": plan},
        "subscription_data": {
            "metadata": {"user_id": str(user.id), "plan": plan},
        },
        "allow_promotion_codes": True,
    }
    if subscription.external_customer_id:
        parameters["customer"] = subscription.external_customer_id
    else:
        parameters["customer_email"] = user.email

    session = stripe.checkout.Session.create(**parameters)
    checkout_url = getattr(session, "url", None) or _as_dict(session).get("url")
    if not checkout_url:
        raise BillingError("Stripe did not return a checkout URL")
    return checkout_url


def create_portal_url(db: Session, user: models.User) -> str:
    subscription = db.query(models.Subscription).filter_by(user_id=user.id).first()
    if subscription is None or not subscription.external_customer_id:
        raise BillingError("No Stripe customer exists for this account")

    frontend_url = (os.getenv("FRONTEND_URL") or "http://localhost:5173").rstrip("/")
    session = _stripe().billing_portal.Session.create(
        customer=subscription.external_customer_id,
        return_url=frontend_url,
    )
    portal_url = getattr(session, "url", None) or _as_dict(session).get("url")
    if not portal_url:
        raise BillingError("Stripe did not return a billing portal URL")
    return portal_url


def subscription_payload(db: Session, user: models.User) -> dict:
    subscription = db.query(models.Subscription).filter_by(user_id=user.id).first()
    if subscription is None:
        return {
            "plan": "free",
            "status": "inactive",
            "cancel_at_period_end": False,
            "current_period_end": None,
            "can_manage": False,
        }
    return {
        "plan": user.subscription_plan or "free",
        "status": subscription.status,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "current_period_end": subscription.current_period_end,
        "can_manage": bool(subscription.external_customer_id),
    }


def _plan_for_price(price_id: str | None, metadata: dict) -> str | None:
    metadata_plan = str(metadata.get("plan") or "")
    if metadata_plan in SUPPORTED_PLANS:
        return metadata_plan
    for plan, configured_price in _price_ids().items():
        if price_id and configured_price and price_id == configured_price:
            return plan
    return None


def _find_subscription_owner(db: Session, payload: dict) -> tuple[models.User | None, models.Subscription | None]:
    external_subscription_id = str(payload.get("id") or "")
    external_customer_id = str(payload.get("customer") or "")
    metadata = _as_dict(payload.get("metadata"))
    raw_user_id = metadata.get("user_id")
    user = None
    if str(raw_user_id or "").isdigit():
        user = db.get(models.User, int(raw_user_id))

    subscription = None
    if external_subscription_id:
        subscription = db.query(models.Subscription).filter_by(
            external_subscription_id=external_subscription_id
        ).first()
    if subscription is None and external_customer_id:
        subscription = db.query(models.Subscription).filter_by(
            external_customer_id=external_customer_id
        ).first()
    if user is None and subscription is not None:
        user = db.get(models.User, subscription.user_id)
    if user is not None and subscription is None:
        subscription = _subscription_for_user(db, user.id)
    return user, subscription


def _apply_subscription_event(
    db: Session,
    payload: dict,
    *,
    event_created: int,
    deleted: bool = False,
) -> None:
    user, subscription = _find_subscription_owner(db, payload)
    if user is None or subscription is None:
        return
    if (
        subscription.last_event_created is not None
        and event_created < subscription.last_event_created
    ):
        return

    items = _as_dict(payload.get("items")).get("data") or []
    first_item = _as_dict(items[0]) if items else {}
    price = _as_dict(first_item.get("price"))
    price_id = str(price.get("id") or "") or None
    plan = _plan_for_price(price_id, _as_dict(payload.get("metadata")))
    status = "canceled" if deleted else str(payload.get("status") or "inactive")

    subscription.external_customer_id = str(payload.get("customer") or "") or None
    subscription.external_subscription_id = str(payload.get("id") or "") or None
    subscription.price_id = price_id
    subscription.status = status
    subscription.cancel_at_period_end = bool(payload.get("cancel_at_period_end"))
    subscription.current_period_end = _unix_datetime(
        payload.get("current_period_end") or first_item.get("current_period_end")
    )
    subscription.last_event_created = event_created
    if plan:
        subscription.plan = plan
    user.subscription_plan = (
        subscription.plan
        if subscription.plan in SUPPORTED_PLANS
        and status in ACTIVE_SUBSCRIPTION_STATUSES
        else "free"
    )


def process_webhook(db: Session, payload: bytes, signature: str) -> None:
    webhook_secret = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not webhook_secret:
        raise BillingError("Stripe webhook verification is not configured")
    stripe = _stripe()
    try:
        event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as error:
        raise BillingError("Invalid Stripe webhook signature") from error

    event_data = _as_dict(event)
    event_id = str(event_data.get("id") or "")
    event_type = str(event_data.get("type") or "")
    event_created = int(event_data.get("created") or 0)
    if not event_id or not event_type:
        raise BillingError("Invalid Stripe webhook event")
    if db.get(models.ProcessedWebhookEvent, event_id) is not None:
        return

    data_object = _as_dict(_as_dict(event_data.get("data")).get("object"))
    if event_type == "checkout.session.completed":
        metadata = _as_dict(data_object.get("metadata"))
        user_id = metadata.get("user_id") or data_object.get("client_reference_id")
        if str(user_id or "").isdigit():
            user = db.get(models.User, int(user_id))
            if user is not None:
                subscription = _subscription_for_user(db, user.id)
                subscription.external_customer_id = (
                    str(data_object.get("customer") or "") or None
                )
                subscription.external_subscription_id = (
                    str(data_object.get("subscription") or "") or None
                )
                subscription.plan = _plan_for_price(None, metadata) or "free"
                if subscription.status not in ACTIVE_SUBSCRIPTION_STATUSES:
                    subscription.status = "pending"
    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        _apply_subscription_event(
            db,
            data_object,
            event_created=event_created,
            deleted=event_type == "customer.subscription.deleted",
        )
    elif event_type == "invoice.payment_failed":
        external_subscription_id = str(data_object.get("subscription") or "")
        subscription = db.query(models.Subscription).filter_by(
            external_subscription_id=external_subscription_id
        ).first()
        if subscription is not None:
            if (
                subscription.last_event_created is None
                or event_created >= subscription.last_event_created
            ):
                subscription.status = "past_due"
                subscription.last_event_created = event_created
                user = db.get(models.User, subscription.user_id)
                if user is not None:
                    user.subscription_plan = "free"

    db.add(
        models.ProcessedWebhookEvent(
            id=event_id,
            event_type=event_type,
        )
    )
    db.commit()
