from datetime import UTC, datetime
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import CarrierUserFactory
from apps.garage.tests.factories import VehicleTypeFactory
from apps.loads.models import Load
from apps.loads.tests.helpers_list import add_offer_to_load, create_test_load


@pytest.mark.django_db
@pytest.mark.urls("apps.loads.tests.urls_list_only")
class TestLoadListFilters:
    """Test suite covering every query filter with positive and negative checks."""

    @pytest.fixture(autouse=True)
    def setup_client(self) -> None:
        self.user = CarrierUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_filter_origin_country(self) -> None:
        load_uz = create_test_load(origin_country="UZ", destination_country="RU")
        load_tr = create_test_load(origin_country="TR", destination_country="RU")

        # Positive
        resp_uz = self.client.get("/api/v1/loads?origin_country=UZ")
        assert resp_uz.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp_uz.data["results"]]
        assert load_uz.id in ids
        assert load_tr.id not in ids

        # Negative
        resp_none = self.client.get("/api/v1/loads?origin_country=KZ")
        assert resp_none.status_code == status.HTTP_200_OK
        assert resp_none.data["count"] == 0

    def test_filter_destination_country(self) -> None:
        load_ru = create_test_load(origin_country="UZ", destination_country="RU")
        load_tr = create_test_load(origin_country="UZ", destination_country="TR")

        # Positive
        resp_ru = self.client.get("/api/v1/loads?destination_country=RU")
        assert resp_ru.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp_ru.data["results"]]
        assert load_ru.id in ids
        assert load_tr.id not in ids

        # Negative
        resp_none = self.client.get("/api/v1/loads?destination_country=DE")
        assert resp_none.status_code == status.HTTP_200_OK
        assert resp_none.data["count"] == 0

    def test_filter_body_types_repeated_and_comma_separated(self) -> None:
        vt1 = VehicleTypeFactory(code="tent_flt")
        vt2 = VehicleTypeFactory(code="reefer_flt")
        vt3 = VehicleTypeFactory(code="board_flt")

        load1 = create_test_load(body_types=[vt1])
        load2 = create_test_load(body_types=[vt2])
        load3 = create_test_load(body_types=[vt3])

        # Positive single
        resp_single = self.client.get(f"/api/v1/loads?body_types={vt1.id}")
        assert resp_single.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp_single.data["results"]]
        assert load1.id in ids
        assert load2.id not in ids
        assert load3.id not in ids

        # Positive repeated
        resp_repeated = self.client.get(f"/api/v1/loads?body_types={vt1.id}&body_types={vt2.id}")
        assert resp_repeated.status_code == status.HTTP_200_OK
        ids_rep = [item["id"] for item in resp_repeated.data["results"]]
        assert load1.id in ids_rep
        assert load2.id in ids_rep
        assert load3.id not in ids_rep

        # Positive comma separated
        resp_csv = self.client.get(f"/api/v1/loads?body_types={vt1.id},{vt2.id}")
        assert resp_csv.status_code == status.HTTP_200_OK
        ids_csv = [item["id"] for item in resp_csv.data["results"]]
        assert load1.id in ids_csv
        assert load2.id in ids_csv
        assert load3.id not in ids_csv

        # Negative: valid vehicle type not attached to any loads
        vt_unused = VehicleTypeFactory(code="unused_flt")
        resp_unused = self.client.get(f"/api/v1/loads?body_types={vt_unused.id}")
        assert resp_unused.status_code == status.HTTP_200_OK
        assert resp_unused.data["count"] == 0

        # Invalid ID returns 400 validation error
        resp_invalid = self.client.get("/api/v1/loads?body_types=999999")
        assert resp_invalid.status_code == status.HTTP_400_BAD_REQUEST

    def test_filter_weight_min_and_max(self) -> None:
        load_light = create_test_load(weight_t=Decimal("10.000"))
        load_medium = create_test_load(weight_t=Decimal("20.000"))
        load_heavy = create_test_load(weight_t=Decimal("30.000"))

        # Positive min
        resp_min = self.client.get("/api/v1/loads?weight_min=15")
        assert resp_min.status_code == status.HTTP_200_OK
        ids_min = [item["id"] for item in resp_min.data["results"]]
        assert load_medium.id in ids_min
        assert load_heavy.id in ids_min
        assert load_light.id not in ids_min

        # Positive max
        resp_max = self.client.get("/api/v1/loads?weight_max=15")
        assert resp_max.status_code == status.HTTP_200_OK
        ids_max = [item["id"] for item in resp_max.data["results"]]
        assert load_light.id in ids_max
        assert load_medium.id not in ids_max
        assert load_heavy.id not in ids_max

        # Negative
        resp_neg = self.client.get("/api/v1/loads?weight_min=50")
        assert resp_neg.status_code == status.HTTP_200_OK
        assert resp_neg.data["count"] == 0

    def test_filter_volume_min_and_max(self) -> None:
        load_small = create_test_load(volume_m3=Decimal("40.000"))
        load_big = create_test_load(volume_m3=Decimal("95.000"))

        # Positive min
        resp_min = self.client.get("/api/v1/loads?volume_min=60")
        assert resp_min.status_code == status.HTTP_200_OK
        ids_min = [item["id"] for item in resp_min.data["results"]]
        assert load_big.id in ids_min
        assert load_small.id not in ids_min

        # Positive max
        resp_max = self.client.get("/api/v1/loads?volume_max=60")
        assert resp_max.status_code == status.HTTP_200_OK
        ids_max = [item["id"] for item in resp_max.data["results"]]
        assert load_small.id in ids_max
        assert load_big.id not in ids_max

        # Negative
        resp_neg = self.client.get("/api/v1/loads?volume_min=120")
        assert resp_neg.status_code == status.HTTP_200_OK
        assert resp_neg.data["count"] == 0

    def test_filter_price_min_and_max(self) -> None:
        load_cheap = create_test_load(price_amount=Decimal("1000.00"))
        load_expensive = create_test_load(price_amount=Decimal("4000.00"))

        # Positive min
        resp_min = self.client.get("/api/v1/loads?price_min=2500")
        assert resp_min.status_code == status.HTTP_200_OK
        ids_min = [item["id"] for item in resp_min.data["results"]]
        assert load_expensive.id in ids_min
        assert load_cheap.id not in ids_min

        # Positive max
        resp_max = self.client.get("/api/v1/loads?price_max=2500")
        assert resp_max.status_code == status.HTTP_200_OK
        ids_max = [item["id"] for item in resp_max.data["results"]]
        assert load_cheap.id in ids_max
        assert load_expensive.id not in ids_max

        # Negative
        resp_neg = self.client.get("/api/v1/loads?price_min=8000")
        assert resp_neg.status_code == status.HTTP_200_OK
        assert resp_neg.data["count"] == 0

    def test_filter_currency(self) -> None:
        load_usd = create_test_load(currency_code="USD")
        load_eur = create_test_load(currency_code="EUR")

        # Positive
        resp_usd = self.client.get("/api/v1/loads?currency=USD")
        assert resp_usd.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp_usd.data["results"]]
        assert load_usd.id in ids
        assert load_eur.id not in ids

        # Negative
        resp_neg = self.client.get("/api/v1/loads?currency=RUB")
        assert resp_neg.status_code == status.HTTP_200_OK
        assert resp_neg.data["count"] == 0

    def test_filter_loading_dates_range(self) -> None:
        d1 = datetime(2026, 10, 10, 10, 0, 0, tzinfo=UTC)
        d2 = datetime(2026, 10, 20, 10, 0, 0, tzinfo=UTC)

        load1 = create_test_load(origin_planned_from=d1)
        load2 = create_test_load(origin_planned_from=d2)

        # Positive loading_from
        resp_from = self.client.get("/api/v1/loads?loading_from=2026-10-15T00:00:00Z")
        assert resp_from.status_code == status.HTTP_200_OK
        ids_from = [item["id"] for item in resp_from.data["results"]]
        assert load2.id in ids_from
        assert load1.id not in ids_from

        # Positive loading_to
        resp_to = self.client.get("/api/v1/loads?loading_to=2026-10-15T00:00:00Z")
        assert resp_to.status_code == status.HTTP_200_OK
        ids_to = [item["id"] for item in resp_to.data["results"]]
        assert load1.id in ids_to
        assert load2.id not in ids_to

        # Negative
        resp_neg = self.client.get("/api/v1/loads?loading_from=2026-11-01T00:00:00Z")
        assert resp_neg.status_code == status.HTTP_200_OK
        assert resp_neg.data["count"] == 0

    def test_filter_unloading_dates_range(self) -> None:
        d1 = datetime(2026, 10, 12, 10, 0, 0, tzinfo=UTC)
        d2 = datetime(2026, 10, 25, 10, 0, 0, tzinfo=UTC)

        load1 = create_test_load(destination_planned_from=d1)
        load2 = create_test_load(destination_planned_from=d2)

        # Positive unloading_from
        resp_from = self.client.get("/api/v1/loads?unloading_from=2026-10-18T00:00:00Z")
        assert resp_from.status_code == status.HTTP_200_OK
        ids_from = [item["id"] for item in resp_from.data["results"]]
        assert load2.id in ids_from
        assert load1.id not in ids_from

        # Positive unloading_to
        resp_to = self.client.get("/api/v1/loads?unloading_to=2026-10-18T00:00:00Z")
        assert resp_to.status_code == status.HTTP_200_OK
        ids_to = [item["id"] for item in resp_to.data["results"]]
        assert load1.id in ids_to
        assert load2.id not in ids_to

        # Negative
        resp_neg = self.client.get("/api/v1/loads?unloading_from=2026-11-01T00:00:00Z")
        assert resp_neg.status_code == status.HTTP_200_OK
        assert resp_neg.data["count"] == 0

    def test_filter_is_adr(self) -> None:
        load_adr = create_test_load(is_adr=True, adr_class=3)
        load_no_adr = create_test_load(is_adr=False)

        # Positive true
        resp_true = self.client.get("/api/v1/loads?is_adr=true")
        assert resp_true.status_code == status.HTTP_200_OK
        ids_true = [item["id"] for item in resp_true.data["results"]]
        assert load_adr.id in ids_true
        assert load_no_adr.id not in ids_true

        # Positive false
        resp_false = self.client.get("/api/v1/loads?is_adr=false")
        assert resp_false.status_code == status.HTTP_200_OK
        ids_false = [item["id"] for item in resp_false.data["results"]]
        assert load_no_adr.id in ids_false
        assert load_adr.id not in ids_false

    def test_filter_temp_controlled(self) -> None:
        load_temp = create_test_load(
            temp_controlled=True,
            temp_min_c=Decimal("-18.00"),
            temp_max_c=Decimal("-10.00"),
        )
        load_standard = create_test_load(temp_controlled=False)

        # Positive true
        resp_true = self.client.get("/api/v1/loads?temp_controlled=true")
        assert resp_true.status_code == status.HTTP_200_OK
        ids_true = [item["id"] for item in resp_true.data["results"]]
        assert load_temp.id in ids_true
        assert load_standard.id not in ids_true

        # Positive false
        resp_false = self.client.get("/api/v1/loads?temp_controlled=false")
        assert resp_false.status_code == status.HTTP_200_OK
        ids_false = [item["id"] for item in resp_false.data["results"]]
        assert load_standard.id in ids_false
        assert load_temp.id not in ids_false

    def test_filter_has_offers(self) -> None:
        load_with_offers = create_test_load()
        add_offer_to_load(load_with_offers)

        load_without_offers = create_test_load()

        # Positive true
        resp_true = self.client.get("/api/v1/loads?has_offers=true")
        assert resp_true.status_code == status.HTTP_200_OK
        ids_true = [item["id"] for item in resp_true.data["results"]]
        assert load_with_offers.id in ids_true
        assert load_without_offers.id not in ids_true

        # Positive false
        resp_false = self.client.get("/api/v1/loads?has_offers=false")
        assert resp_false.status_code == status.HTTP_200_OK
        ids_false = [item["id"] for item in resp_false.data["results"]]
        assert load_without_offers.id in ids_false
        assert load_with_offers.id not in ids_false

    def test_filter_transport_mode(self) -> None:
        load_ftl = create_test_load(transport_mode=Load.TransportMode.FTL)
        load_ltl = create_test_load(transport_mode=Load.TransportMode.LTL)

        # Positive FTL
        resp_ftl = self.client.get("/api/v1/loads?transport_mode=FTL")
        assert resp_ftl.status_code == status.HTTP_200_OK
        ids_ftl = [item["id"] for item in resp_ftl.data["results"]]
        assert load_ftl.id in ids_ftl
        assert load_ltl.id not in ids_ftl

        # Positive LTL
        resp_ltl = self.client.get("/api/v1/loads?transport_mode=LTL")
        assert resp_ltl.status_code == status.HTTP_200_OK
        ids_ltl = [item["id"] for item in resp_ltl.data["results"]]
        assert load_ltl.id in ids_ltl
        assert load_ftl.id not in ids_ltl

    def test_filter_search(self) -> None:
        load1 = create_test_load(
            cargo_description="Raw cotton yarn in bales",
            origin_address="Andijan, Central Depot",
            destination_address="Baku, International Port",
        )
        load2 = create_test_load(
            cargo_description="Solar monocrystalline panels",
            origin_address="Samarkand, High Tech Park",
            destination_address="Almaty, Warehouse 5",
        )

        # Match description
        resp_desc = self.client.get("/api/v1/loads?search=cotton")
        assert resp_desc.status_code == status.HTTP_200_OK
        ids_desc = [item["id"] for item in resp_desc.data["results"]]
        assert load1.id in ids_desc
        assert load2.id not in ids_desc

        # Match origin address
        resp_orig = self.client.get("/api/v1/loads?search=Samarkand")
        assert resp_orig.status_code == status.HTTP_200_OK
        ids_orig = [item["id"] for item in resp_orig.data["results"]]
        assert load2.id in ids_orig
        assert load1.id not in ids_orig

        # Match destination address
        resp_dest = self.client.get("/api/v1/loads?search=Baku")
        assert resp_dest.status_code == status.HTTP_200_OK
        ids_dest = [item["id"] for item in resp_dest.data["results"]]
        assert load1.id in ids_dest
        assert load2.id not in ids_dest

        # Negative
        resp_neg = self.client.get("/api/v1/loads?search=NonexistentSuperQuery999")
        assert resp_neg.status_code == status.HTTP_200_OK
        assert resp_neg.data["count"] == 0
