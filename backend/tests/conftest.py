import httpx
import pytest


@pytest.fixture(autouse=True)
def isolate_credentials_and_network(monkeypatch):
    """Unit tests never use local credentials or contact a courier."""
    for key in (
        "AUSPOST_API_KEY",
        "AUSPOST_API_PASSWORD",
        "AUSPOST_ACCOUNT_NUMBER",
        "STARTRACK_ACCOUNT_NUMBER",
    ):
        monkeypatch.setenv(key, "")

    def reject_network(*args, **kwargs):
        raise AssertionError("Unit test attempted an unmocked external request")

    monkeypatch.setattr(httpx, "get", reject_network)
