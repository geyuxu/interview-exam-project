from fastapi.testclient import TestClient

from app import main
from app.orders import build_orders, load_dataset, load_products


def test_preview_does_not_require_sample_orders(monkeypatch):
    data = load_dataset().model_dump(mode="json")

    def broken_orders():
        raise ValueError("Corrupted sample file")

    monkeypatch.setattr(main, "load_dataset", broken_orders)
    response = TestClient(main.app).post("/api/orders/preview", json=data)
    assert response.status_code == 200


def test_tracking_does_not_require_product_catalog(monkeypatch):
    def broken_catalog():
        raise ValueError("Corrupted product file")

    monkeypatch.setattr(main, "load_products", broken_catalog)
    response = TestClient(main.app).get("/api/shipments/Track%203/tracking")
    assert response.status_code == 200
    assert response.json()["state"] == "not_implemented"


def test_imported_tracking_calls_real_adapter(monkeypatch):
    seen = []

    def record(request):
        seen.append((request.carrier, request.tracking_no))
        return {
            "state": "unavailable",
            "status": None,
            "last_update": None,
            "events": [],
            "message": "Synthetic test response",
            "environment": "testbed",
            "checked_at": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(main.tracking_service, "get", record)
    response = TestClient(main.app).post(
        "/api/tracking", json={"carrier": "startrack", "tracking_no": "NEW123"}
    )
    assert response.status_code == 200
    assert seen == [("startrack", "NEW123")]


def test_server_enforces_import_size():
    response = TestClient(main.app).post(
        "/api/orders/preview",
        content=b" " * (1024 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_fractional_cent_rrp_is_not_silently_displayed_as_different_price():
    products = load_products()
    products["TBAMET10"]["RRP"] = "0.001"
    order = build_orders(load_dataset(), products)[0]
    assert order["totals"]["total"] is None


def test_template_is_downloadable():
    response = TestClient(main.app).get("/api/orders/template")
    assert response.status_code == 200
    assert response.json()["orders"][0]["order_no"]
    assert "attachment" in response.headers["content-disposition"]


def test_chunked_request_cannot_bypass_size_limit():
    def chunks():
        for _ in range(17):
            yield b" " * 65536

    response = TestClient(main.app).post(
        "/api/orders/preview", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


def test_invalid_tracking_request_is_rejected():
    client = TestClient(main.app)
    assert (
        client.post(
            "/api/tracking", json={"carrier": "startrack", "tracking_no": "https://example.com"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/tracking", json={"carrier": "unknown", "tracking_no": "123"}).status_code
        == 422
    )


def test_corrupt_product_file_returns_clear_error(monkeypatch):
    def broken_catalog():
        raise ValueError("internal contents must not be exposed")

    monkeypatch.setattr(main, "load_products", broken_catalog)
    response = TestClient(main.app).get("/api/orders")
    assert response.status_code == 503
    assert "internal contents" not in response.text
