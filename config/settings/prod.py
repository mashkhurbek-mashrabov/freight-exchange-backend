"""Production settings."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])  # noqa: F405

# SECRET_KEY is strictly required from environment with no insecure fallback
try:
    SECRET_KEY = env("SECRET_KEY")  # noqa: F405
    if not SECRET_KEY or SECRET_KEY == "dev-insecure-key":
        raise ImproperlyConfigured("SECRET_KEY must be set to a secure value in production.")
except (ImproperlyConfigured, KeyError) as exc:
    raise ImproperlyConfigured(f"SECRET_KEY is required in production: {exc}") from exc

# Forced empty in production so dev backdoor is completely disabled
OTP_DEV_CODE = ""

# Security hardening
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)  # noqa: F405
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)  # noqa: F405
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)  # noqa: F405
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=True)  # noqa: F405
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Sane upload limits: 10 MB files + overhead
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int(  # noqa: F405
    "DATA_UPLOAD_MAX_MEMORY_SIZE", default=12 * 1024 * 1024
)
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int(  # noqa: F405
    "FILE_UPLOAD_MAX_MEMORY_SIZE", default=10 * 1024 * 1024
)

# CORS hardening: allow-all strictly disabled in production
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])  # noqa: F405
