from copy import deepcopy
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import OrderDataset
from app.orders import build_orders, load_dataset, load_products, measurement, shipping_estimate


@pytest.fixture
def data():
    return load_dataset().model_dump(mode="json")


def test_sample_totals_and_order_isolation():
    orders = build_orders(load_dataset(), load_products())
    assert [order["quantity"] for order in orders] == [15, 16]
    assert [len(order["shipments"]) for order in orders] == [1, 2]
    assert [order["totals"]["total"] for order in orders] == ["2131.00", "1655.00"]
    for order in orders:
        assert all(item["order_no"] == order["order_no"] for item in order["items"])
        totals = order["totals"]
        assert Decimal(totals["total"]) == sum(
            Decimal(totals[key]) for key in ("subtotal", "gst", "shipment_fee")
        )
        assert sum(Decimal(line["line_subtotal"]) for line in order["items"]) + Decimal(
            totals["rounding_adjustment"]
        ) == Decimal(totals["subtotal"])


def test_no_early_unit_rounding_or_double_tax(data):
    dataset = deepcopy(data)
    dataset["orders"] = dataset["orders"][:1]
    dataset["shipments"] = dataset["shipments"][:1]
    dataset["line_items"] = dataset["line_items"][:1]
    dataset["line_items"][0].update(sku="NEW-SKU", quantity=6)
    product = {"NEW-SKU": {"ProductName": "Synthetic test item", "RRP": "1.00"}}
    order = build_orders(OrderDataset.model_validate(dataset), product)[0]
    assert order["items"][0]["unit_ex_gst"] == "0.91"
    assert order["items"][0]["line_subtotal"] == "5.45"
    assert order["totals"]["total"] == "6.00"


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True, "3", 100001])
def test_invalid_quantities_rejected(data, quantity):
    data["line_items"][0]["quantity"] = quantity
    with pytest.raises(ValidationError):
        OrderDataset.model_validate(data)


@pytest.mark.parametrize(
    "case",
    ["cross_order", "orphan_line", "duplicate_order", "duplicate_shipment", "unused_shipment"],
)
def test_invalid_relationships(data, case):
    if case == "cross_order":
        data["line_items"][0]["shipment_id"] = "Track 2"
    elif case == "orphan_line":
        data["line_items"][0]["order_no"] = "MISSING"
    elif case == "duplicate_order":
        data["orders"].append(data["orders"][0])
    elif case == "duplicate_shipment":
        data["shipments"].append(data["shipments"][0])
    else:
        data["shipments"].append({**data["shipments"][0], "id": "UNUSED"})
    with pytest.raises(ValidationError):
        OrderDataset.model_validate(data)


def test_missing_sku_blocks_only_affected_order(data):
    data["line_items"][0]["sku"] = "MISSING"
    orders = build_orders(OrderDataset.model_validate(data), load_products())
    assert orders[0]["totals"]["total"] is None
    assert orders[0]["warnings"]
    assert orders[1]["totals"]["total"] == "1655.00"


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-1", "not-a-number", None])
def test_invalid_price_does_not_crash(price):
    products = load_products()
    products["TBAMET10"]["RRP"] = price
    order = build_orders(load_dataset(), products)[0]
    assert order["items"][0]["rrp"] is None
    assert not order["totals"]["complete"]


def test_shipping_estimate_aggregates_with_tnt_zero():
    orders = build_orders(load_dataset(), load_products(), estimate=True)
    # Order 1: 0.988 kg product weight + 0.2 kg packaging = 1.188 kg;
    # ceil to 2 kg, then 8 + 2.5 * 2 + 3 = 16 AUD.
    assert [order["totals"]["shipment_fee"] for order in orders] == ["16.00", "16.00"]
    assert orders[0]["shipments"][0]["shipping"]["chargeable_kg"] == "1.188"
    assert orders[1]["shipments"][1]["shipping"]["fee"] == "0.00"
    assert orders[1]["totals"]["total"] == "1671.00"


def test_unit_conversion_and_shipping_fallback():
    assert measurement("1000g", {"g": Decimal("0.001")}) == Decimal("1")
    assert measurement("1lb", {"g": Decimal("0.001")}) is None
    result = shipping_estimate(
        [{"product": {"weight": "1kg"}, "quantity": 1}], "3141", "startrack", True
    )
    assert result["state"] == "not_estimated"
    assert result["fee"] == "0.00"


def test_preview_validation_and_missing_shipment(data):
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/orders").status_code == 200
    data["line_items"][0]["quantity"] = 0
    response = client.post("/api/orders/preview", json=data)
    assert response.status_code == 422
    assert "quantity" in response.json()["detail"][0]["field"]
    assert "input" not in response.text
    assert client.get("/api/shipments/unknown/tracking").status_code == 404


def test_new_order_identifier_is_data_driven(data):
    for row in data["orders"] + data["shipments"] + data["line_items"]:
        row["order_no"] = "NEW-" + row["order_no"]
    client = TestClient(app)
    response = client.post("/api/orders/preview?estimate=true", json=data)
    assert response.status_code == 200
    assert response.json()["orders"][0]["totals"]["total"] == "2147.00"
