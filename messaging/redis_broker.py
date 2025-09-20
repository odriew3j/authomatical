import redis
from config import Config

class RedisBroker:
    def __init__(self, stream="jobs"):
        self.redis = redis.Redis.from_url(Config.REDIS_URL)
        self.stream = stream

    def publish(self, data):
        return self.redis.xadd(self.stream, data)

    def consume(self, group, consumer, block=5000, count=1):
        try:
            self.redis.xgroup_create(self.stream, group, id="0", mkstream=True)
        except redis.exceptions.ResponseError:
            pass
        messages = self.redis.xreadgroup(group, consumer, {self.stream: ">"}, count=count, block=block)
        return messages

    def ack(self, group, msg_id):
        self.redis.xack(self.stream, group, msg_id)
