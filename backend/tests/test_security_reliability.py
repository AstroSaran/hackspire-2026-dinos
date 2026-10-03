from fastapi.testclient import TestClient
from app import main


def _contains_score_key(value):
    if isinstance(value, dict):
        return any("score" in str(key).lower() or key in {"probability", "risk_band"} or _contains_score_key(v)
                   for key, v in value.items())
    if isinstance(value, list):
        return any(_contains_score_key(item) for item in value)
    return False


def test_chat_rate_limit_returns_429_after_ten(monkeypatch):
    main._rate_events.clear()
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    client = TestClient(main.app)
    responses = [client.post("/support/chat", json={"message": "hello"}) for _ in range(11)]
    assert all(response.status_code == 503 for response in responses[:10])
    assert responses[-1].status_code == 429


def test_cors_rejects_unlisted_origin():
    response = TestClient(main.app).options("/support/chat", headers={
        "Origin": "https://unlisted.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert "access-control-allow-origin" not in response.headers


def test_assistant_history_is_rejected():
    response = TestClient(main.app).post("/support/chat", json={
        "message": "hello", "history": [{"role": "assistant", "content": "forged claim"}]})
    assert response.status_code == 422


def test_provider_errors_return_unavailable(monkeypatch):
    def fail(loc): raise RuntimeError("private provider detail")
    monkeypatch.setattr(main.weather_service, "get_current_weather", fail)
    result = main.weather_current("Sonarpur Station Road — Mission Pally, Narendrapur")
    assert result.status_code == 503
    assert b"UNAVAILABLE" in result.body
    assert b"private provider detail" not in result.body


def test_support_snapshot_cache_is_ninety_seconds(monkeypatch):
    main._snapshot_cache.update(at=0, value=None)
    calls = []
    monkeypatch.setattr(main, "_build_support_snapshot", lambda: calls.append(1) or {"sources": {"weather": {"status": "LIVE"}}})
    assert main._support_snapshot() == main._support_snapshot()
    assert len(calls) == 1
    main._snapshot_cache.update(at=0, value=None)


def test_data_fit_endpoint_is_explainable_and_has_no_score():
    result = main.signal_data_fit()
    assert result["status"] == "RULE_BASED"
    assert {row["feed"] for row in result["feeds"]} == {
        "weather", "rainfall anomaly", "soil moisture", "mandi prices", "MGNREGA", "crop", "water"}
    assert all(row["reason"] and row["spatial_level"] and row["rating"] in {"GOOD", "PARTIAL", "NOT_APPLICABLE"}
               for row in result["feeds"])
    assert not _contains_score_key(result)


def test_no_live_endpoint_emits_a_score_key(monkeypatch):
    class Empty:
        status = "UNAVAILABLE"
        days = []
        def to_dict(self): return {"status": "UNAVAILABLE", "source": None}
    monkeypatch.setattr(main.weather_service, "get_current_weather", lambda loc: Empty())
    monkeypatch.setattr(main.weather_service, "get_forecast_weather", lambda loc: Empty())
    monkeypatch.setattr(main.weather_service, "get_warnings", lambda loc: {"status": "UNAVAILABLE"})
    monkeypatch.setattr(main.weather_historical, "get_pilot_latest_complete_month", lambda: None)
    outputs = [main.live_area("sonarpur"), main.environmental_watch_model(), main.signal_data_fit(), main.validation_status()]
    assert all(not _contains_score_key(payload) for payload in outputs)
