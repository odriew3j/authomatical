"""Backend half of the "اتصال با یک کلیک" (one-click connect) flow.

The ODview Sync WordPress plugin generates a short-lived, random token in
wp-admin and POSTs it here together with the site's own secret — *before*
any chat conversation happens. The bot later consumes that token exactly
once, when the person opens the returned /start connect_<token> deep link
(see workers/common_handlers.py), so the secret never has to be typed or
pasted into chat.

This endpoint is deliberately public/unauthenticated (there is no chat
identity yet to authenticate against) — the token is the only thing of
value handed back, and it must have enough entropy that it can't be
guessed. The plugin is responsible for generating it; this endpoint just
enforces a sane minimum length as a sanity check, not as its security
boundary.
"""
import logging

from flask import Blueprint, jsonify, request

from config import Config
from database.db import init_db
from database.repository import create_pending_connection
from utils.helpers import log

logger = logging.getLogger(__name__)

connect_bp = Blueprint("connect_bp", __name__)

# Below this, a token doesn't carry enough entropy to safely be the sole
# secret protecting a pending connection.
MIN_TOKEN_LENGTH = 32
MAX_TOKEN_LENGTH = 128


@connect_bp.route("/register", methods=["POST"])
def register():
    init_db()
    data = request.get_json(silent=True) or {}

    token = str(data.get("token") or "").strip()
    site_url = str(data.get("site_url") or "").strip().rstrip("/")
    secret = str(data.get("secret") or "").strip()

    if not (MIN_TOKEN_LENGTH <= len(token) <= MAX_TOKEN_LENGTH):
        return jsonify({"status": "error", "message": "توکن نامعتبر است."}), 400
    if not site_url.startswith(("http://", "https://")):
        return jsonify({"status": "error", "message": "آدرس سایت نامعتبر است."}), 400
    if not secret:
        return jsonify({"status": "error", "message": "کلید امنیتی لازم است."}), 400

    try:
        create_pending_connection(
            token, site_url, secret, ttl_seconds=Config.CONNECT_TOKEN_TTL_SECONDS,
        )
    except ValueError:
        # Astronomically unlikely with a properly random token — treat it
        # as a request to retry with a fresh one rather than a fatal error.
        return jsonify({"status": "error", "message": "توکن تکراری است، دوباره تلاش کن."}), 409
    except Exception:
        logger.exception("Could not persist pending connection")
        return jsonify({"status": "error", "message": "ثبت درخواست اتصال ناموفق بود."}), 503

    payload = str(data.get("payload") or f"connect_{token}")
    deep_links = {}
    if Config.TELEGRAM_BOT_USERNAME:
        deep_links["telegram"] = f"https://t.me/{Config.TELEGRAM_BOT_USERNAME}?start={payload}"
    if Config.BALE_BOT_USERNAME:
        deep_links["bale"] = f"https://ble.ir/{Config.BALE_BOT_USERNAME}?start={payload}"

    log(f"Registered one-click connect token for site={site_url}")
    return jsonify({
        "status": "ok",
        "expires_in": Config.CONNECT_TOKEN_TTL_SECONDS,
        "deep_links": deep_links,
    })