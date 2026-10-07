"""Tests for Rule 11: suitable loads filter."""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import CarrierUserFactory
from apps.garage.models import VehicleKind
from apps.garage.tests.factories import VehicleFactory, VehicleTypeFactory
from apps.loads.tests.helpers_list import create_carrier_with_vehicle, create_test_load


@pytest.mark.django_db
@pytest.mark.urls("apps.loads.tests.urls_list_only")
class TestLoadListSuitable:
    """Test suite for ?suitable=true/false and no-body-types load rule."""

    def test_suitable_true_includes_matching_and_no_body_type_loads(self) -> None:
        vt_reefer = VehicleTypeFactory(code="reefer_suit", kind=VehicleKind.TRAILER)
        vt_tent = VehicleTypeFactory(code="tent_suit", kind=VehicleKind.TRAILER)

        carrier, _ = create_carrier_with_vehicle(vehicle_type=vt_reefer, is_active=True)
        client = APIClient()
        client.force_authenticate(user=carrier)

        # 1. Matching load
        load_matching = create_test_load(
            cargo_description="Frozen meat",
            body_types=[vt_reefer],
        )
        # 2. Non-matching load
        load_other = create_test_load(
            cargo_description="Dry construction materials",
            body_types=[vt_tent],
        )
        # 3. Load with NO body types (matches everything)
        load_universal = create_test_load(
            cargo_description="General freight any truck",
            body_types=[],
        )

        resp = client.get("/api/v1/loads?suitable=true")
        assert resp.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp.data["results"]]

        assert load_matching.id in ids
        assert load_universal.id in ids
        assert load_other.id not in ids

    def test_suitable_false_excludes_matching_and_no_body_type_loads(self) -> None:
        vt_reefer = VehicleTypeFactory(code="reefer_suit2", kind=VehicleKind.TRAILER)
        vt_tent = VehicleTypeFactory(code="tent_suit2", kind=VehicleKind.TRAILER)

        carrier, _ = create_carrier_with_vehicle(vehicle_type=vt_reefer, is_active=True)
        client = APIClient()
        client.force_authenticate(user=carrier)

        load_matching = create_test_load(
            cargo_description="Dairy products",
            body_types=[vt_reefer],
        )
        load_other = create_test_load(
            cargo_description="Cereals in bulk",
            body_types=[vt_tent],
        )
        load_universal = create_test_load(
            cargo_description="Universal cargo",
            body_types=[],
        )

        resp = client.get("/api/v1/loads?suitable=false")
        assert resp.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp.data["results"]]

        # Unsuitable loads are loads that require body types the carrier does NOT have
        assert load_other.id in ids
        assert load_matching.id not in ids
        # Universal load (no body types) matches everything, so it is never unsuitable
        assert load_universal.id not in ids

    def test_suitable_only_considers_active_vehicles(self) -> None:
        vt_tent = VehicleTypeFactory(code="tent_act", kind=VehicleKind.TRAILER)
        vt_board = VehicleTypeFactory(code="board_act", kind=VehicleKind.TRAILER)

        carrier = CarrierUserFactory()
        # Inactive vehicle with tent
        VehicleFactory(owner=carrier, vehicle_type=vt_tent, kind=vt_tent.kind, is_active=False)
        # Active vehicle with board
        VehicleFactory(owner=carrier, vehicle_type=vt_board, kind=vt_board.kind, is_active=True)

        client = APIClient()
        client.force_authenticate(user=carrier)

        load_tent = create_test_load(body_types=[vt_tent])
        load_board = create_test_load(body_types=[vt_board])

        resp = client.get("/api/v1/loads?suitable=true")
        assert resp.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp.data["results"]]

        assert load_board.id in ids
        assert load_tent.id not in ids

    def test_carrier_with_no_vehicles_suitable_filter(self) -> None:
        carrier_empty = CarrierUserFactory()
        client = APIClient()
        client.force_authenticate(user=carrier_empty)

        vt = VehicleTypeFactory(code="tanker_empty", kind=VehicleKind.TRAILER)
        load_specific = create_test_load(body_types=[vt])
        load_universal = create_test_load(body_types=[])

        # suitable=true: only universal load matches
        resp_true = client.get("/api/v1/loads?suitable=true")
        assert resp_true.status_code == status.HTTP_200_OK
        ids_true = [item["id"] for item in resp_true.data["results"]]
        assert load_universal.id in ids_true
        assert load_specific.id not in ids_true

        # suitable=false: specific load is unsuitable
        resp_false = client.get("/api/v1/loads?suitable=false")
        assert resp_false.status_code == status.HTTP_200_OK
        ids_false = [item["id"] for item in resp_false.data["results"]]
        assert load_specific.id in ids_false
        assert load_universal.id not in ids_false
