"""Feature entitlements and AI quota — the licensing authority.

This module, not the WordPress plugin and not the bot handlers, is the only
place that decides whether a tenant may use a feature or has AI quota left.
Callers (bot command handlers, article worker, future web/API routes) must
call `require_feature` / `require_ai_quota` and handle the structured
exceptions below; they must never infer entitlement from anything the client
sent.

Deliberately absent: any `if plan_key == "pro"` branch. `plan_key` is a
display label only (see the License model). All decisions read
`features_json` and the two limit columns, so introducing, renaming, or
repricing a plan never touches this file — only the row's values change.
"""
from __future__ import annotations

import datetime
import json

from database.db import SessionLocal
from database.models import AiUsage, License


# A tenant with no license row yet (e.g. mid-pairing, before any plan is
# assigned) gets these defaults — enough to try the product, nothing paid.
DEFAULT_PLAN_KEY = "trial"
DEFAULT_FEATURES = {"bot": True, "telegram": True, "bale": True, "ai": True, "woocommerce": True, "automation": False}
DEFAULT_AI_DAILY_LIMIT = 2
DEFAULT_AI_MONTHLY_LIMIT = None  # no separate monthly ceiling for the trial


class FeatureNotAvailable(Exception):
    """Raised when a tenant's license does not include the requested feature."""

    def __init__(self, feature: str):
        self.feature = feature
        super().__init__(f"feature not available: {feature}")


class QuotaExceeded(Exception):
    """Raised when a tenant has used all AI quota for the current window.

    Carries enough structured detail for a bot/plugin to present a clean,
    specific message (see spec's UX-states requirement) without the caller
    needing to re-derive it.
    """

    def __init__(self, window: str, used: int, limit: int):
        self.window = window  # "daily" | "monthly"
        self.used = used
        self.limit = limit
        super().__init__(f"{window} AI quota exceeded: {used}/{limit}")


def _license_defaults(tenant_id: int) -> License:
    return License(
        tenant_id=tenant_id,
        plan_key=DEFAULT_PLAN_KEY,
        status="active",
        features_json=json.dumps(DEFAULT_FEATURES),
        ai_daily_limit=DEFAULT_AI_DAILY_LIMIT,
        ai_monthly_limit=DEFAULT_AI_MONTHLY_LIMIT,
    )


def get_or_create_license(tenant_id: int) -> dict:
    """Returns this tenant's license as a plain dict, creating a trial-default
    row on first use so every other function here can assume one exists."""

    with SessionLocal() as session:
        license_row = session.query(License).filter_by(tenant_id=tenant_id).first()
        if not license_row:
            license_row = _license_defaults(tenant_id)
            session.add(license_row)
            session.commit()
            session.refresh(license_row)
        return _license_to_dict(license_row)


def _license_to_dict(license_row: License) -> dict:
    try:
        features = json.loads(license_row.features_json or "{}")
    except (TypeError, ValueError):
        features = {}
    return {
        "tenant_id": license_row.tenant_id,
        "plan_key": license_row.plan_key,
        "status": license_row.status,
        "features": features,
        "ai_daily_limit": license_row.ai_daily_limit,
        "ai_monthly_limit": license_row.ai_monthly_limit,
    }


def feature_enabled(tenant_id: int, feature: str) -> bool:
    license_dict = get_or_create_license(tenant_id)
    if license_dict["status"] != "active":
        return False
    return bool(license_dict["features"].get(feature, False))


def require_feature(tenant_id: int, feature: str) -> None:
    if not feature_enabled(tenant_id, feature):
        raise FeatureNotAvailable(feature)


def _usage_since(session, tenant_id: int, since: datetime.datetime) -> int:
    rows = (
        session.query(AiUsage)
        .filter(AiUsage.tenant_id == tenant_id, AiUsage.occurred_at >= since)
        .all()
    )
    return sum(row.credits for row in rows)


def ai_quota_status(tenant_id: int, *, now: datetime.datetime | None = None) -> dict:
    """Returns current usage/limit for both windows without consuming credit.
    A None limit means that window is not enforced for this tenant."""

    now = now or datetime.datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)

    license_dict = get_or_create_license(tenant_id)
    with SessionLocal() as session:
        used_today = _usage_since(session, tenant_id, day_start)
        used_month = _usage_since(session, tenant_id, month_start)

    return {
        "daily_used": used_today,
        "daily_limit": license_dict["ai_daily_limit"],
        "monthly_used": used_month,
        "monthly_limit": license_dict["ai_monthly_limit"],
    }


def require_ai_quota(tenant_id: int, credits: int = 1) -> None:
    """Raises FeatureNotAvailable / QuotaExceeded, or returns None if the
    tenant may spend `credits` more AI credit right now. Does not itself
    record usage — call record_ai_usage only after the operation succeeds,
    so a failed generation never consumes the tenant's quota."""

    require_feature(tenant_id, "ai")
    status = ai_quota_status(tenant_id)

    if status["daily_limit"] is not None and status["daily_used"] + credits > status["daily_limit"]:
        raise QuotaExceeded("daily", status["daily_used"], status["daily_limit"])
    if status["monthly_limit"] is not None and status["monthly_used"] + credits > status["monthly_limit"]:
        raise QuotaExceeded("monthly", status["monthly_used"], status["monthly_limit"])


def record_ai_usage(tenant_id: int, operation: str, credits: int = 1) -> None:
    with SessionLocal() as session:
        session.add(AiUsage(tenant_id=tenant_id, operation=operation, credits=credits))
        session.commit()
