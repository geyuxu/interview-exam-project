import httpx
import pytest

from app.models import Shipment
from app.tracking import TrackingService, parse_tracking


@pytest.fixture
def shipment(monkeypatch):
    for key in ("AUSPOST_API_KEY", "AUSPOST_API_PASSWORD", "STARTRACK_ACCOUNT_NUMBER"):
        monkeypatch.setenv(key, "synthetic-test-only")
    return Shipment(id="TEST", order_no="ORDER", carrier="startrack", tracking_no="TEST123")


def test_parse_tracks_latest_event_and_missing_date():
    result = parse_tracking({"tracking_results": [{"tracking_id": "TEST123", "status": "In Transit", "trackable_items": [{"article_id": "ARTICLE1", "events": [
        {"description": "Event without date"},
        {"description": "Earlier", "date": "2026-01-01T09:00:00+11:00"},
        {"description": "Latest", "date": "2026-01-02T10:00:00+11:00", "location": "Sydney"},
    ]}]}]}, "TEST123")
    assert result["state"] == "available"
    assert result["last_update"] == "2026-01-02T10:00:00+11:00"
    assert result["events"][0]["description"] == "Latest"
    assert result["environment"] == "testbed"


@pytest.mark.parametrize("payload", [None, [], {}, {"tracking_results": []}, {"tracking_results": [{"tracking_id": "OTHER", "status": "Delivered"}]}, {"tracking_results": [{"tracking_id": "TEST123", "trackable_items": "bad"}]}, {"tracking_results": [{"tracking_id": "TEST123", "errors": [{"code": "INVALID"}]}]}])
def test_invalid_and_unmatched_responses_are_unavailable(payload):
    result = parse_tracking(payload, "TEST123")
    assert result["state"] == "unavailable"
    assert result["status"] is None


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_failures_are_safe_and_cached(monkeypatch, shipment, status):
    calls = []
    def fake_get(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(status, text="private upstream error")
    monkeypatch.setattr(httpx, "get", fake_get)
    service = TrackingService()
    first = service.get(shipment)
    second = service.get(shipment)
    assert first["state"] == "unavailable"
    assert str(status) in first["message"]
    assert "private" not in str(first)
    assert second["cached"]
    assert len(calls) == 1
    assert calls[0]["headers"]["Account-Number"] == "synthetic-test-only"


def test_timeout_and_missing_config(monkeypatch, shipment):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("upstream timeout")
    monkeypatch.setattr(httpx, "get", timeout)
    assert TrackingService().get(shipment)["state"] == "unavailable"
    monkeypatch.delenv("AUSPOST_API_KEY")
    assert TrackingService().get(shipment)["state"] == "not_configured"


def test_non_json_and_tnt(monkeypatch, shipment):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(200, text="not json"))
    assert TrackingService().get(shipment)["state"] == "unavailable"
    shipment.carrier = "tnt"
    assert TrackingService().get(shipment)["state"] == "not_implemented"


def test_local_rate_limit(monkeypatch, shipment):
    calls = []
    def fake_get(*args, **kwargs):
        calls.append(1)
        return httpx.Response(200, json={"tracking_results": []})
    monkeypatch.setattr(httpx, "get", fake_get)
    service = TrackingService()
    for index in range(11):
        shipment.tracking_no = f"TEST{index}"
        result = service.get(shipment)
    assert len(calls) == 10
    assert "上限" in result["message"]
