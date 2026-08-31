"""Redis Streams wrapper used by the bot and article worker."""
import logging

import redis

from config import Config
from utils.helpers import log

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _as_text(value) -> str:
    """Normalize Redis bytes at the broker boundary.

    A Redis stream ID is still only a transport identifier, but decoding it
    here prevents accidental keys such as ``article_temp:b'123-0'`` in any
    caller that logs or temporarily associates it with another value.
    """

    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)


class RedisBroker:
    def __init__(self, stream="jobs", redis_client=None):
        # Creating a redis-py client does not connect immediately.  A useful
        # local default makes imports/test discovery safe while real command
        # failures are handled in publish/consume/ack below.
        self.redis = redis_client or redis.Redis.from_url(Config.REDIS_URL or DEFAULT_REDIS_URL)
        self.stream = stream

    def publish(self, data: dict):
        """Send one message to a Redis Stream.

        Redis itself stores bytes.  Preserve byte values passed by legacy
        callers instead of turning ``b'value'`` into the literal text
        ``b'value'``; all normal Python values are encoded once.
        """
        data_bytes = {
            str(key): value if isinstance(value, bytes) else str(value).encode()
            for key, value in data.items()
        }
        try:
            return _as_text(self.redis.xadd(self.stream, data_bytes))
        except redis.exceptions.RedisError as exc:
            log(f"[Redis publish error] {exc}")
            raise RuntimeError(f"Redis is unavailable: {exc}") from exc

    def consume(self, group, consumer, block=5000, count=1):
        """Read messages for a consumer group, returning decoded fields.

        An outage is transient and should not kill a worker process.  Return
        an empty batch so the outer loop can wait and try again; publishing
        still raises because the caller needs to tell the user their job was
        not queued.
        """
        try:
            self.redis.xgroup_create(self.stream, group, id="0", mkstream=True)
        except redis.exceptions.ResponseError:
            # BUSYGROUP means the group already exists, which is expected.
            pass
        except redis.exceptions.RedisError as exc:
            log(f"[Redis consumer-group error] {exc}")
            return []

        try:
            messages = self.redis.xreadgroup(
                group,
                consumer,
                {self.stream: ">"},
                count=count,
                block=block,
            )
            converted = []
            for stream_name, msgs in messages:
                converted_fields = []
                for msg_id, fields in msgs:
                    readable_fields = {
                        _as_text(key): _as_text(value)
                        for key, value in fields.items()
                    }
                    converted_fields.append((_as_text(msg_id), readable_fields))
                converted.append((_as_text(stream_name), converted_fields))
            return converted
        except redis.exceptions.RedisError as exc:
            log(f"[Redis consume error] {exc}")
            return []

    def ack(self, group, msg_id) -> bool:
        try:
            self.redis.xack(self.stream, group, msg_id)
            return True
        except redis.exceptions.RedisError as exc:
            log(f"[Redis ack error] {exc}")
            return False
