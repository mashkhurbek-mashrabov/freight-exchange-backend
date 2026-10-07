# Freight Exchange Backend: Plan Coverage Audit

This document audits the implementation status of the Freight Exchange backend against the architecture and specifications defined in `plan.md` (Sections 4, 5, 6, and Phase 8.4).

---

## 1. Executive Summary

- **Total Concrete Models:** 20 (across all 8 project apps: `core`, `accounts`, `geo`, `garage`, `loads`, `offers`, `orders`, `notifications`). All 20 models are registered in Django admin with configured `list_display`, `list_filter`, and `search_fields`.
- **Section 5 Business Rules (Rules 1–15):** 15 / 15 Fully Implemented and verified with automated unit and integration tests.
- **Section 6 Endpoints:** 49 / 49 endpoints implemented, mounted in URL routing, documented in OpenAPI / Swagger schema via `drf-spectacular`, and covered by automated tests.
- **End-to-End Business Flow:** Validated via `apps/core/tests/test_e2e_business_flow.py` exercising complete HTTP REST flows (OTP auth, profile setup, admin verification, vehicle registration, load posting/publishing, offer/counter-offer negotiation, order state machine, completion, rating, and notifications).

---

## 2. Section 5: Business Rules Coverage (Rules 1–15)

| Rule # | Rule Name & Description | Implementing Function / Class | Test File & Test Name | Status | Notes |
|---|---|---|---|---|---|
| **1** | **Verification Gate**<br>Only users with `status=verified` may create offers, create loads, and change order status. Others receive `403` with `code: "account_not_verified"`. Browsing loads is allowed for any authenticated user. | - `apps.core.permissions.IsVerified`<br>- `apps.loads.services.create_load`<br>- `apps.offers.services.create_offer`<br>- `apps.offers.services.accept_offer`<br>- `apps.offers.services.reject_offer`<br>- `apps.offers.services.cancel_offer`<br>- `apps.offers.services.counter_offer`<br>- `apps.orders.services.transition_order_status` | - `apps/accounts/tests/test_permissions.py::test_is_verified_permission_denied_code`<br>- `apps/loads/tests/test_crud_views.py::test_create_load_unverified_403`<br>- `apps/offers/tests/test_services.py::test_create_offer_unverified_carrier_forbidden`<br>- `apps/offers/tests/test_views.py::test_create_offer_unverified_forbidden`<br>- `apps/orders/tests/test_services.py::test_unverified_user_cannot_transition_status`<br>- `apps/orders/tests/test_views.py::test_unverified_user_cannot_transition_order_status`<br>- `apps/core/tests/test_e2e_business_flow.py::test_unverified_user_blocked_with_account_not_verified` | **Full** | Enforced at both DRF view permission layer (`IsVerified`) and domain service layer (`ServiceError` with code `account_not_verified`). |
| **2** | **Role Gate**<br>Posting loads requires role `shipper|both`. Creating offers requires `carrier|both`. | - `apps.core.permissions.HasRole`<br>- `apps.loads.views.LoadListCreateView`<br>- `apps.loads.services.create_load`<br>- `apps.offers.views.LoadOfferCreateView`<br>- `apps.offers.services.create_offer` | - `apps/accounts/tests/test_permissions.py::test_has_role_rejects_disallowed_role`<br>- `apps/accounts/tests/test_permissions.py::test_has_role_allows_matching_and_both`<br>- `apps/loads/tests/test_services.py::test_create_load_role_validation`<br>- `apps/offers/tests/test_services.py::test_create_offer_carrier_or_both_role`<br>- `apps/offers/tests/test_views.py::test_create_offer_wrong_role_forbidden` | **Full** | `HasRole.of("shipper", "both")` on load view; `HasRole.of("carrier", "both")` on offer view; reinforced in service functions. |
| **3** | **Create Offer**<br>Load must be active. Carrier cannot offer on own load. If `mode=price_bid`, amount and currency are required. If `price_negotiable=false` and load has price, price_bid is rejected (`400`); only `comment_only` allowed. Duplicate pending offer returns `409`. Proposer=carrier, recipient=load.shipper. Notification sent to recipient. | - `apps.offers.services.create_offer`<br>- `apps.offers.views.LoadOfferCreateView` | - `apps/offers/tests/test_services.py::test_create_offer_price_bid_success`<br>- `apps/offers/tests/test_services.py::test_create_offer_comment_only_success`<br>- `apps/offers/tests/test_services.py::test_create_offer_on_own_load_forbidden`<br>- `apps/offers/tests/test_services.py::test_create_offer_inactive_load_conflict`<br>- `apps/offers/tests/test_services.py::test_create_offer_non_negotiable_price_bid_rejected`<br>- `apps/offers/tests/test_services.py::test_create_offer_duplicate_pending_conflict`<br>- `apps/offers/tests/test_views.py::test_create_offer_price_bid_success`<br>- `apps/core/tests/test_e2e_business_flow.py::test_full_business_flow_e2e_happy_path` | **Full** | Locks load via `select_for_update()`, checks non-negotiable prices, prevents self-bidding, sends `offer_received` notification. |
| **4** | **Accept Offer**<br>Only recipient, only if pending. Atomic with `select_for_update()` on load & offer: status=accepted, create Order + OrderStatusEvent(created). Load `trucks_found += 1`. If `trucks_found >= trucks_needed`, load becomes `in_progress` and other pending offers auto-rejected. Proposer notified. | - `apps.offers.services.accept_offer`<br>- `apps.offers.views.OfferAcceptView` | - `apps/offers/tests/test_services.py::test_accept_offer_single_truck_creates_order_and_sets_in_progress`<br>- `apps/offers/tests/test_services.py::test_accept_offer_multi_truck_partial_and_full_fill`<br>- `apps/offers/tests/test_services.py::test_accept_offer_non_recipient_forbidden`<br>- `apps/offers/tests/test_services.py::test_accept_offer_not_pending_conflict`<br>- `apps/offers/tests/test_services.py::test_concurrency_simultaneous_accepts_one_winner`<br>- `apps/offers/tests/test_views.py::test_accept_offer_success`<br>- `apps/core/tests/test_e2e_business_flow.py::test_two_truck_load_three_competing_carriers_auto_reject` | **Full** | Includes concurrency safety test with `select_for_update()`; handles multi-truck loads, auto-rejection, and notifications. |
| **5** | **Reject Offer**<br>Recipient only, if pending. Offer status `rejected`, `responded_at=now`. Notify proposer with `offer_rejected`. | - `apps.offers.services.reject_offer`<br>- `apps.offers.views.OfferRejectView` | - `apps/offers/tests/test_services.py::test_reject_offer_success`<br>- `apps/offers/tests/test_services.py::test_reject_offer_non_recipient_forbidden`<br>- `apps/offers/tests/test_views.py::test_reject_offer_success` | **Full** | Validates recipient ownership, pending state, records timestamp, dispatches notification. |
| **6** | **Cancel Offer**<br>Proposer only, if pending. Offer status `cancelled`. | - `apps.offers.services.cancel_offer`<br>- `apps.offers.views.OfferCancelView` | - `apps/offers/tests/test_services.py::test_cancel_offer_success`<br>- `apps/offers/tests/test_services.py::test_cancel_offer_non_proposer_forbidden`<br>- `apps/offers/tests/test_views.py::test_cancel_offer_success` | **Full** | Enforces proposer-only authorization and pending status prerequisite. |
| **7** | **Counter Offer**<br>Recipient only, if pending. Mark old offer `countered`; create new pending offer with `parent=old`, `proposer=old.recipient`, `recipient=old.proposer`, new amount/currency/comment, same carrier. Notify recipient. | - `apps.offers.services.counter_offer`<br>- `apps.offers.views.OfferCounterView` | - `apps/offers/tests/test_services.py::test_counter_offer_success`<br>- `apps/offers/tests/test_services.py::test_counter_offer_non_recipient_forbidden`<br>- `apps/offers/tests/test_views.py::test_counter_offer_success`<br>- `apps/core/tests/test_e2e_business_flow.py::test_full_business_flow_e2e_happy_path` | **Full** | Inverted parties (`proposer=old.recipient`), parent linkage, notification `offer_countered`. Proposer cannot accept own counter. |
| **8** | **Order Status Transitions**<br>Follows lifecycle state machine: `received`, `picked_up`, `delivered`, `awaiting_confirm` are carrier-only; `completed` is shipper-only; `cancelled` is either party (from `created` or `received`, requires note). Invalid transition returns `409 invalid_transition`. Writes `OrderStatusEvent` + notification. On cancel: `load.trucks_found -= 1`, load returns to `active`. When all orders complete, load becomes `completed`. | - `apps.orders.services.transition_order_status`<br>- `apps.orders.views.OrderStatusView` | - `apps/orders/tests/test_services.py::test_carrier_happy_path_transitions`<br>- `apps/orders/tests/test_services.py::test_shipper_completes_order_and_completes_load`<br>- `apps/orders/tests/test_services.py::test_cancel_order_decrements_trucks_and_restores_active_load`<br>- `apps/orders/tests/test_services.py::test_invalid_transition_returns_409`<br>- `apps/orders/tests/test_services.py::test_carrier_cannot_complete_order_403`<br>- `apps/orders/tests/test_views.py::test_carrier_transitions_order_status`<br>- `apps/core/tests/test_e2e_business_flow.py::test_full_business_flow_e2e_happy_path`<br>- `apps/core/tests/test_e2e_business_flow.py::test_order_cancellation_decrements_trucks_and_restores_load_active` | **Full** | Comprehensive role and state transition enforcement, cancellation trucks decrement, load auto-completion. |
| **9** | **Rating**<br>Only for `completed` orders, only by a party of the order, once per rater (`409` otherwise). Ratee is the other party. Recomputes `Company.rating_avg` and `rating_count` in the same transaction. | - `apps.orders.services.rate_order`<br>- `apps.orders.views.OrderRatingView` | - `apps/orders/tests/test_services.py::test_rate_order_updates_company_rating`<br>- `apps/orders/tests/test_services.py::test_rate_uncompleted_order_conflict`<br>- `apps/orders/tests/test_services.py::test_duplicate_rating_conflict`<br>- `apps/orders/tests/test_views.py::test_create_order_rating_success`<br>- `apps/core/tests/test_e2e_business_flow.py::test_full_business_flow_e2e_happy_path` | **Full** | Atomic computation of `rating_avg` and `rating_count` on target company. Enforces idempotency per user per order. |
| **10** | **Deals Lists**<br>`direction=outgoing` means `proposer = me`. `direction=incoming` means `recipient = me`. | - `apps.offers.filters.OfferFilter::filter_direction`<br>- `apps.offers.views.OfferListView` | - `apps/offers/tests/test_views.py::test_list_offers_filter_direction_outgoing`<br>- `apps/offers/tests/test_views.py::test_list_offers_filter_direction_incoming` | **Full** | Tested with both outgoing and incoming query parameter filters. |
| **11** | **Suitable Loads**<br>`?suitable=true`: Load `body_types` intersect the body types of caller's active vehicles (a load with no body types matches everything). | - `apps.loads.filters.LoadFilter::filter_suitable`<br>- `apps.loads.list_views.LoadListView` | - `apps/loads/tests/test_list_suitable.py::TestSuitableFilter::test_suitable_true_includes_matching_and_no_body_type_loads`<br>- `apps/loads/tests/test_list_suitable.py::TestSuitableFilter::test_suitable_false_excludes_matching_and_no_body_type_loads`<br>- `apps/loads/tests/test_list_suitable.py::TestSuitableFilter::test_suitable_only_considers_active_vehicles`<br>- `apps/loads/tests/test_list_suitable.py::TestSuitableFilter::test_carrier_with_no_vehicles_suitable_filter`<br>- `apps/core/tests/test_e2e_business_flow.py::test_full_business_flow_e2e_happy_path` | **Full** | Correctly includes open/universal loads (no required body types) and filters against caller's active vehicle inventory. |
| **12** | **Sorting**<br>`ordering` accepts `-published_at` (default), `distance_km`, `-price_amount`, and `price_per_km` (annotates `price_amount / NULLIF(distance_km, 0)`). | - `apps.loads.filters.LoadFilter`<br>- `apps.loads.list_views.LoadListView::get_queryset` | - `apps/loads/tests/test_list_ordering.py::TestLoadOrdering::test_ordering_published_at_default`<br>- `apps/loads/tests/test_list_ordering.py::TestLoadOrdering::test_ordering_distance_km`<br>- `apps/loads/tests/test_list_ordering.py::TestLoadOrdering::test_ordering_price_amount`<br>- `apps/loads/tests/test_list_ordering.py::TestLoadOrdering::test_ordering_price_per_km`<br>- `apps/loads/tests/test_list_ordering.py::TestLoadOrdering::test_ordering_price_per_km_with_null_and_zero_distance` | **Full** | Annotated `price_per_km` calculation safely handles NULL and zero distances with nulls last ordering. |
| **13** | **Distance**<br>If client sends `distance_km`, store it; else compute haversine distance between consecutive route points via `compute_distance_km`. | - `apps.loads.services.compute_distance_km`<br>- `apps.loads.services.create_load`<br>- `apps.loads.services.update_load` | - `apps/loads/tests/test_services.py::test_compute_distance_km`<br>- `apps/loads/tests/test_distance.py::test_haversine_distance_computation`<br>- `apps/loads/tests/test_crud_views.py::test_create_load_calculates_distance_when_omitted` | **Full** | Modular haversine distance implementation behind service interface ready for future external routing providers. |
| **14** | **Expiry**<br>Celery beat task every 10 min: active loads with `expires_at < now` become `expired`; pending offers auto-rejected. | - `apps.loads.tasks.expire_loads`<br>- `config.settings.base.CELERY_BEAT_SCHEDULE` | - `apps/loads/tests/test_tasks.py::test_expire_loads_updates_status_and_rejects_pending_offers` | **Full** | Celery beat scheduled task configured in `config/settings/base.py`, rejects pending offers and notifies carriers. |
| **15** | **OTP**<br>6 digits, hashed, TTL 5 min, max 5 attempts, max 3 requests per phone per 10 min (Redis counter). SMS via `ConsoleSmsBackend` / `SMS_BACKEND`. Dev mode accepts `OTP_DEV_CODE`. | - `apps.accounts.services.request_otp`<br>- `apps.accounts.services.verify_otp`<br>- `apps.accounts.sms.send_sms`<br>- `apps.accounts.sms.ConsoleSmsBackend` | - `apps/accounts/tests/test_otp_services.py::test_request_otp_happy_path`<br>- `apps/accounts/tests/test_otp_services.py::test_request_otp_rate_limit`<br>- `apps/accounts/tests/test_otp_services.py::test_verify_otp_happy_path`<br>- `apps/accounts/tests/test_otp_services.py::test_verify_otp_dev_code`<br>- `apps/accounts/tests/test_otp_services.py::test_verify_otp_max_attempts`<br>- `apps/accounts/tests/test_otp_services.py::test_verify_otp_expired`<br>- `apps/accounts/tests/test_sms.py::test_console_sms_backend`<br>- `apps/accounts/tests/test_auth_endpoints.py::test_otp_request_endpoint`<br>- `apps/accounts/tests/test_auth_endpoints.py::test_otp_verify_endpoint` | **Full** | Secure PBKDF2 code hashing, Redis request counter, attempt throttling, configurable pluggable SMS backends. |

---

## 3. Section 6: API Endpoints Audit

### 3.1 Auth and Profile

| Method | Path | View Class | Test File & Test Function | Status | Notes |
|---|---|---|---|---|---|
| POST | `/api/v1/auth/otp/request` | `apps.accounts.views.OtpRequestView` | `apps/accounts/tests/test_auth_endpoints.py::test_otp_request_endpoint` | **Full** | Returns HTTP 204 |
| POST | `/api/v1/auth/otp/verify` | `apps.accounts.views.OtpVerifyView` | `apps/accounts/tests/test_auth_endpoints.py::test_otp_verify_endpoint` | **Full** | Returns access, refresh, is_new, user |
| POST | `/api/v1/auth/token/refresh` | `apps.accounts.views.TokenRefreshCustomView` | `apps/accounts/tests/test_auth_endpoints.py::test_token_refresh_endpoint_success` | **Full** | SimpleJWT token refresh |
| POST | `/api/v1/auth/logout` | `apps.accounts.views.LogoutView` | `apps/accounts/tests/test_auth_endpoints.py::test_logout_endpoint_blacklists_refresh_token` | **Full** | Blacklists refresh token |
| GET | `/api/v1/me` | `apps.accounts.views.MeView` | `apps/accounts/tests/test_profile_endpoints.py::test_get_profile` | **Full** | Authenticated user profile |
| PATCH | `/api/v1/me` | `apps.accounts.views.MeView` | `apps/accounts/tests/test_profile_endpoints.py::test_patch_profile` | **Full** | Supports multipart avatar and role updates |
| PUT | `/api/v1/me/company` | `apps.accounts.views.MeCompanyView` | `apps/accounts/tests/test_profile_endpoints.py::test_upsert_company` | **Full** | Upserts company profile |
| POST | `/api/v1/me/devices` | `apps.accounts.views.MeDeviceView` | `apps/accounts/tests/test_profile_endpoints.py::test_register_device` | **Full** | Registers FCM push token |
| DELETE | `/api/v1/me/devices/{token}` | `apps.accounts.views.MeDeviceDeleteView` | `apps/accounts/tests/test_profile_endpoints.py::test_delete_device` | **Full** | Removes device token |

### 3.2 Reference Data

| Method | Path | View Class | Test File & Test Function | Status | Notes |
|---|---|---|---|---|---|
| GET | `/api/v1/countries` | `apps.geo.views.CountryListView` | `apps/geo/tests/test_views.py::test_country_list_endpoint` | **Full** | Cached, multilingual names, flag URL |
| GET | `/api/v1/currencies` | `apps.geo.views.CurrencyListView` | `apps/geo/tests/test_views.py::test_currency_list_endpoint` | **Full** | Cached reference data |
| GET | `/api/v1/vehicle-types` | `apps.garage.views.VehicleTypeListView` | `apps/garage/tests/test_views.py::test_vehicle_type_list_endpoint` | **Full** | Filterable by `?kind=tractor\|trailer` |
| GET | `/api/v1/exchange-rates` | `apps.geo.views.ExchangeRateListView` | `apps/geo/tests/test_views.py::test_exchange_rate_list_endpoint` | **Full** | Base and quote currencies |

### 3.3 Garage

| Method | Path | View Class | Test File & Test Function | Status | Notes |
|---|---|---|---|---|---|
| GET | `/api/v1/vehicles` | `apps.garage.views.VehicleListCreateView` | `apps/garage/tests/test_views.py::test_vehicle_list_scoping_and_filter` | **Full** | Owner-scoped, `?kind=` filter |
| POST | `/api/v1/vehicles` | `apps.garage.views.VehicleListCreateView` | `apps/garage/tests/test_views.py::test_create_vehicle_happy_path_and_pairing` | **Full** | Validates tractor/trailer pairing |
| GET | `/api/v1/vehicles/{id}` | `apps.garage.views.VehicleDetailView` | `apps/garage/tests/test_views.py::test_vehicle_detail_endpoint` | **Full** | Owner-scoped retrieval |
| PATCH | `/api/v1/vehicles/{id}` | `apps.garage.views.VehicleDetailView` | `apps/garage/tests/test_views.py::test_vehicle_patch_endpoint` | **Full** | Partial vehicle updates |
| DELETE | `/api/v1/vehicles/{id}` | `apps.garage.views.VehicleDetailView` | `apps/garage/tests/test_views.py::test_vehicle_soft_delete` | **Full** | Soft delete via `is_active=false` |

### 3.4 Loads

| Method | Path | View Class | Test File & Test Function | Status | Notes |
|---|---|---|---|---|---|
| GET | `/api/v1/loads` | `apps.loads.list_views.LoadListView` | `apps/loads/tests/test_list_views.py::test_loads_list_structure` | **Full** | Supports all filters, suitable, ordering |
| POST | `/api/v1/loads` | `apps.loads.root_views.LoadListCreateView` | `apps/loads/tests/test_crud_views.py::test_create_load_happy_path` | **Full** | Nested route points, payment terms |
| GET | `/api/v1/loads/{id}` | `apps.loads.views.LoadDetailView` | `apps/loads/tests/test_crud_views.py::test_get_load_detail` | **Full** | Includes points, terms, docs, my_offer |
| PATCH | `/api/v1/loads/{id}` | `apps.loads.views.LoadDetailView` | `apps/loads/tests/test_crud_views.py::test_patch_load_detail` | **Full** | Owner only, draft or active only |
| POST | `/api/v1/loads/{id}/publish` | `apps.loads.views.LoadPublishView` | `apps/loads/tests/test_crud_views.py::test_publish_load` | **Full** | Sets `status=active`, `published_at` |
| POST | `/api/v1/loads/{id}/cancel` | `apps.loads.views.LoadCancelView` | `apps/loads/tests/test_crud_views.py::test_cancel_load` | **Full** | Shipper cancel |
| GET | `/api/v1/loads/mine` | `apps.loads.list_views.LoadMineView` | `apps/loads/tests/test_list_mine.py::test_load_mine_returns_owner_loads` | **Full** | Shipper's own loads in any status |
| POST | `/api/v1/loads/{id}/favorite` | `apps.loads.views.LoadFavoriteView` | `apps/loads/tests/test_crud_views.py::test_post_load_favorite` | **Full** | Idempotent bookmark |
| DELETE | `/api/v1/loads/{id}/favorite` | `apps.loads.views.LoadFavoriteView` | `apps/loads/tests/test_crud_views.py::test_delete_load_favorite` | **Full** | Idempotent unbookmark |
| GET | `/api/v1/me/favorites` | `apps.loads.list_views.MyFavoritesView` | `apps/loads/tests/test_list_favorites.py::test_favorites_returns_user_bookmarks_newest_first` | **Full** | User's bookmarked loads list |
| GET | `/api/v1/loads/map` | `apps.loads.list_views.LoadMapView` | `apps/loads/tests/test_list_map.py::test_load_map_bounding_box_filter` | **Full** | Filterable by `?bbox=minLng,minLat,maxLng,maxLat` |

### 3.5 Offers

| Method | Path | View Class | Test File & Test Function | Status | Notes |
|---|---|---|---|---|---|
| POST | `/api/v1/loads/{id}/offers` | `apps.offers.views.LoadOfferCreateView` | `apps/offers/tests/test_views.py::test_create_offer_price_bid_success` | **Full** | Price bid or comment only |
| GET | `/api/v1/offers` | `apps.offers.views.OfferListView` | `apps/offers/tests/test_views.py::test_list_offers_filter_direction_outgoing` | **Full** | `?direction=outgoing\|incoming&status=` |
| GET | `/api/v1/offers/{id}` | `apps.offers.views.OfferDetailView` | `apps/offers/tests/test_views.py::test_get_offer_detail_success` | **Full** | Detailed view for parties |
| POST | `/api/v1/offers/{id}/accept` | `apps.offers.views.OfferAcceptView` | `apps/offers/tests/test_views.py::test_accept_offer_success` | **Full** | Recipient only, creates Order |
| POST | `/api/v1/offers/{id}/reject` | `apps.offers.views.OfferRejectView` | `apps/offers/tests/test_views.py::test_reject_offer_success` | **Full** | Recipient only |
| POST | `/api/v1/offers/{id}/cancel` | `apps.offers.views.OfferCancelView` | `apps/offers/tests/test_views.py::test_cancel_offer_success` | **Full** | Proposer only |
| POST | `/api/v1/offers/{id}/counter` | `apps.offers.views.OfferCounterView` | `apps/offers/tests/test_views.py::test_counter_offer_success` | **Full** | Recipient only, creates new offer |

### 3.6 Orders

| Method | Path | View Class | Test File & Test Function | Status | Notes |
|---|---|---|---|---|---|
| GET | `/api/v1/orders` | `apps.orders.views.OrderListView` | `apps/orders/tests/test_views.py::test_order_list_active_tab` | **Full** | `?tab=active\|history` |
| GET | `/api/v1/orders/{id}` | `apps.orders.views.OrderDetailView` | `apps/orders/tests/test_views.py::test_order_detail_view` | **Full** | Includes route points, events, docs |
| POST | `/api/v1/orders/{id}/status` | `apps.orders.views.OrderStatusView` | `apps/orders/tests/test_views.py::test_carrier_transitions_order_status` | **Full** | Enforces role matrix and notes |
| POST | `/api/v1/orders/{id}/documents` | `apps.orders.views.OrderDocumentUploadView` | `apps/orders/tests/test_views.py::test_upload_order_document` | **Full** | Multipart file upload |
| POST | `/api/v1/orders/{id}/rating` | `apps.orders.views.OrderRatingView` | `apps/orders/tests/test_views.py::test_create_order_rating_success` | **Full** | Completed order rating (1-5 stars) |

### 3.7 Notifications

| Method | Path | View Class | Test File & Test Function | Status | Notes |
|---|---|---|---|---|---|
| GET | `/api/v1/notifications` | `apps.notifications.views.NotificationListView` | `apps/notifications/tests/test_views.py::test_notification_list_with_unread_count` | **Full** | Includes top-level `unread_count` |
| POST | `/api/v1/notifications/{id}/read` | `apps.notifications.views.NotificationReadView` | `apps/notifications/tests/test_views.py::test_notification_read_endpoint` | **Full** | Marks single notification as read |
| POST | `/api/v1/notifications/read-all` | `apps.notifications.views.NotificationReadAllView` | `apps/notifications/tests/test_views.py::test_notification_read_all_endpoint` | **Full** | Marks all user notifications read |

### 3.8 Service Endpoints

| Method | Path | View Class | Test File & Test Function | Status | Notes |
|---|---|---|---|---|---|
| GET | `/health/` | `apps.core.views.HealthCheckView` | `apps/core/tests/test_health.py::test_health_check_returns_200` | **Full** | Health probe checking DB connectivity |
| ALL | `/admin/` | `django.contrib.admin.site.urls` | `apps/core/tests/test_admin_coverage.py::test_admin_changelist_smoke_tests` | **Full** | Django admin with 100% changelist coverage |
| GET | `/api/schema/` | `drf_spectacular.views.SpectacularAPIView` | `apps/core/tests/test_docs.py::test_schema_returns_200` | **Full** | OpenAPI schema JSON |
| GET | `/api/docs/` | `drf_spectacular.views.SpectacularSwaggerView` | `apps/core/tests/test_docs.py::test_docs_returns_200` | **Full** | Swagger UI with Bearer auth support |
| GET | `/api/redoc/` | `drf_spectacular.views.SpectacularRedocView` | `apps/core/tests/test_docs.py::test_redoc_returns_200` | **Full** | ReDoc interactive documentation |

---

## 4. Section 4: Project Models & Admin Audit

Every project model in the 8 project apps is registered with Django Admin, with meaningful `list_display`, `list_filter`, and `search_fields` configurations, and passes automated changelist smoke tests:

| App | Model | Admin Registration | `list_display` | `list_filter` | `search_fields` |
|---|---|---|---|---|---|
| **accounts** | `User` | Registered (`UserAdmin`) | phone, full_name, role, status, is_active | status, role, language | phone, full_name |
| **accounts** | `Company` | Registered (`CompanyAdmin`) | name, owner, tin, rating_avg, rating_count, verified_at | rating_avg | name, tin, owner__phone |
| **accounts** | `Device` | Registered (`DeviceAdmin`) | user, platform, fcm_token, last_seen_at | platform | fcm_token, user__phone |
| **accounts** | `OtpCode` | Registered (`OtpCodeAdmin`) | phone, attempts, expires_at, used_at, created_at | attempts, used_at | phone |
| **geo** | `Country` | Registered (`CountryAdmin`) | code, name_en, name_ru, name_uz, flag_url | HasFlagFilter | code |
| **geo** | `Currency` | Registered (`CurrencyAdmin`) | code, name | code | code, name |
| **geo** | `ExchangeRate` | Registered (`ExchangeRateAdmin`) | base, quote, rate, fetched_at | base, quote | base__code, quote__code |
| **garage** | `VehicleType` | Registered (`VehicleTypeAdmin`) | id, code, kind, image_url | kind | code, name_i18n |
| **garage** | `Vehicle` | Registered (`VehicleAdmin`) | id, plate_number, kind, owner, vehicle_type, paired_vehicle, is_active, created_at | kind, is_active, vehicle_type | plate_number, brand, owner_full_name, owner__phone, tech_passport_no |
| **loads** | `Load` | Registered (`LoadAdmin`) | id, cargo_description, shipper, status, transport_mode, trucks_needed, trucks_found, price_amount, currency, published_at | status, transport_mode, is_adr, temp_controlled, currency, created_at | cargo_description, cargo_type, shipper__phone, shipper__full_name |
| **loads** | `RoutePoint` | Registered (`RoutePointAdmin`) | id, load, seq, kind, country, address, asap, ready_to_load | kind, country, asap, ready_to_load | address, comment, load__cargo_description |
| **loads** | `PaymentTerms` | Registered (`PaymentTermsAdmin`) | load, prepay_amount, prepay_method, paid_amount, paid_method, payment_due_days | prepay_method, paid_method | load__cargo_description, conditions |
| **loads** | `LoadDocument` | Registered (`LoadDocumentAdmin`) | id, load, name, created_at | created_at | name, load__cargo_description |
| **loads** | `Favorite` | Registered (`FavoriteAdmin`) | id, user, load, created_at | created_at | user__phone, load__cargo_description |
| **offers** | `Offer` | Registered (`OfferAdmin`) | id, load, carrier, proposer, recipient, mode, amount, currency, status, created_at, responded_at | status, mode, currency, created_at | load__cargo_description, carrier__phone, proposer__phone, recipient__phone, comment |
| **orders** | `Order` | Registered (`OrderAdmin`) | id, load, shipper, carrier, status, agreed_amount, currency, created_at, completed_at | status, currency, created_at | id, load__cargo_description, shipper__phone, shipper__full_name, carrier__phone, carrier__full_name |
| **orders** | `OrderStatusEvent` | Registered (`OrderStatusEventAdmin`) | id, order, status, actor, at | status, at | order__id, actor__phone, note |
| **orders** | `OrderDocument` | Registered (`OrderDocumentAdmin`) | id, order, name, size_kb, uploaded_by, created_at | created_at | name, order__id, uploaded_by__phone |
| **orders** | `Rating` | Registered (`RatingAdmin`) | id, order, rater, ratee, stars, created_at | stars, created_at | order__id, rater__phone, ratee__phone, comment |
| **notifications** | `Notification` | Registered (`NotificationAdmin`) | id, user, type, read_at, created_at | type, read_at, created_at | user__phone |

---

## 5. Identified Gaps & Deferred Items (Honest Audit)

The following items from the overarching roadmap (`plan.md`) are outside the immediate scope of Phase 8.4 or planned for subsequent delivery:

1. **Phase 8.1 Demo Seeding Command (`seed_demo`):**
   - *Status:* Deferred / Pending Phase 8.1.
   - *Detail:* A custom management command `python manage.py seed_demo` to generate mock data (~30 loads, multi-point routes) is planned in Phase 8 item 1. Fixtures for reference data (`countries`, `currencies`, `vehicle_types`) are present and functional.

2. **Phase 8.2 Global DRF Throttles:**
   - *Status:* Deferred / Pending Phase 8.2.
   - *Detail:* DRF `DEFAULT_THROTTLE_CLASSES` (`AnonRateThrottle` at 60/min, `UserRateThrottle` at 600/min) are not yet activated in `config/settings/base.py`. Phone-level OTP request throttling (max 3 requests per 10 minutes) is implemented and active via Django cache in `apps/accounts/services.py::request_otp`.

3. **Phase 7 Push Notification Delivery:**
   - *Status:* Logging stub by design.
   - *Detail:* The Celery task `apps/notifications/tasks.py::send_push` is an intentional stub that logs dispatches (`push to user %s type %s`), with actual FCM network push integration deferred as specified in `plan.md` ("stub that logs; wired for FCM later").
