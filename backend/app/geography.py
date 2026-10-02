"""

Kavach — West Bengal Geography Reference
============================================
This is NOT a US project. Country: India. State: West Bengal.
Timezone: Asia/Kolkata. Units: degC, mm, km/h.

Coordinates below are approximate district/block-headquarters centroids —
general public geography, not sourced from any restricted API. They are
accurate enough to select a weather grid cell (Open-Meteo/IMD both work on
lat/lon), but are NOT precise village-level survey coordinates. Where a
village-level coordinate is not independently known, the block headquarters
coordinate is used and the location record says so explicitly
(`resolution: "block_centroid"`) rather than implying village-level GPS
precision.

IMD's district-wise APIs (rainfall/warnings/nowcast) key on IMD's own
internal numeric district IDs, which IMD does not publish as an open,
verifiable lookup table (the few IDs visible in public examples, e.g. 164
for Adilabad, Telangana, are from unrelated states and must not be
reused/guessed for West Bengal). Rather than invent a Nadia district ID and
present it as verified, `imd_district_id` is left `None` here until a real
value is confirmed directly with IMD — see README "IMD integration status".
"""

import json
from pathlib import Path

COUNTRY = "India"
STATE = "West Bengal"
TIMEZONE = "Asia/Kolkata"
UNITS = {"temperature": "C", "rainfall": "mm", "wind_speed": "km/h"}

# A resolution tag on every location record: "block_centroid" means the
# coordinate is the block headquarters, not a village-specific GPS point.
DISTRICTS = {
    "Nadia": {
        "blocks": {
            "Krishnanagar Sadar": {
                "latitude": 23.4058, "longitude": 88.5017, "resolution": "block_centroid",
                "villages": ["Bagula", "Chapra", "Krishnaganj", "Hanskhali"],
            },
            "Tehatta": {
                "latitude": 23.6167, "longitude": 88.5333, "resolution": "block_centroid",
                "villages": ["Tehatta", "Karimpur", "Palashipara", "Debagram"],
            },
            "Ranaghat": {
                "latitude": 23.1833, "longitude": 88.5667, "resolution": "block_centroid",
                "villages": ["Ranaghat", "Santipur", "Nabadwip", "Fulia", "Birnagar", "Taherpur"],
            },
            "Kalyani": {
                "latitude": 22.9750, "longitude": 88.4344, "resolution": "block_centroid",
                "villages": ["Kaliganj", "Nakashipara", "Chakdaha", "Haringhata", "Mayapur", "Gangnapur", "Dhubulia"],
            },
        },
        "imd_district_id": None,  # unresolved — see docstring; do not guess
    },
}

# Horticulture Directorate district rows use this 22-district vintage. These
# display names are normalized from that official source; HQ queries are only
# sent to the live geocoder and no coordinates are guessed or embedded here.
DISTRICT_HQ_QUERIES = {
    "Darjeeling": "Darjeeling", "Kalimpong": "Kalimpong", "Jalpaiguri": "Jalpaiguri",
    "Alipurduar": "Alipurduar", "Cooch Behar": "Cooch Behar", "Uttar Dinajpur": "Raiganj",
    "Dakshin Dinajpur": "Balurghat", "Malda": "Malda", "Murshidabad": "Berhampore",
    "Nadia": "Krishnanagar", "North 24 Parganas": "Barasat", "South 24 Parganas": "Alipore",
    "Howrah": "Howrah", "Hooghly": "Chinsurah", "Purba Bardhaman": "Bardhaman",
    "Paschim Bardhaman": "Asansol", "Birbhum": "Suri", "Bankura": "Bankura",
    "Purulia": "Purulia", "Paschim Medinipur": "Midnapore", "Jhargram": "Jhargram",
    "Purba Medinipur": "Tamluk",
}

for _district in DISTRICT_HQ_QUERIES:
    DISTRICTS.setdefault(_district, {"blocks": {}, "imd_district_id": None})


def all_villages():
    out = []
    for district, d in DISTRICTS.items():
        for block, b in d["blocks"].items():
            for v in b["villages"]:
                out.append({
                    "country": COUNTRY, "state": STATE, "district": district, "block": block,
                    "village": v, "latitude": b["latitude"], "longitude": b["longitude"],
                    "resolution": b["resolution"],
                })
    return out


def resolve_location(village: str):
    for rec in all_villages():
        if rec["village"].lower() == village.lower():
            return rec
    return None


def district_catalog():
    """Return the published district vintage and live-geocoder search labels."""
    return {name: {"headquarters_search": query, "coordinates": None,
                   "resolution": "district headquarters resolved from live geocoder on selection"}
            for name, query in DISTRICT_HQ_QUERIES.items()}


def is_supported_state(state: str) -> bool:
    """Geography guard: this product is India / West Bengal only in this build."""
    return state.strip().lower() == STATE.lower()


def is_supported_country(country: str) -> bool:
    return country.strip().lower() == COUNTRY.lower()
