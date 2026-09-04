import pytest

from app.callback_validation import validate_callback_url


def test_rejects_non_http_scheme(monkeypatch):
    monkeypatch.setenv("CALLBACK_ALLOWED_HOSTS", "localhost")
    with pytest.raises(ValueError):
        validate_callback_url("ftp://localhost")


def test_rejects_unknown_host(monkeypatch):
    monkeypatch.setenv("CALLBACK_ALLOWED_HOSTS", "localhost")
    with pytest.raises(ValueError):
        validate_callback_url("http://evil.com")


def test_rejects_private_ip(monkeypatch):
    monkeypatch.setenv("CALLBACK_ALLOWED_HOSTS", "localhost")
    with pytest.raises(ValueError):
        validate_callback_url("http://169.254.169.254")


def test_accepts_allowed_host(monkeypatch):
    monkeypatch.setenv("CALLBACK_ALLOWED_HOSTS", "localhost")
    validate_callback_url("http://localhost/callback")


def test_empty_allowlist_rejects_all(monkeypatch):
    monkeypatch.setenv("CALLBACK_ALLOWED_HOSTS", "")
    with pytest.raises(ValueError):
        validate_callback_url("http://localhost")
