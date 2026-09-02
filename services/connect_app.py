"""Minimal public process for ODview Sync one-click pairing.

Keep this separate from the optional operator dashboard: a reverse proxy can
publish only this tiny surface to WordPress installations while dashboard/API
routes remain private or independently authenticated.
"""
import os

from flask import Flask, jsonify

from services.blueprints.connect import connect_bp
from utils.logging_utils import configure_worker_logging


# Reuse the project's redacting formatter because this public process receives
# URLs containing short-lived bearer capabilities (not just bot workers).
configure_worker_logging()
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))
app.register_blueprint(connect_bp, url_prefix="/api/connect")


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})
