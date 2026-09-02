import socket

import pytest

from services import connect_security as security


def test_connect_token_contract_fits_a_telegram_start_payload():
    token = "A" * 43
    assert security.is_valid_connect_token(token)
    assert len(security.CONNECT_START_PREFIX + token) <= 64
    assert not security.is_valid_connect_token("A" * 42)
    assert not security.is_valid_connect_token("A" * 57)
    assert not security.is_valid_connect_token("!" + "A" * 42)


def test_normalise_site_url_rejects_non_https_and_obvious_ssrf_targets():
    assert security.normalise_site_url(" https://Shop.Example.com/path/ ") == "https://shop.example.com/path"

    for unsafe_url in (
        "http://shop.example.com",
        "https://user:pass@shop.example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://shop.example.com/?next=bad",
    ):
        with pytest.raises(security.ConnectValidationError):
            security.normalise_site_url(unsafe_url)


def test_public_host_resolution_rejects_private_dns_answers(monkeypatch):
    def private_answer(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))]

    monkeypatch.setattr(security.socket, "getaddrinfo", private_answer)
    with pytest.raises(security.ConnectValidationError):
        security.assert_site_host_is_public("https://shop.example.com")

    def public_answer(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(security.socket, "getaddrinfo", public_answer)
    security.assert_site_host_is_public("https://shop.example.com")


def test_connect_hmac_binds_platform_site_token_and_issue_time():
    proof = security.connect_proof("secret", "telegram", "https://shop.example", "A" * 43, 100)

    assert security.has_valid_connect_proof(
        proof, "secret", "telegram", "https://shop.example", "A" * 43, 100,
    )
    assert not security.has_valid_connect_proof(
        proof, "secret", "bale", "https://shop.example", "A" * 43, 100,
    )
    assert not security.has_valid_connect_proof(
        proof, "secret", "telegram", "https://shop.example", "A" * 43, 101,
    )
