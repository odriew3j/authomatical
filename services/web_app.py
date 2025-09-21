from flask import Flask, render_template, jsonify, request
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blueprints.article import article_bp
from blueprints.product import product_bp
from messaging.redis_broker import RedisBroker

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))

app.register_blueprint(article_bp, url_prefix="/articles")
app.register_blueprint(product_bp, url_prefix="/products")

# Redis brokers
article_broker = RedisBroker(stream="article_jobs")
product_broker = RedisBroker(stream="product_jobs")

@app.route("/")
def dashboard():
    return render_template("dashboard_advanced.html")

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
