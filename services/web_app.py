import sys
import os

# مسیر ریشه پروژه (دایرکتوری بالا نسبت به services)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify
from messaging.redis_broker import RedisBroker
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))
broker = RedisBroker(stream="article_jobs")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/submit", methods=["POST"])
def submit():
    text = request.form.get("keywords")
    if not text:
        return jsonify({"status": "error", "message": "لطفاً موضوع مقاله وارد شود."})

    job_data = {
        "keywords": text,
        "chapters": "5",
        "max_words": "500",
        "tone": "informative",
        "audience": "general"
    }
    job_data_bytes = {k: str(v).encode() for k, v in job_data.items()}

    job_id = broker.publish(job_data_bytes)
    logging.info(f"Published job id: {job_id}")

    job_id_str = job_id.decode() if isinstance(job_id, bytes) else str(job_id)

    return jsonify({"status": "success", "message": "درخواستت ثبت شد، مقاله در حال تولید است...", "job_id_str": job_id_str})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
