"""Development settings."""

from .base import *  # noqa: F403

DEBUG = env.bool("DEBUG", default=True)  # noqa: F405
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])  # noqa: F405
CORS_ALLOW_ALL_ORIGINS = True
OTP_DEV_CODE = env("OTP_DEV_CODE", default="000000")  # noqa: F405
