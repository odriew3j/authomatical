import io
import logging

from utils.logging_utils import RedactingFormatter, redact_sensitive_text


TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdef"


def test_redacts_bot_tokens_in_urls_and_standalone_text():
    message = (
        f"POST https://tapi.bale.ai/bot{TOKEN}/getUpdates failed; "
        f"telegram token is {TOKEN}"
    )

    redacted = redact_sensitive_text(message)

    assert TOKEN not in redacted
    assert "https://tapi.bale.ai/bot<redacted>/getUpdates" in redacted
    assert "<redacted-bot-token>" in redacted


def test_redacts_authorization_and_site_secrets():
    message = "Authorization: Bearer sk-or-v1-very-secret-key X-ODVIEW-SECRET: site-secret"
    redacted = redact_sensitive_text(message)

    assert "sk-or-v1-very-secret-key" not in redacted
    assert "site-secret" not in redacted
    assert "Authorization: Bearer <redacted>" in redacted
    assert "X-ODVIEW-SECRET: <redacted>" in redacted


def test_redacting_formatter_cleans_exception_tracebacks_too():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter("%(levelname)s %(message)s"))
    logger = logging.getLogger("test.redacting_formatter")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.ERROR)

    try:
        raise RuntimeError(f"request URL https://api.telegram.org/bot{TOKEN}/sendMessage")
    except RuntimeError:
        logger.exception("Delivery failed")

    output = stream.getvalue()
    assert TOKEN not in output
    assert "/bot<redacted>/sendMessage" in output
