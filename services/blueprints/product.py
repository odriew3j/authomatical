from flask import Blueprint, request, jsonify, render_template
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from messaging.redis_broker import RedisBroker
from utils.helpers import log

template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
product_bp = Blueprint("product_bp", __name__, template_folder=template_dir)
broker = RedisBroker(stream="product_jobs")


@product_bp.route("/publish_product", methods=["GET"])
def index():
    return render_template("index_products.html")

@product_bp.route("/publish_product", methods=["POST"])
def publish_product():
    data = request.json or {}

    job_data = {
        "title": data.get("title"),
        "price": data.get("price", 0),
        "sale_price": data.get("sale_price"),
        "category": data.get("category", "Uncategorized"),
        "brand": data.get("brand"),
        "tags": ",".join(data.get("tags", [])),
        "images": ",".join(data.get("images", [])),
        "keywords": data.get("keywords", ""),
        "tone": data.get("tone", "informative"),
        "audience": data.get("audience", "general")
    }

    job_id = broker.publish(job_data)
    log(f"Published product job id: {job_id}")
    return jsonify({"job_id": str(job_id, 'utf-8'), "status": "queued"})

