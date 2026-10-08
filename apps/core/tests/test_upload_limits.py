"""Tests for file upload limits and validators."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import serializers, status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.core.validators import (
    MAX_DOCUMENT_SIZE_BYTES,
    MAX_IMAGE_SIZE_BYTES,
    validate_document_file,
    validate_image_file,
)
from apps.garage.models import VehicleKind
from apps.orders.models import Order
from apps.orders.tests.factories import OrderFactory


def generate_image_bytes(fmt: str = "PNG", size: tuple[int, int] = (10, 10)) -> bytes:
    """Generate in-memory valid image bytes using Pillow."""
    buffer = io.BytesIO()
    mode = "RGB" if fmt in ("JPEG", "PNG", "WEBP") else "RGB"
    img = Image.new(mode, size, color="blue")
    img.save(buffer, format=fmt)
    return buffer.getvalue()


def generate_pdf_bytes() -> bytes:
    """Generate minimal valid PDF bytes with correct header."""
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


# ---------------------------------------------------------------------------
# Unit tests for validate_image_file
# ---------------------------------------------------------------------------


def test_validate_image_file_valid_png():
    """Valid PNG passes validation."""
    content = generate_image_bytes(fmt="PNG")
    uploaded = SimpleUploadedFile("avatar.png", content, content_type="image/png")
    assert validate_image_file(uploaded) == uploaded


def test_validate_image_file_valid_jpeg():
    """Valid JPEG passes validation."""
    content = generate_image_bytes(fmt="JPEG")
    uploaded = SimpleUploadedFile("photo.jpg", content, content_type="image/jpeg")
    assert validate_image_file(uploaded) == uploaded


def test_validate_image_file_valid_webp():
    """Valid WEBP passes validation."""
    content = generate_image_bytes(fmt="WEBP")
    uploaded = SimpleUploadedFile("avatar.webp", content, content_type="image/webp")
    assert validate_image_file(uploaded) == uploaded


def test_validate_image_file_oversize():
    """Oversize image (> 5 MB) raises validation error."""
    large_data = b"x" * (MAX_IMAGE_SIZE_BYTES + 1024)
    uploaded = SimpleUploadedFile("big.png", large_data, content_type="image/png")
    with pytest.raises(serializers.ValidationError) as exc:
        validate_image_file(uploaded)
    assert "cannot exceed 5 MB" in str(exc.value)


def test_validate_image_file_unsupported_extension():
    """Image with unsupported extension (.bmp) raises validation error."""
    content = generate_image_bytes(fmt="PNG")
    uploaded = SimpleUploadedFile("image.bmp", content, content_type="image/bmp")
    with pytest.raises(serializers.ValidationError) as exc:
        validate_image_file(uploaded)
    assert "Unsupported image extension" in str(exc.value)


def test_validate_image_file_corrupted():
    """Image with corrupted content raises validation error."""
    corrupted_data = b"not a real png header content"
    uploaded = SimpleUploadedFile("broken.png", corrupted_data, content_type="image/png")
    with pytest.raises(serializers.ValidationError) as exc:
        validate_image_file(uploaded)
    assert "valid image" in str(exc.value).lower()


class MockUploadFile(io.BytesIO):
    def __init__(self, name: str, content: bytes, content_type: str = "image/png"):
        super().__init__(content)
        self.name = name
        self.size = len(content)
        self.content_type = content_type


def test_validate_image_file_path_traversal():
    """Image with path traversal characters raises validation error."""
    content = generate_image_bytes(fmt="PNG")
    for bad_name in ["../avatar.png", "..\\avatar.png", "sub/avatar.png", "avatar\x00.png"]:
        uploaded = MockUploadFile(bad_name, content, content_type="image/png")
        with pytest.raises(serializers.ValidationError) as exc:
            validate_image_file(uploaded)
        assert "Path traversal characters are not allowed" in str(exc.value)


# ---------------------------------------------------------------------------
# Unit tests for validate_document_file
# ---------------------------------------------------------------------------


def test_validate_document_file_valid_pdf():
    """Valid PDF bytes pass document validation."""
    content = generate_pdf_bytes()
    uploaded = SimpleUploadedFile("document.pdf", content, content_type="application/pdf")
    assert validate_document_file(uploaded) == uploaded


def test_validate_document_file_valid_text():
    """Valid text file passes document validation."""
    content = b"Some invoice notes."
    uploaded = SimpleUploadedFile("notes.txt", content, content_type="text/plain")
    assert validate_document_file(uploaded) == uploaded


def test_validate_document_file_oversize():
    """Oversize document (> 10 MB) raises validation error."""
    large_data = b"x" * (MAX_DOCUMENT_SIZE_BYTES + 1024)
    uploaded = SimpleUploadedFile("large.pdf", large_data, content_type="application/pdf")
    with pytest.raises(serializers.ValidationError) as exc:
        validate_document_file(uploaded)
    assert "cannot exceed 10 MB" in str(exc.value)


def test_validate_document_file_path_traversal():
    """Document with path traversal characters raises validation error."""
    content = generate_pdf_bytes()
    for bad_name in ["../doc.pdf", "..\\doc.pdf", "sub/doc.pdf", "doc\x00.pdf"]:
        uploaded = MockUploadFile(bad_name, content, content_type="application/pdf")
        with pytest.raises(serializers.ValidationError) as exc:
            validate_document_file(uploaded)
        assert "Path traversal characters are not allowed" in str(exc.value)


def test_validate_document_file_forbidden_executable():
    """Executables (.exe, .sh) are rejected."""
    sh_file = SimpleUploadedFile(
        "script.sh", b"#!/bin/sh\necho hi", content_type="application/x-sh"
    )
    with pytest.raises(serializers.ValidationError) as exc:
        validate_document_file(sh_file)
    assert "Executable files are not allowed" in str(exc.value)

    exe_file = SimpleUploadedFile("program.exe", b"MZ...", content_type="application/x-msdownload")
    with pytest.raises(serializers.ValidationError) as exc2:
        validate_document_file(exe_file)
    assert "Executable files are not allowed" in str(exc2.value)


def test_validate_document_file_unsupported_extension():
    """Document with unsupported extension (.zip) raises validation error."""
    uploaded = SimpleUploadedFile("archive.zip", b"PK...", content_type="application/zip")
    with pytest.raises(serializers.ValidationError) as exc:
        validate_document_file(uploaded)
    assert "Unsupported document extension" in str(exc.value)


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_patch_me_avatar_validation():
    """PATCH /me avatar field enforces size and type limits returning 400 validation_error."""
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=user)

    # 1. Valid avatar upload
    valid_content = generate_image_bytes(fmt="PNG")
    valid_file = SimpleUploadedFile("avatar.png", valid_content, content_type="image/png")
    resp_ok = client.patch("/api/v1/me", {"avatar": valid_file}, format="multipart")
    assert resp_ok.status_code == status.HTTP_200_OK

    # 2. Oversize avatar (> 5 MB) -> 400 validation_error
    oversize_data = b"x" * (MAX_IMAGE_SIZE_BYTES + 1024)
    big_file = SimpleUploadedFile("big_avatar.png", oversize_data, content_type="image/png")
    resp_oversize = client.patch("/api/v1/me", {"avatar": big_file}, format="multipart")
    assert resp_oversize.status_code == status.HTTP_400_BAD_REQUEST
    data_oversize = resp_oversize.json()
    assert data_oversize["code"] == "validation_error"

    # 3. Wrong type (.exe) -> 400 validation_error
    wrong_file = SimpleUploadedFile("avatar.exe", b"MZ...", content_type="application/x-msdownload")
    resp_wrong = client.patch("/api/v1/me", {"avatar": wrong_file}, format="multipart")
    assert resp_wrong.status_code == status.HTTP_400_BAD_REQUEST
    data_wrong = resp_wrong.json()
    assert data_wrong["code"] == "validation_error"


@pytest.mark.django_db
def test_vehicle_tech_passport_image_validation():
    """POST /vehicles tech_passport_image enforces limits returning 400 validation_error."""
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=user)

    # 1. Valid image upload
    valid_content = generate_image_bytes(fmt="JPEG")
    valid_file = SimpleUploadedFile("passport.jpg", valid_content, content_type="image/jpeg")
    resp_ok = client.post(
        "/api/v1/vehicles",
        {
            "kind": VehicleKind.TRACTOR,
            "plate_number": "01A777AA",
            "tech_passport_image": valid_file,
        },
        format="multipart",
    )
    assert resp_ok.status_code == status.HTTP_201_CREATED

    # 2. Corrupt / fake image -> 400 validation_error
    fake_file = SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg")
    resp_bad = client.post(
        "/api/v1/vehicles",
        {
            "kind": VehicleKind.TRAILER,
            "plate_number": "01A778AA",
            "tech_passport_image": fake_file,
        },
        format="multipart",
    )
    assert resp_bad.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_bad.json()["code"] == "validation_error"


@pytest.mark.django_db
def test_order_document_upload_validation():
    """POST /orders/{id}/documents validates document types returning 400 validation_error."""
    carrier = UserFactory()
    shipper = UserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    client = APIClient()
    client.force_authenticate(user=carrier)
    url = f"/api/v1/orders/{order.pk}/documents"

    # 1. Valid PDF upload -> 201
    pdf_content = generate_pdf_bytes()
    pdf_file = SimpleUploadedFile("cmr.pdf", pdf_content, content_type="application/pdf")
    resp_ok = client.post(
        url,
        {"name": "CMR Document", "file": pdf_file},
        format="multipart",
    )
    assert resp_ok.status_code == status.HTTP_201_CREATED

    # 2. Executable document upload -> 400 validation_error
    exe_file = SimpleUploadedFile("payload.exe", b"MZ...", content_type="application/x-msdownload")
    resp_exe = client.post(
        url,
        {"name": "Malicious doc", "file": exe_file},
        format="multipart",
    )
    assert resp_exe.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_exe.json()["code"] == "validation_error"

    # 3. Oversize document (> 10 MB) -> 400 validation_error
    oversize_data = b"x" * (MAX_DOCUMENT_SIZE_BYTES + 1024)
    huge_file = SimpleUploadedFile("huge.pdf", oversize_data, content_type="application/pdf")
    resp_huge = client.post(
        url,
        {"name": "Huge file", "file": huge_file},
        format="multipart",
    )
    assert resp_huge.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_huge.json()["code"] == "validation_error"
