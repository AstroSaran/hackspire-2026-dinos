"""
Kavach test suite — network guard (Part 19: "Normal unit tests must NOT
require internet access", regardless of the environment they run in).

This autouse fixture patches `requests.get` for every test by default to
raise a connection error, so no test's pass/fail depends on whether the
network happens to be reachable. Individual tests that need to simulate a
provider succeeding wrap their own `with patch("requests.get", ...)` inside
the test body, which takes precedence for its scope. The one deliberate
exception is the explicitly-marked, opt-in integration test
(`test_integration_real_open_meteo_call_succeeds`), which is skipped unless
KAVACH_RUN_LIVE_INTEGRATION_TESTS=true is set.
"""
import os
import pytest
import requests as _requests


@pytest.fixture(autouse=True)
def _no_real_network(request, monkeypatch):
    if request.node.get_closest_marker("integration") or os.environ.get("KAVACH_RUN_LIVE_INTEGRATION_TESTS") == "true":
        yield
        return

    def _blocked(*args, **kwargs):
        raise _requests.exceptions.ConnectionError("network access blocked by test suite guard (Part 19)")

    monkeypatch.setattr(_requests, "get", _blocked)
    yield
