from app.main import SONARPUR_LIVE_VILLAGE, SONARPUR_SIMULATED_REMAINDER
from app import geography

def test_sonarpur_exact_live_location():
    rec = geography.resolve_location(SONARPUR_LIVE_VILLAGE)
    assert rec["latitude"] == 22.442948
    assert rec["longitude"] == 88.428633
    assert rec["district"] == "South 24 Parganas"
    assert rec["block"] == "Rajpur Sonarpur"

def test_sonarpur_remainder_is_explicitly_simulated():
    assert set(SONARPUR_SIMULATED_REMAINDER) == {
        "crop_stress_index", "mandi_price_deviation_pct", "mgnrega_demand_spike_pct",
        "water_stress_index", "historical_vulnerability"
    }
