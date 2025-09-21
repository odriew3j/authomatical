# services/web_app.py
from flask import Flask, request, jsonify
from messaging.redis_broker import RedisBroker
from utils.helpers import log

app = Flask(__name__)

broker = RedisBroker(stream="article_jobs")

@app.route("/", methods=["GET", "POST"])
def index_or_publish():
    if request.method == "GET":

        return jsonify({
            "service": "authomatical",
            "status": "running",
            "message": "Send a POST request with article data to publish jobs."
        })

    if request.method == "POST":
        data = request.json or {}
        job_data = {
            "keywords": data.get("keywords"),
            "chapters": data.get("chapters", 5),
            "max_words": data.get("max_words", 500),
            "tone": data.get("tone", "informative"),
            "audience": data.get("audience", "general")
        }

        # encode to bytes for Redis Stream
        job_data_bytes = {k: str(v).encode() for k, v in job_data.items()}

        job_id = broker.publish(job_data_bytes)
        log(f"Published job id: {job_id}")

        return jsonify({"job_id": job_id, "status": "queued"})
