# Security, Authorization, and Money Correctness Review

**Reviewer:** Farrux (Antigravity Security & Correctness Audit)  
**Date:** October 8, 2026  
**Target:** Freight Exchange Django Backend (`fx-wt-farrux`, branch `ag/farrux`)

---

## 1. Executive Summary

This review audited the Freight Exchange platform backend against security, authorization, and financial correctness requirements specified in the project architecture plan (sections 5 and 6) and core production standards.

All identified vulnerabilities and correctness gaps were patched with minimal, surgical diffs, validated with dedicated regression tests, and confirmed against the complete ~330-test suite with zero regressions.

---

## 2. Findings, Actions & Decisions

### 2.1 Authentication & OTP Security

| Finding ID | Severity | Status | Description & Remediation |
|---|---|---|---|
| **AUTH-01** | High | **FIXED** | **Inactive users could verify OTP & blocked/inactive users could refresh tokens.** In `apps/accounts/services.py`, `verify_otp` only checked for existing users without verifying `user.is_active`. Furthermore, SimpleJWT's default refresh serializer only validated user existence and token validity, allowing blocked and deactivated users to continuously obtain fresh access tokens. Patched `verify_otp` to reject inactive accounts, implemented `CustomTokenRefreshSerializer` checking `is_active` and `status != 'blocked'` before rotation, and added tests. |
| **AUTH-02** | Critical | **FIXED** | **Blocked users could make authenticated requests using valid JWTs.** SimpleJWT 5.5.1 does not execute `USER_AUTHENTICATION_RULE` during standard Bearer request decoding. Subclassed `JWTAuthentication` with `CustomJWTAuthentication` in `apps/accounts/authentication.py`, configured it as the primary authenticator, and registered `CustomJWTScheme` with `drf-spectacular` OpenAPI schema generation. |
| **AUTH-03** | High | **FIXED** | **Race conditions in OTP rate limiting and attempt counting.** `check_and_increment_otp_rate_limit` used non-atomic check-then-set cache operations. Replaced with atomic `cache.add` + `cache.incr`. In `verify_otp`, attempt counter increments were wrapped in `select_for_update()` under an isolated transaction savepoint so failed verification attempts cannot be lost via service rollbacks. |
| **AUTH-04** | Low | **ACCEPTED-RISK** | **`OTP_DEV_CODE` exists in dev settings.** The dev code (`000000`) allows headless Swagger/E2E testing without external SMS provider costs. In `config/settings/prod.py`, `OTP_DEV_CODE = ""` is strictly enforced, and `config/settings/base.py` defaults to empty string, preventing any production bypass. |

---

### 2.2 Authorization & Access Control (IDOR)

| Finding ID | Severity | Status | Description & Remediation |
|---|---|---|---|
| **AUTHZ-01** | Medium | **FIXED** | **Draft load IDOR via favorite endpoints.** `LoadFavoriteView` allowed users to add or remove arbitrary loads from favorites without checking draft status ownership, leaking existence and metadata of private draft loads belonging to other shippers. Patched `LoadFavoriteView` to return `404 Not Found` for unowned draft loads, and added regression tests. |
| **AUTHZ-02** | High | **FIXED** | **Unverified shippers could publish loads.** Per business rule 1, only verified users may publish loads. `LoadPublishView` was configured with `IsAuthenticated` instead of `IsVerified`, and `publish_load` service did not verify user status. Added `IsVerified` permission class and `account_not_verified` check in `publish_load`. |
| **AUTHZ-03** | Low | **VERIFIED (SECURE)** | **Vehicle ownership and pairing scoping.** `VehicleDetailView` restricts queries to `owner=request.user, is_active=True`. `create_vehicle` and `update_vehicle` strictly validate that `paired_vehicle` belongs to the authenticated owner and has the opposite kind (`tractor` vs `trailer`). |
| **AUTHZ-04** | Low | **VERIFIED (SECURE)** | **Order and document access control.** `OrderDetailView`, `OrderStatusView`, and `OrderDocumentUploadView` enforce party check (`request.user.pk in (order.carrier_id, order.shipper_id)`), returning 404 to unauthorized users. `change_status` strictly enforces the state machine role matrix. |
| **AUTHZ-05** | Low | **VERIFIED (SECURE)** | **Notifications scoping.** `NotificationListView` and `mark_read` filter strictly on `user=request.user`, preventing cross-account notification access. |
| **AUTHZ-06** | Low | **VERIFIED (SECURE)** | **Device token reassignment.** When registering an FCM token via `register_device`, the token is atomically reassigned to `user=request.user`, ensuring that devices switching accounts do not receive notifications intended for prior users. Deletion is strictly scoped to `user=request.user`. |
| **AUTHZ-07** | Low | **VERIFIED (SECURE)** | **Counterparty privacy prior to offer acceptance.** `OfferPartySerializer` explicitly suppresses counterparty phone numbers until the offer status transitions to `accepted`. |
| **AUTHZ-08** | Low | **VERIFIED (SECURE)** | **Mass-assignment protection.** Write serializers for users, vehicles, loads, and offers explicitly omit sensitive fields (`status`, `is_active`, `rating_avg`, `rating_count`, `shipper`, `carrier`, `trucks_found`). Model instances are constructed with authoritative values from context. |

---

### 2.3 Financial & Money Correctness

| Finding ID | Severity | Status | Description & Remediation |
|---|---|---|---|
| **MONEY-01** | High | **FIXED** | **Zero and negative amounts accepted in loads and payment terms.** `LoadWriteSerializer` and `apps/loads/services.py` allowed non-positive `price_amount` and negative payment terms amounts (`prepay_amount`, `paid_amount`, `remaining_amount`). Added `min_value=Decimal("0.01")` for load price and `min_value=Decimal("0.00")` for payment terms, enforced in both serializer and domain service layer. |
| **MONEY-02** | High | **FIXED** | **Zero and negative amounts accepted in offers and counter-offers.** `OfferCreateSerializer` and `CounterOfferSerializer` did not specify `min_value`, and services did not reject non-positive amounts. Added `min_value=Decimal("0.01")` and service validation rejecting `amount <= 0` with code `validation_error`. |
| **MONEY-03** | Medium | **FIXED** | **Currency mismatch between load and offer.** If a load was priced in USD, a carrier could submit a price bid in EUR or UZS, creating order amount discrepancy upon acceptance. Added validation in `create_offer` and `counter_offer`: if `load.currency` is set and does not match `offer.currency`, the request is rejected with `400 Bad Request` and `code="currency_mismatch"`. |
| **MONEY-04** | Low | **VERIFIED (SECURE)** | **Absence of floating-point arithmetic for currency.** Codebase grep confirmed `float()` is exclusively used in `apps/loads/distance.py` for spherical Haversine trigonometric functions. All currency, pricing, and fee calculations utilize `Decimal` and Django `DecimalField(max_digits=18, decimal_places=2)`. |
| **MONEY-05** | Low | **VERIFIED (SECURE)** | **Rating averaging and price_per_km calculations.** Rating averaging in `apps/orders/services.py` uses `quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`. `price_per_km` query annotation uses `F("price_amount") / NullIf(F("distance_km"), 0)` with `DecimalField` output and nulls-last ordering. |

---

### 2.4 File Uploads & Traversal Protection

| Finding ID | Severity | Status | Description & Remediation |
|---|---|---|---|
| **UPLOAD-01** | Medium | **FIXED** | **Path traversal characters in uploaded file names.** While Django's `UploadedFile` derives `os.path.basename`, custom upload handling or raw filenames could potentially allow path traversal characters (`..`, `/`, `\\`, `\x00`). Added explicit path traversal checks in `validate_image_file` and `validate_document_file` in `apps/core/validators.py`. |
| **UPLOAD-02** | Low | **VERIFIED (SECURE)** | **Safe media serving in production.** `config/urls.py` does not serve media via `django.views.static.serve`. Production settings set `DEBUG = False`, enforce request size limits (`10MB` file upload, `12MB` request body), and require external secure storage/reverse proxy for static and media assets. |

---

### 2.5 Error Handling & Information Leakage

| Finding ID | Severity | Status | Description & Remediation |
|---|---|---|---|
| **ERR-01** | Medium | **FIXED** | **Unhandled database exceptions leaking schema details.** Raw `IntegrityError` or `DatabaseError` exceptions escaping DRF views could expose SQL queries, table names, and constraint names in dev or unformatted 500 HTML in prod. Updated `apps/core/exceptions.py` to intercept `IntegrityError` (returning 409 `conflict`) and `DatabaseError` (returning 500 `database_error`) with sanitized JSON payloads. |
| **ERR-02** | Low | **VERIFIED (SECURE)** | **`DEBUG` defaults.** `config/settings/base.py` defaults `DEBUG` to `False` (`env.bool("DEBUG", default=False)`), and `config/settings/prod.py` hardcodes `DEBUG = False`. |

---

## 3. Test Suite Verification

All fixes include targeted regression tests. Full test suite execution status:

- **Total Tests Passing:** 333 / 333 (100%)
- **Django System Check:** 0 issues (`python manage.py check`)
- **Model Migrations Check:** 0 pending migrations (`python manage.py makemigrations --check`)
- **Spectacular OpenAPI Validation:** Valid schema with 0 warnings (`python manage.py spectacular --validate --fail-on-warn`)
- **Linter (Ruff):** 0 errors / 0 warnings (`ruff check .`)
