"""Small, worker-safe notification helper for Telegram and Bale.

The long-running bot applications own their polling loops, so background
workers must not construct another ``telegram.ext.Application`` just to send
one completion message.  Both APIs expose a compatible HTTPS ``sendMessage``
endpoint; this module calls that endpoint directly and returns ``False`` on a
delivery problem instead of crashing or requeueing an already-published job.
"""
import logging
from typing import Any

import requests

from config import Config

logger = logging.getLogger(__name__)

_PLATFORM_CONFIG = {
    "telegram": ("https://api.telegram.org/bot", "TELEGRAM_BOT_TOKEN"),
    "bale": ("https://tapi.bale.ai/bot", "BALE_BOT_TOKEN"),
}


def _token_for(platform: str) -> str | None:
    if platform == "telegram":
        return Config.TELEGRAM_BOT_TOKEN
    if platform == "bale":
        return Config.BALE_BOT_TOKEN
    return None


def send_platform_message(platform: str, chat_id: int | str, text: str, *, timeout: int | None = None) -> bool:
    """Deliver plain text to one Telegram/Bale chat.

    The function intentionally does not raise for an unavailable platform,
    missing token, network failure, or non-2xx response.  Article publishing
    has already succeeded by the time it is called; failure to notify a user
    should be logged but must never turn that job into a retry loop.
    """
    normalized_platform = (platform or "").strip().lower()
    config = _PLATFORM_CONFIG.get(normalized_platform)
    if not config:
        logger.warning("Cannot notify an unknown platform: %r", platform)
        return False

    base_url, token_name = config
    token = _token_for(normalized_platform)
    if not token:
        logger.error("Cannot send %s notification: %s is not configured", normalized_platform, token_name)
        return False

    payload: dict[str, Any] = {"chat_id": chat_id, "text": str(text)}
    try:
        response = requests.post(
            f"{base_url}{token}/sendMessage",
            json=payload,
            timeout=timeout if timeout is not None else Config.TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Could not deliver %s notification to chat %s: %s", normalized_platform, chat_id, exc)
        return False

    if not response.ok:
        # Never log the URL: it embeds the bot token.
        logger.warning(
            "%s notification failed: status=%s body=%s",
            normalized_platform,
            response.status_code,
            response.text[:500],
        )
        return False

    try:
        body = response.json()
    except ValueError:
        logger.warning("%s notification endpoint returned invalid JSON", normalized_platform)
        return False

    if isinstance(body, dict) and body.get("ok") is False:
        logger.warning("%s notification endpoint rejected the message: %s", normalized_platform, str(body)[:500])
        return False

    return True
