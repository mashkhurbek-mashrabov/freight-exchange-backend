"""Tests for LoadListView: public active loads board and query performance."""

from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import CarrierUserFactory, CompanyFactory, ShipperUserFactory
from apps.garage.tests.factories import VehicleTypeFactory
from apps.loads.models import Load, RoutePoint
from apps.loads.tests.factories import LoadFactory, RoutePointFactory
from apps.loads.tests.helpers_list import (
    create_shipper_with_company,
    create_test_load,
    get_or_create_country,
)


@pytest.mark.django_db
@pytest.mark.urls("apps.loads.tests.urls_list_only")
class TestLoadListView:
    """Test suite for GET /api/v1/loads."""

    def test_unauthenticated_request_returns_401(self) -> None:
        client = APIClient()
        response = client.get("/api/v1/loads")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["code"] == "not_authenticated"

    def test_list_response_shape_and_pagination(self) -> None:
        user = CarrierUserFactory()
        client = APIClient()
        client.force_authenticate(user=user)

        shipper, company = create_shipper_with_company(company_name="Logistics Pro")
        vtype = VehicleTypeFactory(code="tent", name_i18n={"en": "Tent"})
        load = create_test_load(
            shipper=shipper,
            company=company,
            cargo_description="Industrial machinery",
            weight_t=Decimal("22.500"),
            volume_m3=Decimal("90.000"),
            distance_km=1200,
            price_amount=Decimal("3500.00"),
            currency_code="USD",
            price_negotiable=True,
            trucks_needed=2,
            trucks_found=1,
            origin_country="UZ",
            origin_address="Tashkent, Sergeli",
            destination_country="RU",
            destination_address="Moscow, South Port",
            body_types=[vtype],
        )

        response = client.get("/api/v1/loads")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data
        assert data["count"] == 1
        assert len(data["results"]) == 1

        item = data["results"][0]
        assert item["id"] == load.id
        assert item["origin"] == {"country": "UZ", "address": "Tashkent, Sergeli"}
        assert item["destination"] == {"country": "RU", "address": "Moscow, South Port"}
        assert item["distance_km"] == 1200
        assert Decimal(item["weight_t"]) == Decimal("22.500")
        assert Decimal(item["volume_m3"]) == Decimal("90.000")
        assert Decimal(item["price_amount"]) == Decimal("3500.00")
        assert item["currency"] == "USD"
        assert item["shipper_company"] == "Logistics Pro"
        assert item["negotiable"] is True
        assert item["trucks_needed"] == 2
        assert item["trucks_found"] == 1
        assert item["published_at"] is not None

        assert len(item["body_types"]) == 1
        assert item["body_types"][0]["id"] == vtype.id
        assert item["body_types"][0]["code"] == "tent"
        assert item["body_types"][0]["name_i18n"] == {"en": "Tent"}

    def test_list_excludes_non_active_loads(self) -> None:
        user = CarrierUserFactory()
        client = APIClient()
        client.force_authenticate(user=user)

        active_load = create_test_load(status=Load.Status.ACTIVE)
        create_test_load(status=Load.Status.DRAFT)
        create_test_load(status=Load.Status.IN_PROGRESS)
        create_test_load(status=Load.Status.COMPLETED)
        create_test_load(status=Load.Status.CANCELLED)
        create_test_load(status=Load.Status.EXPIRED)

        response = client.get("/api/v1/loads")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == active_load.id

    def test_shipper_company_fallback_resolution(self) -> None:
        user = CarrierUserFactory()
        client = APIClient()
        client.force_authenticate(user=user)

        # 1. Load with direct company
        s1 = ShipperUserFactory()
        c1 = CompanyFactory(owner=s1, name="Direct Company")
        load1 = create_test_load(shipper=s1, company=c1)

        # 2. Load without direct company, but shipper has company
        s2 = ShipperUserFactory()
        CompanyFactory(owner=s2, name="Owner Fallback Co")
        load2 = create_test_load(shipper=s2, company=None)

        # 3. Load without company and shipper without company
        s3 = ShipperUserFactory()
        load3 = create_test_load(shipper=s3, company=None)

        response = client.get("/api/v1/loads")
        assert response.status_code == status.HTTP_200_OK

        results_by_id = {item["id"]: item for item in response.data["results"]}
        assert results_by_id[load1.id]["shipper_company"] == "Direct Company"
        assert results_by_id[load2.id]["shipper_company"] == "Owner Fallback Co"
        assert results_by_id[load3.id]["shipper_company"] is None

    def test_origin_and_destination_seq_rules(self) -> None:
        """Origin is loading point with lowest seq; destination is unloading with highest seq."""
        user = CarrierUserFactory()
        client = APIClient()
        client.force_authenticate(user=user)

        load = LoadFactory(status=Load.Status.ACTIVE)

        uz = get_or_create_country("UZ")
        kz = get_or_create_country("KZ")
        ru = get_or_create_country("RU")

        RoutePointFactory(
            load=load,
            seq=1,
            kind=RoutePoint.Kind.LOADING,
            country=uz,
            address="Point 1 (loading)",
        )
        RoutePointFactory(
            load=load,
            seq=2,
            kind=RoutePoint.Kind.LOADING,
            country=uz,
            address="Point 2 (second loading)",
        )
        RoutePointFactory(
            load=load,
            seq=3,
            kind=RoutePoint.Kind.BORDER,
            country=kz,
            address="Point 3 (border transit)",
        )
        RoutePointFactory(
            load=load,
            seq=4,
            kind=RoutePoint.Kind.UNLOADING,
            country=ru,
            address="Point 4 (unloading)",
        )

        response = client.get("/api/v1/loads")
        assert response.status_code == status.HTTP_200_OK
        item = response.data["results"][0]

        # Origin must still be seq 1 (lowest loading seq)
        assert item["origin"]["address"] == "Point 1 (loading)"
        # Destination must be seq 4 (highest unloading seq)
        assert item["destination"]["address"] == "Point 4 (unloading)"

    def test_constant_query_count_regardless_of_page_size(
        self, django_assert_max_num_queries
    ) -> None:
        """Verify that page_size=5 and page_size=50 execute the exact same number of SQL queries."""
        user = CarrierUserFactory()
        client = APIClient()
        client.force_authenticate(user=user)

        vtype1 = VehicleTypeFactory(code="tent_opt", name_i18n={"en": "Tent"})
        vtype2 = VehicleTypeFactory(code="reefer_opt", name_i18n={"en": "Reefer"})

        # Seed 60 loads
        for i in range(60):
            create_test_load(
                cargo_description=f"Load #{i}",
                body_types=[vtype1, vtype2],
            )

        # 1. Warm-up request to populate internal caches (auth, content types, etc.)
        client.get("/api/v1/loads?page_size=1")

        # 2. Count queries for page_size=5
        with django_assert_max_num_queries(10) as captured_5:
            resp_5 = client.get("/api/v1/loads?page_size=5")
            assert resp_5.status_code == status.HTTP_200_OK
            assert len(resp_5.data["results"]) == 5

        queries_5_count = len(captured_5.captured_queries)

        # 3. Count queries for page_size=50
        with django_assert_max_num_queries(10) as captured_50:
            resp_50 = client.get("/api/v1/loads?page_size=50")
            assert resp_50.status_code == status.HTTP_200_OK
            assert len(resp_50.data["results"]) == 50

        queries_50_count = len(captured_50.captured_queries)

        # The query count must be strictly identical regardless of page size!
        assert queries_5_count == queries_50_count
