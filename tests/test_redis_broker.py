from unittest.mock import MagicMock

import pytest
import redis

from messaging.redis_broker import RedisBroker


def test_publish_encodes_regular_values_once_and_preserves_bytes():
    client = MagicMock()
    client.xadd.return_value = b"1-0"
    broker = RedisBroker(stream="articles", redis_client=client)

    assert broker.publish({"title": "متن", "already_bytes": b"raw", "count": 3}) == b"1-0"
    client.xadd.assert_called_once_with(
        "articles",
        {"title": "متن".encode(), "already_bytes": b"raw", "count": b"3"},
    )


def test_publish_raises_clear_error_when_redis_is_down():
    client = MagicMock()
    client.xadd.side_effect = redis.exceptions.ConnectionError("connection refused")
    broker = RedisBroker(redis_client=client)

    with pytest.raises(RuntimeError, match="Redis is unavailable"):
        broker.publish({"x": "y"})


def test_consume_decodes_fields_and_tolerates_existing_group():
    client = MagicMock()
    client.xgroup_create.side_effect = redis.exceptions.ResponseError("BUSYGROUP")
    client.xreadgroup.return_value = [
        (b"article_jobs", [(b"1-0", {b"keywords": "مقاله".encode(), b"chapters": b"5"})])
    ]
    broker = RedisBroker(stream="article_jobs", redis_client=client)

    messages = broker.consume("group", "consumer")

    assert messages == [(b"article_jobs", [(b"1-0", {"keywords": "مقاله", "chapters": "5"})])]


def test_consume_and_ack_do_not_kill_worker_on_redis_error():
    client = MagicMock()
    client.xgroup_create.side_effect = redis.exceptions.ConnectionError("down")
    broker = RedisBroker(redis_client=client)
    assert broker.consume("group", "consumer") == []

    client.xgroup_create.side_effect = None
    client.xack.side_effect = redis.exceptions.ConnectionError("down")
    assert broker.ack("group", "1-0") is False
