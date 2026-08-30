"""
Shared fixtures. Every test that touches the database gets a fresh
sqlite file (so tests never depend on or pollute your real
authomatical.db), and Redis is mocked everywhere so the test suite
never needs a real Redis connection.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config


@pytest.fixture
def test_db(tmp_path):
    """Point the app at a throwaway sqlite file for this test only."""
    db_path = tmp_path / "test.sqlite3"
    Config.DATABASE_URL = f"sqlite:///{db_path}"
    Config.SECRET_KEY = "y9E37_5hODeqz5ZBzlpWHE0U7gsk1gnqh7kwIxIAySg="  # test-only Fernet key

    import database.db as dbmod
    dbmod.reset_for_tests(Config.DATABASE_URL)

    import database.repository as repo
    yield repo


@pytest.fixture
def mocked_redis_broker():
    with patch("messaging.redis_broker.RedisBroker") as MockBroker:
        MockBroker.return_value.redis = MagicMock()
        MockBroker.return_value.publish.return_value = "fake-job-id"
        yield MockBroker
