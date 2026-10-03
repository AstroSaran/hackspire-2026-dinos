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
import csv
import pytest
import requests as _requests


@pytest.fixture
def mango_source(tmp_path):
    """Test-only panel for registry/serving contracts, never production training."""
    from app import train_mango_yield_model as trainer
    source=tmp_path/'mango-fixture.csv'
    fields=['state','district','crop','year','estimate_round',
            'area_thousand_ha','production_thousand_mt','source_url']
    with source.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for year_index,(year,(area_total,production_total)) in enumerate(trainer.EXPECTED_TOTALS.items()):
            for index in range(22):
                centered=(index-10.5)/11
                writer.writerow({'state':'West Bengal','district':'Malda' if index==0 else f'Test District {index:02d}',
                    'crop':'Mango','year':year,'estimate_round':'Final Estimate',
                    'area_thousand_ha':f'{area_total/22*(1+centered*.04):.6f}',
                    'production_thousand_mt':f'{production_total/22*(1+centered*.12+(year_index%2)*centered*.02):.6f}',
                    'source_url':'https://wbfpih.wb.gov.in/download?id=test-fixture'})
    return source


@pytest.fixture(autouse=True)
def _no_real_network(request, monkeypatch):
    if request.node.get_closest_marker("integration") or os.environ.get("KAVACH_RUN_LIVE_INTEGRATION_TESTS") == "true":
        yield
        return

    def _blocked(*args, **kwargs):
        raise _requests.exceptions.ConnectionError("network access blocked by test suite guard (Part 19)")

    monkeypatch.setattr(_requests, "get", _blocked)
    yield
