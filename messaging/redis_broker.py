import redis
from config import Config
from utils.helpers import log

class RedisBroker:
    def __init__(self, stream="jobs"):
        self.redis = redis.Redis.from_url(Config.REDIS_URL)
        self.stream = stream

    def publish(self, data: dict):
        """Send message to Redis Stream"""
        data_bytes = {k: str(v).encode() for k, v in data.items()}
        return self.redis.xadd(self.stream, data_bytes)

    def consume(self, group, consumer, block=5000, count=1):
        """Reading a message from a Redis Stream by converting bytes to str"""
        try:
            self.redis.xgroup_create(self.stream, group, id="0", mkstream=True)
        except redis.exceptions.ResponseError:
            pass
        try:
            messages = self.redis.xreadgroup(group, consumer, {self.stream: ">"}, count=count, block=block)
            # Convert bytes to str
            converted = []
            for stream_name, msgs in messages:
                converted_msgs = []
                for msg_id, fields in msgs:
                    converted_fields = {k.decode(): v.decode() for k, v in fields.items()}
                    converted_msgs.append((msg_id, converted_fields))
                converted.append((stream_name, converted_msgs))
            return converted
        except redis.exceptions.RedisError as e:
            log(f"[Redis consume error] {e}")
            return []

    def ack(self, group, msg_id):
        try:
            self.redis.xack(self.stream, group, msg_id)
        except redis.exceptions.RedisError as e:
            log(f"[Redis ack error] {e}")
