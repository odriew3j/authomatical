"""Safe logging configuration for long-running bot workers.

python-telegram-bot/httpx logs complete request URLs at INFO level.  Bot API
URLs contain the bot token, so workers must never emit those URLs verbatim.
"""
import logging
import re
from typing import Any

DEFAULT_LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"

# Covers Telegram/Bale API URLs such as https://…/bot123:token/getUpdates.
_BOT_URL_TOKEN_RE = re.compile(
    r"(?P<prefix>https?://[^\s/]+/bot)(?P<token>[^\s/?#]+)",
    flags=re.IGNORECASE,
)
# Covers a token printed outside a URL.  Both Telegram and Bale use a numeric
# bot id followed by a colon and a long URL-safe secret.
_BOT_TOKEN_RE = re.compile(r"(?<![\w-])\d{6,}:[A-Za-z0-9_-]{10,}(?![\w-])")
_BEARER_RE = re.compile(
    r"(?i)(?P<prefix>\bauthorization\s*[:=]\s*bearer\s+|\bbearer\s+)(?P<secret>[^\s,]+)"
)
_ODVIEW_SECRET_RE = re.compile(r"(?i)(\bx-odview-secret\s*[:=]\s*)[^\s,]+")
_OPENROUTER_KEY_RE = re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]+")


def redact_sensitive_text(value: Any) -> str:
    """Return a log-safe string with API tokens/secrets removed."""
    text = str(value)
    text = _BOT_URL_TOKEN_RE.sub(r"\g<prefix><redacted>", text)
    text = _BOT_TOKEN_RE.sub("<redacted-bot-token>", text)
    text = _BEARER_RE.sub(r"\g<prefix><redacted>", text)
    text = _ODVIEW_SECRET_RE.sub(r"\1<redacted>", text)
    return _OPENROUTER_KEY_RE.sub("<redacted-openrouter-key>", text)


class RedactingFormatter(logging.Formatter):
    """Apply redaction after normal formatting, including tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_text(super().format(record))


def configure_worker_logging(level: int = logging.INFO) -> None:
    """Install redacting output and silence successful HTTP request URLs.

    It is safe to call more than once: existing root handlers are reused so
    worker startup cannot duplicate every log line.
    """
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())

    formatter = RedactingFormatter(DEFAULT_LOG_FORMAT)
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

    root_logger.setLevel(level)

    # httpx emits an INFO record for every successful request and includes the
    # full URL. Network warnings/errors still remain visible and are redacted
    # by the formatter above.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
