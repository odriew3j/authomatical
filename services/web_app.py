from flask import Flask, render_template, jsonify, request
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.blueprints.article import article_bp
from services.blueprints.product import product_bp
from messaging.redis_broker import RedisBroker
from database.db import init_db
from database.repository import list_connected_tenants

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))

app.register_blueprint(article_bp, url_prefix="/articles")
app.register_blueprint(product_bp, url_prefix="/products")

# Redis brokers
article_broker = RedisBroker(stream="article_jobs")
# NOTE: product_jobs is no longer consumed by anything — product creation
# is now synchronous (see services/blueprints/product.py and
# workers/common_handlers.py). This broker instance and the generic job
# viewer below are kept only so any product_jobs entries queued by an
# older deployment remain visible/inspectable in the dashboard.
product_broker = RedisBroker(stream="product_jobs")

@app.route("/")
def dashboard():
    return render_template("dashboard_advanced.html")


@app.route("/api/tenants", methods=["GET"])
def list_tenants():
    """Tenants with a verified site connection — powers the tenant picker
    on both the product and article web forms. The web dashboard has no
    chat identity of its own (unlike the bot), so an operator must pick
    which tenant's site any web-originated action applies to."""
    init_db()
    return jsonify(list_connected_tenants())

@app.route("/api/jobs/<job_type>", methods=["GET"])
def get_jobs(job_type):
    """
    job_type: 'article' یا 'product'
    """
    broker = article_broker if job_type == "article" else product_broker
    # Read the last 20 messages (simple)
    messages = broker.redis.xrevrange(broker.stream, count=20)
    jobs = []
    for msg_id, fields in messages:
        jobs.append({
            "id": msg_id.decode(),
            "data": {k.decode(): v.decode() for k,v in fields.items()}
        })
    return jsonify(jobs)

@app.route("/api/jobs/<job_type>/delete/<job_id>", methods=["POST"])
def delete_job(job_type, job_id):
    broker = article_broker if job_type == "article" else product_broker
    broker.redis.xdel(broker.stream, job_id)
    return jsonify({"status": "deleted", "job_id": job_id})

@app.route("/api/jobs/<job_type>/requeue/<job_id>", methods=["POST"])
def requeue_job(job_type, job_id):
    broker = article_broker if job_type == "article" else product_broker
    msg = broker.redis.xrange(broker.stream, min=job_id, max=job_id)
    if msg:
        _, fields = msg[0]
        broker.publish(fields)
        return jsonify({"status": "requeued", "job_id": job_id})
    return jsonify({"status": "not_found", "job_id": job_id})

if __name__ == "__main__":
    app.run(debug=True)