from messaging.redis_broker import RedisBroker
from utils.helpers import log

if __name__ == "__main__":
    log("=== Article Job Publisher ===")
    
    keywords = input("Enter main keywords/topic: ")
    chapters = input("Number of chapters (default 5): ")
    max_words = input("Max words per chapter/section (optional, default 500): ")
    tone = input("Tone (informative, persuasive, friendly, technical) [informative]: ")
    audience = input("Audience (general, developers, marketers, etc.) [general]: ")

    broker = RedisBroker(stream="article_jobs")

    try:
        broker.redis.xgroup_create(broker.stream, "article_jobs_group", id="0", mkstream=True)
    except Exception:
        pass

    job_data = {
        "keywords": keywords,
        "chapters": chapters,
        "max_words": max_words,
        "tone": tone,
        "audience": audience
    }

    job_data_bytes = {k: str(v).encode() for k, v in job_data.items()}

    job_id = broker.publish(job_data_bytes)
    log(f"Published job id: {job_id}")
