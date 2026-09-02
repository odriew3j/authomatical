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


def test_redacts_one_click_request_json_fields():
    message = "{'token': 'opaque-token', 'secret': 'site-secret', 'X-ODVIEW-CONNECT-PROOF': 'proof-value'}"

    redacted = redact_sensitive_text(message)

    for value in ("opaque-token", "site-secret", "proof-value"):
        assert value not in redacted


def test_redacts_one_click_pairing_tokens_from_deep_and_qr_urls():
    connect_token = "Abcdefghijklmnopqrstuvwxyz0123456789_-ABCDEfghi"
    message = (
        "https://t.me/MyBot?start=connect_" + connect_token + " "
        "GET /api/connect/qr/" + connect_token + ".svg?platform=telegram"
    )

    redacted = redact_sensitive_text(message)

    assert connect_token not in redacted
    assert "connect_<redacted-connect-token>" in redacted
    assert "/api/connect/qr/<redacted-connect-token>.svg" in redacted


def test_legacy_stdout_log_helper_uses_the_redactor(capsys):
    from utils.helpers import log

    token = "Z" * 43
    log("pairing is connect_" + token)

    output = capsys.readouterr().out
    assert token not in output
    assert "<redacted-connect-token>" in output


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
