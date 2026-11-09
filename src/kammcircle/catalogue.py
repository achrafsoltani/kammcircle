"""Typed access to the packaged, provenance-tagged data (bikes, surfaces, sources)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from .physics import fork_offset_mm, parse_tyre_size, tyre_radius_from_code

STATUSES = frozenset({"verified", "derived", "unverified", "unpublished", "method"})


def load_json(name: str) -> dict[str, Any]:
    """Load one of the JSON files shipped in ``kammcircle/data``."""
    text = resources.files("kammcircle.data").joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


@dataclass(frozen=True)
class Source:
    id: str
    group: str
    supports: str
    url: str


@dataclass(frozen=True)
class Surface:
    id: str
    label: str
    mu: float
    sources: tuple[str, ...]
    note: str | None = None


@dataclass(frozen=True)
class Bike:
    id: str
    name: str
    wheelbase_mm: float
    ground_clearance_mm: float
    rake_deg: float
    trail_mm: float
    front_tyre: str
    rear_tyre: str
    mass_kg: float
    mass_note: str
    raw: dict[str, Any]

    @property
    def front_wheel_radius_mm(self) -> float:
        return tyre_radius_from_code(self.front_tyre)

    @property
    def rear_wheel_radius_mm(self) -> float:
        return tyre_radius_from_code(self.rear_tyre)

    @property
    def fork_offset_mm(self) -> float:
        """Back-solved from the published rake and trail; no manufacturer publishes it."""
        return fork_offset_mm(self.rake_deg, self.front_wheel_radius_mm, self.trail_mm)

    @property
    def front_weight_share(self) -> float | None:
        """Measured share of the motorcycle's weight on the front wheel, when a source gives one."""
        entry = self.raw.get("front_weight_share") or self.raw.get("derived", {}).get("front_weight_share")
        return None if entry is None or entry.get("value") is None else float(entry["value"])

    @property
    def rear_crown_radius_mm(self) -> float:
        """Half the rear section width: a common approximation of a round tyre profile."""
        return parse_tyre_size(self.rear_tyre).width_mm / 2


@cache
def sources() -> dict[str, Source]:
    return {s["id"]: Source(**s) for s in load_json("sources.json")["sources"]}


@cache
def surfaces() -> tuple[Surface, ...]:
    return tuple(
        Surface(
            id=s["id"],
            label=s["label"],
            mu=float(s["ui_default"]),
            sources=tuple(s.get("source", ())),
            note=s.get("note"),
        )
        for s in load_json("surfaces.json")["surfaces"]
    )


def _bike_mass(raw: dict[str, Any]) -> tuple[float, str]:
    if "kerb_weight_kg" in raw:
        entry = raw["kerb_weight_kg"]
        return float(entry["value"]), f"kerb weight ({entry['definition']})"
    entry = raw["weight_kg"]
    return float(entry["measured_nz_autocar"]), "measured weight (NZ Autocar)"


@cache
def bikes() -> tuple[Bike, ...]:
    result = []
    for raw in load_json("bikes.json")["bikes"]:
        chassis, wheels = raw["chassis"], raw["wheels"]
        mass, note = _bike_mass(raw)
        year = f" ({raw['model_year']})" if "model_year" in raw else ""
        result.append(
            Bike(
                id=raw["id"],
                name=f"{raw['make']} {raw['model']}{year}",
                wheelbase_mm=float(chassis["wheelbase_mm"]),
                ground_clearance_mm=float(chassis["ground_clearance_mm"]),
                rake_deg=float(chassis["rake_deg"]),
                trail_mm=float(chassis["trail_mm"]),
                front_tyre=wheels["front_tyre"],
                rear_tyre=wheels["rear_tyre"],
                mass_kg=mass,
                mass_note=note,
                raw=raw,
            )
        )
    return tuple(result)


def bike(bike_id: str) -> Bike:
    for b in bikes():
        if b.id == bike_id:
            return b
    raise KeyError(bike_id)
