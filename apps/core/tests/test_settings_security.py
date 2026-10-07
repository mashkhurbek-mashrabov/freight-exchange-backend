"""Tests for production settings security hardening."""

import importlib
import os
import subprocess
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured


def test_prod_settings_with_valid_env(monkeypatch: pytest.MonkeyPatch):
    """Prod settings loaded with valid environment asserts all security hardening flags."""
    monkeypatch.setenv("SECRET_KEY", "test-prod-secret-key-at-least-50-characters-long-1234567890")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.freight.uz,admin.freight.uz")
    monkeypatch.setenv("OTP_DEV_CODE", "999999")  # Should be overridden by prod settings

    # Clean cached modules so environ reads fresh env
    sys.modules.pop("config.settings.prod", None)
    sys.modules.pop("config.settings.base", None)

    prod = importlib.import_module("config.settings.prod")

    assert prod.DEBUG is False
    assert prod.ALLOWED_HOSTS == ["api.freight.uz", "admin.freight.uz"]
    assert "*" not in prod.ALLOWED_HOSTS
    assert prod.SECRET_KEY == "test-prod-secret-key-at-least-50-characters-long-1234567890"
    assert prod.OTP_DEV_CODE == ""
    assert prod.SECURE_SSL_REDIRECT is False
    assert prod.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.SECURE_HSTS_SECONDS == 31536000
    assert prod.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert prod.SECURE_HSTS_PRELOAD is True
    assert prod.SECURE_CONTENT_TYPE_NOSNIFF is True
    assert prod.X_FRAME_OPTIONS == "DENY"
    assert prod.DATA_UPLOAD_MAX_MEMORY_SIZE >= 10 * 1024 * 1024
    assert prod.FILE_UPLOAD_MAX_MEMORY_SIZE >= 10 * 1024 * 1024
    assert prod.CORS_ALLOW_ALL_ORIGINS is False


def test_prod_settings_secret_key_required(monkeypatch: pytest.MonkeyPatch):
    """Prod settings without SECRET_KEY or with insecure default raises ImproperlyConfigured."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    sys.modules.pop("config.settings.prod", None)
    sys.modules.pop("config.settings.base", None)

    with pytest.raises(ImproperlyConfigured) as exc:
        importlib.import_module("config.settings.prod")
    assert "SECRET_KEY" in str(exc.value)

    monkeypatch.setenv("SECRET_KEY", "dev-insecure-key")
    sys.modules.pop("config.settings.prod", None)
    sys.modules.pop("config.settings.base", None)

    with pytest.raises(ImproperlyConfigured) as exc2:
        importlib.import_module("config.settings.prod")
    assert "SECRET_KEY" in str(exc2.value)


def test_prod_settings_ssl_redirect_toggled(monkeypatch: pytest.MonkeyPatch):
    """SECURE_SSL_REDIRECT can be toggled via environment."""
    monkeypatch.setenv("SECRET_KEY", "test-prod-secret-key-at-least-50-characters-long-1234567890")
    monkeypatch.setenv("SECURE_SSL_REDIRECT", "True")
    sys.modules.pop("config.settings.prod", None)
    sys.modules.pop("config.settings.base", None)

    prod = importlib.import_module("config.settings.prod")
    assert prod.SECURE_SSL_REDIRECT is True


def test_prod_settings_subprocess_isolated():
    """Verify prod settings in an isolated subprocess with minimal env."""
    clean_env = {
        "PATH": os.environ.get("PATH", ""),
        "SECRET_KEY": "subprocess-secret-key-at-least-50-characters-long-12345",
        "ALLOWED_HOSTS": "fx.example.com",
        "OTP_DEV_CODE": "999999",
        "DATABASE_URL": "postgres://postgres:postgres@localhost:5433/test_db",
        "REDIS_URL": "redis://localhost:6380/0",
    }
    cmd = [
        sys.executable,
        "-c",
        (
            "import config.settings.prod as s; "
            "assert s.DEBUG is False; "
            "assert s.OTP_DEV_CODE == ''; "
            "assert s.ALLOWED_HOSTS == ['fx.example.com']; "
            "assert s.SESSION_COOKIE_SECURE is True; "
            "assert s.CSRF_COOKIE_SECURE is True; "
            "assert s.X_FRAME_OPTIONS == 'DENY'; "
            "assert s.CORS_ALLOW_ALL_ORIGINS is False; "
            "print('PROD_SETTINGS_OK')"
        ),
    ]
    proc = subprocess.run(cmd, env=clean_env, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"Subprocess failed:\n{proc.stderr}"
    assert "PROD_SETTINGS_OK" in proc.stdout
