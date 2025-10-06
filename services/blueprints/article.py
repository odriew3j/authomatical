from flask import Blueprint, request, jsonify, render_template
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from messaging.redis_broker import RedisBroker
from utils.helpers import log

template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
article_bp = Blueprint("article_bp", __name__, template_folder=template_dir)
broker = RedisBroker(stream="article_jobs")

@article_bp.route("/publish_article", methods=["GET"])
def index():
    return render_template("index_articles.html")

@article_bp.route("/publish_article", methods=["POST"])
def publish_article():
    data = request.json or {}
    job_data = {
        "keywords": data.get("keywords"),
        "chapters": data.get("chapters", 5),
        "max_words": data.get("max_words", 500),
        "tone": data.get("tone", "informative"),
        "audience": data.get("audience", "general")
    }

    job_id = broker.publish(job_data)
    log(f"Published article job id: {job_id}")
    return jsonify({"job_id": str(job_id, 'utf-8'), "status": "queued"})

