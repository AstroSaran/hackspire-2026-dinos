from unittest.mock import patch

from app.main import live_employment_indicators, live_market_prices


class Response:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"records": [
            {"state": "West Bengal", "district": "South 24 Parganas",
             "market": "Baruipur", "commodity": "Rice", "modal_price": "3100"},
            {"state": "Bihar", "district": "Patna", "market": "Patna",
             "commodity": "Rice", "modal_price": "2900"},
        ]}


def test_market_feed_uses_actual_agmarknet_state_field_and_returns_matching_rows(monkeypatch):
    monkeypatch.setenv("DATA_GOV_IN_API_KEY", "private-test-key")
    monkeypatch.setenv("DATA_GOV_IN_MARKET_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070")
    with patch("app.main.requests.get", return_value=Response()) as get:
        result = live_market_prices()

    assert result["status"] == "LIVE"
    assert result["records"][0]["market"] == "Baruipur"
    assert len(result["records"]) == 1
    params = get.call_args.kwargs["params"]
    assert params["filters[state.keyword]"] == "West Bengal"
    assert params["offset"] == 0
    assert params["limit"] == 500
    assert "private-test-key" not in repr(result)


def test_market_feed_does_not_claim_live_when_provider_cannot_be_reached(monkeypatch):
    import requests

    monkeypatch.setenv("DATA_GOV_IN_API_KEY", "private-test-key")
    monkeypatch.setenv("DATA_GOV_IN_MARKET_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070")
    with patch("app.main.requests.get", side_effect=requests.ConnectionError("offline")):
        result = live_market_prices()

    assert result["status"] == "UNAVAILABLE"
    assert result["records"] == []
    assert "private-test-key" not in repr(result)


def test_mgnrega_uses_its_own_key_and_does_not_replace_market_key(monkeypatch):
    monkeypatch.setenv("DATA_GOV_IN_API_KEY", "market-test-key")
    monkeypatch.setenv("DATA_GOV_IN_MGNREGA_API_KEY", "mgnrega-test-key")
    monkeypatch.setenv("DATA_GOV_IN_MGNREGA_RESOURCE_ID", "12345678-1234-1234-1234-123456789012")
    with patch("app.main.requests.get", return_value=Response()) as get:
        live_employment_indicators()

    assert get.call_args.kwargs["params"]["api-key"] == "mgnrega-test-key"
