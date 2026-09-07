"""Validation and protocol primitives for one-click bot pairing.

This module intentionally has no Flask or WordPress dependencies so the web
endpoint and both bot workers enforce the exact same opaque-token contract.
A connect token is a bearer capability; it is never a user-facing password and
must not be written to logs.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit


CONNECT_PLATFORMS = frozenset({"telegram", "bale"})
CONNECT_START_PREFIX = "connect_"

# Telegram deep-link payloads are limited to 64 URL-safe characters.  The
# prefix consumes eight characters, so keep the opaque token at 56 characters
# or less.  The plugin generates 32 random bytes as unpadded base64url (43
# characters / 256 bits), well above this minimum.
MIN_CONNECT_TOKEN_LENGTH = 43
MAX_CONNECT_TOKEN_LENGTH = 56
CONNECT_TOKEN_RE = re.compile(
    rf"^[A-Za-z0-9_-]{{{MIN_CONNECT_TOKEN_LENGTH},{MAX_CONNECT_TOKEN_LENGTH}}}$"
)
CONNECT_PROOF_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
BOT_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,63}$")

MAX_SITE_URL_LENGTH = 500
MAX_CONNECT_SECRET_LENGTH = 512


class ConnectValidationError(ValueError):
    """Raised for a malformed or unsafe pairing input without exposing it."""


def is_supported_connect_platform(value: object) -> bool:
    return isinstance(value, str) and value in CONNECT_PLATFORMS


def is_valid_connect_token(value: object) -> bool:
    return isinstance(value, str) and CONNECT_TOKEN_RE.fullmatch(value) is not None


def normalise_bot_username(value: object) -> str | None:
    """Return a URL-safe configured bot username, or ``None`` if disabled.

    The configuration is deployment-owned, not a request parameter.  Keeping
    it constrained here prevents a bad environment value from turning a
    pairing response into an arbitrary URL.
    """

    if not isinstance(value, str):
        return None
    username = value.strip().lstrip("@")
    if not BOT_USERNAME_RE.fullmatch(username):
        return None
    return username


def normalise_site_url(value: object) -> str:
    """Canonicalise an externally reachable HTTPS WordPress site URL.

    Pairing asks the backend to contact the supplied site during registration,
    so this rejects obvious SSRF targets (credentials, localhost and non-global
    literal IPs) before any network call.  ``assert_site_host_is_public`` adds
    DNS-address validation immediately before that call.
    """

    if not isinstance(value, str):
        raise ConnectValidationError("site URL must be a string")
    raw = value.strip().rstrip("/")
    if not raw or len(raw) > MAX_SITE_URL_LENGTH:
        raise ConnectValidationError("site URL length is invalid")
    if any(ord(character) < 32 for character in raw):
        raise ConnectValidationError("site URL contains control characters")

    try:
        parsed = urlsplit(raw)
        port = parsed.port  # Accessing this validates malformed ports.
    except ValueError as exc:
        raise ConnectValidationError("site URL is malformed") from exc

    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ConnectValidationError("site URL must use HTTPS and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ConnectValidationError("site URL credentials are not allowed")
    if parsed.query or parsed.fragment:
        raise ConnectValidationError("site URL must not include a query or fragment")

    host = parsed.hostname.rstrip(".").lower()
    if not host or host == "localhost" or host.endswith(".localhost"):
        raise ConnectValidationError("local hosts are not allowed")
    if host.endswith((".local", ".internal", ".lan", ".home", ".test")):
        raise ConnectValidationError("private host names are not allowed")

    try:
        ip_address = ipaddress.ip_address(host)
    except ValueError:
        ip_address = None
    if ip_address is not None and not ip_address.is_global:
        raise ConnectValidationError("non-public IP addresses are not allowed")

    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ConnectValidationError("site host is malformed") from exc

    # Explicitly normalise HTTPS's default port so the ping response can be
    # compared reliably with the URL registered by the plugin.
    if port in (None, 443):
        netloc = f"[{host}]" if ":" in host else host
    else:
        netloc_host = f"[{host}]" if ":" in host else host
        netloc = f"{netloc_host}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", netloc, path, "", ""))


def assert_site_host_is_public(site_url: str) -> None:
    """Reject a hostname that currently resolves to a non-public address.

    This is deliberately performed right before the registration proof ping.
    It blocks the usual DNS aliases to loopback/private/link-local services as
    well as literal IP forms.  A production deployment still needs ordinary
    egress controls; this check is a defence-in-depth boundary, not a reason
    to expose internal services to the web container.
    """

    parsed = urlsplit(site_url)
    host = parsed.hostname
    if not host:  # ``normalise_site_url`` has already checked this.
        raise ConnectValidationError("site host is missing")

    try:
        addresses = socket.getaddrinfo(
            host,
            parsed.port or 443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ConnectValidationError("site host could not be resolved") from exc

    if not addresses:
        raise ConnectValidationError("site host could not be resolved")

    for _family, _socktype, _proto, _canonname, sockaddr in addresses:
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError as exc:
            raise ConnectValidationError("site host resolved unexpectedly") from exc
        if not address.is_global:
            raise ConnectValidationError("site host resolves to a non-public address")


def connect_proof(
    secret: str,
    platform: str,
    site_url: str,
    token: str,
    issued_at: int,
) -> str:
    """Build the HMAC expected from the plugin's server-to-server request.

    ``issued_at`` prevents a captured registration body from reviving the same
    expired/consumed token after its digest tombstone has eventually been
    cleaned up.
    """

    message = f"{platform}\n{site_url}\n{token}\n{issued_at}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def has_valid_connect_proof(
    proof: object,
    secret: str,
    platform: str,
    site_url: str,
    token: str,
    issued_at: int,
) -> bool:
    if not isinstance(proof, str) or CONNECT_PROOF_RE.fullmatch(proof) is None:
        return False
    return hmac.compare_digest(
        proof.lower(),
        connect_proof(secret, platform, site_url, token, issued_at),
    )


def status_proof(secret: str, site_url: str, issued_at: int) -> str:
    """HMAC for the read-only /status check.

    Deliberately a different message shape (a literal "status" component
    instead of platform/token) than ``connect_proof`` so a captured proof for
    one endpoint is never replayable against the other.
    """

    message = f"status\n{site_url}\n{issued_at}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def has_valid_status_proof(proof: object, secret: str, site_url: str, issued_at: int) -> bool:
    if not isinstance(proof, str) or CONNECT_PROOF_RE.fullmatch(proof) is None:
        return False
    return hmac.compare_digest(proof.lower(), status_proof(secret, site_url, issued_at))


def connect_token_digest(token: str) -> str:
    """Stable lookup digest; raw bearer tokens are never persisted."""

    return hashlib.sha256(token.encode("ascii")).hexdigest()
