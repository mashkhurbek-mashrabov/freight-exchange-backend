"""File upload validators for images and documents."""

from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".txt",
}

ALLOWED_DOCUMENT_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
}

FORBIDDEN_EXECUTABLE_EXTENSIONS = {
    ".exe",
    ".bat",
    ".cmd",
    ".sh",
    ".bin",
    ".msi",
    ".js",
    ".py",
    ".com",
    ".vbs",
    ".scr",
    ".jar",
    ".app",
    ".dmg",
    ".elf",
}

FORBIDDEN_EXECUTABLE_CONTENT_TYPES = {
    "application/x-msdownload",
    "application/x-executable",
    "application/x-sh",
    "application/x-shellscript",
    "application/javascript",
    "application/x-javascript",
    "application/x-bat",
}


def validate_image_file(f: Any) -> Any:
    """Validate uploaded image file size (max 5 MB), extension, content-type, and integrity."""
    if f is None:
        return f

    file_name = getattr(f, "name", "") or ""
    if not file_name:
        raise serializers.ValidationError("Image file must have a valid name.")

    ext = Path(file_name).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise serializers.ValidationError(
            f"Unsupported image extension '{ext}'. Allowed extensions: jpg, jpeg, png, webp."
        )

    content_type = getattr(f, "content_type", None)
    if content_type:
        content_type_lower = content_type.lower()
        if content_type_lower not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise serializers.ValidationError(
                f"Unsupported image content type '{content_type}'. Allowed types: "
                "image/jpeg, image/png, image/webp."
            )

    size = getattr(f, "size", 0)
    if size > MAX_IMAGE_SIZE_BYTES:
        raise serializers.ValidationError(
            f"Image file size cannot exceed 5 MB (current size: {size / (1024 * 1024):.2f} MB)."
        )

    try:
        if hasattr(f, "seek"):
            f.seek(0)
        img = Image.open(f)
        img.verify()
        if img.format not in ALLOWED_IMAGE_FORMATS:
            raise serializers.ValidationError(
                f"Unsupported image format '{img.format}'. Allowed formats: JPEG, PNG, WEBP."
            )
    except serializers.ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise serializers.ValidationError(
            f"Upload a valid image. The file could not be decoded: {exc}."
        ) from exc
    finally:
        if hasattr(f, "seek"):
            f.seek(0)

    return f


def validate_document_file(f: Any) -> Any:
    """Validate uploaded document file size (max 10 MB), allowed types, and safety."""
    if f is None:
        raise serializers.ValidationError("File is required.")

    file_name = getattr(f, "name", "") or ""
    if not file_name:
        raise serializers.ValidationError("Document file must have a valid name.")

    ext = Path(file_name).suffix.lower()
    content_type = getattr(f, "content_type", None)
    content_type_lower = content_type.lower() if content_type else None

    if ext in FORBIDDEN_EXECUTABLE_EXTENSIONS or (
        content_type_lower and content_type_lower in FORBIDDEN_EXECUTABLE_CONTENT_TYPES
    ):
        raise serializers.ValidationError("Executable files are not allowed.")

    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise serializers.ValidationError(
            f"Unsupported document extension '{ext}'. Allowed extensions: "
            f"{', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}."
        )

    if content_type_lower and content_type_lower not in ALLOWED_DOCUMENT_CONTENT_TYPES:
        raise serializers.ValidationError(
            f"Unsupported document content type '{content_type}'."
        )

    size = getattr(f, "size", 0)
    if size > MAX_DOCUMENT_SIZE_BYTES:
        raise serializers.ValidationError(
            f"Document file size cannot exceed 10 MB (current size: {size / (1024 * 1024):.2f} MB)."
        )

    if ext in ALLOWED_IMAGE_EXTENSIONS:
        try:
            if hasattr(f, "seek"):
                f.seek(0)
            img = Image.open(f)
            img.verify()
        except Exception as exc:
            raise serializers.ValidationError(
                f"Invalid image document: {exc}."
            ) from exc
        finally:
            if hasattr(f, "seek"):
                f.seek(0)
    return f
