"""Licensing/entitlement/quota tests.

These use the same `test_db` fixture as the rest of the suite (fresh sqlite
file per test) but exercise database.licensing directly, since it — not
plan-name string comparisons anywhere else — is the sole authority for
feature access and AI quota.
"""
import datetime

import pytest

from database import licensing


@pytest.fixture
def tenant_id(test_db):
    return test_db.get_or_create_tenant("telegram", "500")


def test_new_tenant_gets_trial_defaults_without_a_prior_license_row(test_db, tenant_id):
    license_dict = licensing.get_or_create_license(tenant_id)

    assert license_dict["plan_key"] == "trial"
    assert license_dict["status"] == "active"
    assert license_dict["ai_daily_limit"] == licensing.DEFAULT_AI_DAILY_LIMIT
    assert license_dict["features"]["ai"] is True


def test_get_or_create_license_does_not_duplicate_the_row(test_db, tenant_id):
    first = licensing.get_or_create_license(tenant_id)
    second = licensing.get_or_create_license(tenant_id)

    assert first["tenant_id"] == second["tenant_id"] == tenant_id


def test_feature_enabled_reads_the_features_json_not_a_plan_name(test_db, tenant_id):
    from database.db import SessionLocal
    from database.models import License
    import json

    licensing.get_or_create_license(tenant_id)
    with SessionLocal() as session:
        row = session.query(License).filter_by(tenant_id=tenant_id).first()
        row.plan_key = "some-future-plan-name-never-seen-before"
        row.features_json = json.dumps({"ai": False, "automation": True})
        session.commit()

    assert licensing.feature_enabled(tenant_id, "ai") is False
    assert licensing.feature_enabled(tenant_id, "automation") is True


def test_suspended_license_disables_every_feature_regardless_of_flags(test_db, tenant_id):
    from database.db import SessionLocal
    from database.models import License

    licensing.get_or_create_license(tenant_id)
    with SessionLocal() as session:
        row = session.query(License).filter_by(tenant_id=tenant_id).first()
        row.status = "suspended"
        session.commit()

    assert licensing.feature_enabled(tenant_id, "ai") is False


def test_require_feature_raises_for_a_disabled_feature(test_db, tenant_id):
    with pytest.raises(licensing.FeatureNotAvailable):
        licensing.require_feature(tenant_id, "automation")  # default False


def test_ai_quota_allows_up_to_the_daily_limit_then_raises(test_db, tenant_id):
    limit = licensing.get_or_create_license(tenant_id)["ai_daily_limit"]

    for _ in range(limit):
        licensing.require_ai_quota(tenant_id)
        licensing.record_ai_usage(tenant_id, operation="article.generate")

    with pytest.raises(licensing.QuotaExceeded) as excinfo:
        licensing.require_ai_quota(tenant_id)
    assert excinfo.value.window == "daily"
    assert excinfo.value.used == limit
    assert excinfo.value.limit == limit


def test_failed_operation_never_consumes_quota_because_caller_records_after_success(test_db, tenant_id):
    """require_ai_quota only checks; record_ai_usage only records. A caller
    that checks, fails to generate, and never calls record_ai_usage must see
    quota unchanged — this is exactly why the two are separate functions."""

    status_before = licensing.ai_quota_status(tenant_id)
    licensing.require_ai_quota(tenant_id)  # simulate a check before a failed generation
    status_after = licensing.ai_quota_status(tenant_id)

    assert status_before == status_after


def test_multi_credit_operation_is_rejected_if_it_would_exceed_the_remaining_daily_quota(test_db, tenant_id):
    from database.db import SessionLocal
    from database.models import License

    licensing.get_or_create_license(tenant_id)
    with SessionLocal() as session:
        row = session.query(License).filter_by(tenant_id=tenant_id).first()
        row.ai_daily_limit = 3
        session.commit()

    licensing.record_ai_usage(tenant_id, operation="article.generate", credits=2)

    with pytest.raises(licensing.QuotaExceeded):
        licensing.require_ai_quota(tenant_id, credits=2)  # 2 used + 2 requested > 3


def test_monthly_limit_is_enforced_independently_of_daily_limit(test_db, tenant_id):
    from database.db import SessionLocal
    from database.models import License

    licensing.get_or_create_license(tenant_id)
    with SessionLocal() as session:
        row = session.query(License).filter_by(tenant_id=tenant_id).first()
        row.ai_daily_limit = 100  # effectively unlimited for this test
        row.ai_monthly_limit = 1
        session.commit()

    licensing.require_ai_quota(tenant_id)
    licensing.record_ai_usage(tenant_id, operation="article.generate")

    with pytest.raises(licensing.QuotaExceeded) as excinfo:
        licensing.require_ai_quota(tenant_id)
    assert excinfo.value.window == "monthly"


def test_usage_outside_the_current_day_does_not_count_toward_todays_quota(test_db, tenant_id):
    from database.db import SessionLocal
    from database.models import AiUsage, License

    licensing.get_or_create_license(tenant_id)
    with SessionLocal() as session:
        row = session.query(License).filter_by(tenant_id=tenant_id).first()
        row.ai_daily_limit = 1
        session.commit()
        session.add(AiUsage(
            tenant_id=tenant_id,
            operation="article.generate",
            credits=1,
            occurred_at=datetime.datetime.utcnow() - datetime.timedelta(days=2),
        ))
        session.commit()

    # Yesterday's usage must not block today's quota.
    licensing.require_ai_quota(tenant_id)


def test_two_tenants_have_independent_licenses_and_usage(test_db, tenant_id):
    other_tenant_id = test_db.get_or_create_tenant("bale", "501")

    licensing.record_ai_usage(tenant_id, operation="article.generate")

    assert licensing.ai_quota_status(tenant_id)["daily_used"] == 1
    assert licensing.ai_quota_status(other_tenant_id)["daily_used"] == 0
