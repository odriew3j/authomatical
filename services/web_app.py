from flask import Flask, render_template, jsonify, request
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.blueprints.article import article_bp
from services.blueprints.product import product_bp
from messaging.redis_broker import RedisBroker
from database.db import init_db
from database.repository import list_article_jobs, list_connected_tenants

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
    """Return Article history from PostgreSQL, not Redis stream history.

    Redis remains useful for inspecting old product messages, but durable
    article lifecycle/history lives exclusively in article_jobs and related
    tables.  This also leaves legacy article stream entries intact instead of
    accidentally treating them as current business records.
    """

    if job_type == "article":
        init_db()
        jobs = list_article_jobs(limit=50)
        return jsonify([
            {
                "id": str(job["id"]),
                "status": job["status"],
                "tenant_id": job["tenant_id"],
                "requested_at": job["requested_at"],
                "completed_at": job["completed_at"],
                "data": {
                    "keywords": job["keywords"],
                    "article_type": job["article_type"],
                    "notes": job["notes"],
                },
            }
            for job in jobs
        ])

    if job_type != "product":
        return jsonify({"status": "error", "message": "نوع job معتبر نیست."}), 404

    # product_jobs is retained only for visibility of older queue entries;
    # product creation itself is synchronous and tenant-scoped.
    messages = product_broker.redis.xrevrange(product_broker.stream, count=20)
    jobs = []
    for msg_id, fields in messages:
        decode = lambda value: value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
        jobs.append({
            "id": decode(msg_id),
            "data": {decode(key): decode(value) for key, value in fields.items()},
        })
    return jsonify(jobs)


@app.route("/api/jobs/<job_type>/delete/<job_id>", methods=["POST"])
def delete_job(job_type, job_id):
    if job_type == "article":
        # Article deletion/cancellation is deliberately not a Redis XDEL.  It
        # would erase only a transport clue while leaving (or worse, hiding)
        # durable audit history.  A future explicit cancellation policy can
        # add its own durable status and authorization checks.
        return jsonify({
            "status": "error",
            "message": "حذف job مقاله از Redis غیرفعال است؛ تاریخچهٔ پایدار حفظ می‌شود.",
        }), 409
    if job_type != "product":
        return jsonify({"status": "error", "message": "نوع job معتبر نیست."}), 404

    product_broker.redis.xdel(product_broker.stream, job_id)
    return jsonify({"status": "deleted", "job_id": job_id})


@app.route("/api/jobs/<job_type>/requeue/<job_id>", methods=["POST"])
def requeue_job(job_type, job_id):
    if job_type == "article":
        # Replaying a terminal failure can duplicate a WordPress post after an
        # ambiguous network outcome.  Keep the old stream record observable
        # until an explicit durable/manual recovery policy is implemented.
        return jsonify({
            "status": "error",
            "message": "ارسال دوبارهٔ مقاله نیازمند فرایند بازیابی پایدار است و فعلاً غیرفعال است.",
        }), 409
    if job_type != "product":
        return jsonify({"status": "error", "message": "نوع job معتبر نیست."}), 404

    msg = product_broker.redis.xrange(product_broker.stream, min=job_id, max=job_id)
    if msg:
        _, fields = msg[0]
        product_broker.publish(fields)
        return jsonify({"status": "requeued", "job_id": job_id})
    return jsonify({"status": "not_found", "job_id": job_id})

if __name__ == "__main__":
    app.run(debug=True)