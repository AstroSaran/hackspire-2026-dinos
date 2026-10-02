"""Registered real pilot locations, loaded from backend/data/live_pilots.json."""
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class LivePilot:
    village: str
    address: str
    url_key: str
    coordinate_source: str
    latitude: float
    longitude: float
    district: str
    block: str
    resolution: str


def _load_registry():
    path = Path(__file__).resolve().parents[1] / "data" / "live_pilots.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        pilots = [LivePilot(**item) for item in raw]
    except (OSError, ValueError, TypeError):
        pilots = []
    return {pilot.url_key.lower(): pilot for pilot in pilots}


_REGISTRY = _load_registry()


def get_by_key(url_key: str) -> Optional[LivePilot]:
    return _REGISTRY.get(url_key.strip().lower())


def all_pilots():
    return list(_REGISTRY.values())
