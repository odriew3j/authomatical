"""Public, proof-checked endpoint for one-click WordPress pairing.

The ODview Sync plugin makes this request server-to-server from wp-admin.  It
registers a short-lived, opaque capability after proving it controls the
submitted WordPress installation.  The browser and QR code receive only a bot
deep link containing that capability; the WordPress shared secret never leaves
the server-to-server path or appears in a URL.
"""
from __future__ import annotations

import io
import logging
import time
from urllib.parse import urlencode

import qrcode
from qrcode.image.svg import SvgPathImage
from flask import Blueprint, Response, jsonify, request

from clients.site_connector_client import SiteConnectorClient, SiteConnectorError
from config import Config
from database.db import init_db
from database.repository import (
    create_pending_connection,
    pending_connection_is_available,
)
from services.connect_security import (
    CONNECT_START_PREFIX,
    MAX_CONNECT_SECRET_LENGTH,
    assert_site_host_is_public,
    has_valid_connect_proof,
    is_supported_connect_platform,
    is_valid_connect_token,
    normalise_bot_username,
    normalise_site_url,
    ConnectValidationError,
)


logger = logging.getLogger(__name__)
connect_bp = Blueprint("connect_bp", __name__)

# A plugin has no reason to send a large payload: token, platform, site URL and
# secret are each bounded below.  Bound the public endpoint before JSON parsing
# so it cannot become a body-buffering DoS vector.
MAX_REGISTER_BODY_BYTES = 4096
_REGISTER_FIELDS = frozenset({"token", "platform", "site_url", "secret", "issued_at"})


@connect_bp.after_request
def _protect_connect_responses(response: Response) -> Response:
    """Pairing JSON/QR responses contain bearer links; never cache or refer."""

    response.headers.setdefault("Cache-Control", "no-store, private")
    response.headers.setdefault("Pragma", "no-cache")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


def _error(message: str, status_code: int) -> tuple[Response, int]:
    # Messages intentionally describe the class of error but never echo a
    # submitted token, secret, HMAC, or URL back to an unauthenticated caller.
    return jsonify({"status": "error", "message": message}), status_code


def _configured_deep_link(platform: str, token: str) -> str | None:
    """Build the only supported deep-link payload server-side.

    In particular, callers cannot supply their own ``payload``/URL and trick
    the plugin into rendering it.  A platform-specific token is required,
    which makes the Telegram/Bale choice explicit and prevents cross-platform
    pairing completion.
    """

    if platform == "telegram":
        username = normalise_bot_username(Config.TELEGRAM_BOT_USERNAME)
        base = f"https://t.me/{username}" if username else None
    elif platform == "bale":
        username = normalise_bot_username(Config.BALE_BOT_USERNAME)
        base = f"https://ble.ir/{username}" if username else None
    else:
        return None
    # Both Telegram bot usernames and Bale's documented deep-link helper
    # require a bot-suffixed username. Treat a misconfigured deployment as
    # disabled instead of returning a link that opens a non-bot account.
    if not base or not username.lower().endswith("bot"):
        return None
    return f"{base}?{urlencode({'start': f'{CONNECT_START_PREFIX}{token}'})}"


def _qr_path(token: str, platform: str) -> str:
    """Return a relative QR route for the plugin to attach to its saved URL.

    Returning a relative path avoids trusting forwarded host/scheme headers at
    a TLS-terminating proxy. The plugin validates this exact path and combines
    it with the same configured HTTPS backend that received the registration.
    """

    return f"/api/connect/qr/{token}.svg?{urlencode({'platform': platform})}"


def _plugin_proves_site_control(site_url: str, secret: str) -> bool:
    """Check the supplied secret against the submitted ODview Sync instance.

    This is the registration authentication boundary: possessing a made-up
    secret is not enough; the backend independently calls the authenticated
    plugin ``/ping`` endpoint and requires it to report the same canonical
    site URL.  The bot repeats this verification immediately before it saves
    a tenant connection, so no unverified record can overwrite a tenant.
    """

    try:
        assert_site_host_is_public(site_url)
        site = SiteConnectorClient(
            site_url,
            secret,
            timeout=Config.CONNECT_VERIFICATION_TIMEOUT_SECONDS,
            # The plugin sends its canonical get_site_url().  Do not follow an
            # attacker-controlled redirect while proving an untrusted URL.
            allow_redirects=False,
        )
        info = site.ping()
    except (ConnectValidationError, SiteConnectorError):
        return False
    except Exception:
        # Do not include upstream exception text: HTTP libraries can include
        # URLs and headers, while neither helps a plugin admin recover here.
        logger.warning("One-click pairing site proof failed unexpectedly")
        return False

    if not isinstance(info, dict) or info.get("success") is not True:
        return False
    try:
        reported_url = normalise_site_url(info.get("site_url"))
    except ConnectValidationError:
        return False
    return reported_url == site_url


@connect_bp.route("/register", methods=["POST"])
def register() -> tuple[Response, int] | Response:
    """Register exactly one platform-bound connection capability.

    The plugin must generate a 256-bit base64url token and sign the canonical
    request tuple (including a fresh issue timestamp) with its existing shared
    secret. The signature is checked before the live authenticated WordPress
    ping, and no caller-controlled deep-link payload is accepted.
    """

    if not request.is_json:
        return _error("درخواست اتصال باید JSON باشد.", 415)
    raw_body = request.get_data(cache=True)
    if len(raw_body) > MAX_REGISTER_BODY_BYTES:
        return _error("درخواست اتصال بیش از حد بزرگ است.", 413)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - _REGISTER_FIELDS:
        return _error("فیلدهای درخواست اتصال نامعتبر است.", 400)

    token = data.get("token")
    platform = data.get("platform")
    raw_site_url = data.get("site_url")
    secret = data.get("secret")
    issued_at = data.get("issued_at")
    if not is_valid_connect_token(token):
        return _error("توکن اتصال نامعتبر است.", 400)
    if not is_supported_connect_platform(platform):
        return _error("پلتفرم اتصال نامعتبر است.", 400)
    if not isinstance(raw_site_url, str):
        return _error("آدرس سایت نامعتبر است.", 400)
    # Match WordPress's untrailingslashit() value for the HMAC wire contract.
    raw_site_url = raw_site_url.strip().rstrip("/")
    if not isinstance(secret, str) or not secret or len(secret) > MAX_CONNECT_SECRET_LENGTH:
        return _error("کلید امنیتی نامعتبر است.", 400)
    if isinstance(issued_at, bool) or not isinstance(issued_at, int):
        return _error("زمان درخواست اتصال نامعتبر است.", 400)
    # A signed request body may cross a queue/proxy only briefly. This bound,
    # plus the retained token digest, makes it useless to replay after a link
    # has expired or been consumed. The symmetric window tolerates reasonable
    # WordPress/backend clock skew without accepting a long-lived proof.
    if abs(int(time.time()) - issued_at) > Config.CONNECT_REGISTRATION_PROOF_MAX_AGE_SECONDS:
        return _error("زمان درخواست اتصال منقضی شده است؛ دوباره تلاش کنید.", 400)

    try:
        site_url = normalise_site_url(raw_site_url)
    except ConnectValidationError:
        return _error("آدرس سایت باید یک URL عمومی HTTPS معتبر باشد.", 400)

    # HMAC alone is not the full proof (a caller can invent a secret), but it
    # protects the exact request tuple. The authenticated /ping below proves
    # the secret is active at this specific ODview Sync installation.
    if not has_valid_connect_proof(
        request.headers.get("X-ODVIEW-CONNECT-PROOF"),
        secret,
        platform,
        raw_site_url,
        token,
        issued_at,
    ):
        return _error("اعتبار درخواست اتصال تأیید نشد.", 403)

    deep_link = _configured_deep_link(platform, token)
    if not deep_link:
        return _error("این ربات برای اتصال یک‌کلیکی در سرور پیکربندی نشده است.", 503)

    if not _plugin_proves_site_control(site_url, secret):
        return _error(
            "افزونهٔ ODview Sync و کلید امنیتی این سایت قابل تأیید نیست. "
            "فعال بودن افزونه و URL عمومی HTTPS سایت را بررسی کنید.",
            422,
        )

    try:
        init_db()
        create_pending_connection(
            token=token,
            platform=platform,
            site_url=site_url,
            secret=secret,
            ttl_seconds=Config.CONNECT_TOKEN_TTL_SECONDS,
        )
    except ValueError:
        # Extremely unlikely for a 256-bit token. Never overwrite a pending
        # capability if it does happen: wp-admin can generate a new one.
        return _error("لینک اتصال تکراری است؛ دوباره تلاش کنید.", 409)
    except Exception:
        # Avoid formatting database driver parameters: they can contain the
        # encrypted secret and must not enter a log sink either.
        logger.error("Could not persist a pending one-click connection")
        return _error("ثبت امن درخواست اتصال ناموفق بود.", 503)

    return jsonify({
        "status": "ok",
        "platform": platform,
        "expires_in": Config.CONNECT_TOKEN_TTL_SECONDS,
        "deep_links": {platform: deep_link},
        "qr_paths": {platform: _qr_path(token, platform)},
    })


@connect_bp.route("/qr/<token>.svg", methods=["GET"])
def qr_svg(token: str) -> Response:
    """Render a platform-bound deep link locally as a no-store SVG QR code.

    The QR payload is generated inside this backend process, never sent to a
    third-party QR-image service.  The endpoint only renders an active pairing
    record, avoiding a generic public QR-generation oracle.
    """

    platform = request.args.get("platform", "")
    if not is_valid_connect_token(token) or not is_supported_connect_platform(platform):
        return Response(status=404)

    try:
        init_db()
        active = pending_connection_is_available(token, platform)
    except Exception:
        logger.error("Could not check one-click pairing QR availability")
        return Response(status=503)
    if not active:
        return Response(status=404)

    deep_link = _configured_deep_link(platform, token)
    if not deep_link:
        return Response(status=404)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    output = io.BytesIO()
    image.save(output)
    response = Response(output.getvalue(), mimetype="image/svg+xml")
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return response
