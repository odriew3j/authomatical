from datetime import datetime

from utils.logging_utils import redact_sensitive_text


def log(message: str):
    """Legacy stdout helper with the same credential redaction as loggers."""

    print(f"[{datetime.now()}] {redact_sensitive_text(message)}")
