"""Typed access to the packaged, provenance-tagged data (bikes, surfaces, sources)."""

from __future__ import annotations

import json
import re
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


# ─── tyres ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TyreProduct:
    id: str
    brand: str
    model: str
    road_offroad_pct: tuple[int, int] | None
    note: str
    mixing: str | None = None

    @property
    def name(self) -> str:
        """Brand and model without the catalogue's parenthetical notes."""
        return f"{self.brand} {re.sub(r' [(].*?[)]', '', self.model)}"

    @property
    def offroad_pct(self) -> int | None:
        return None if self.road_offroad_pct is None else self.road_offroad_pct[1]


@dataclass(frozen=True)
class Offer:
    retailer: str
    source: str
    price_mad: float | None
    in_stock: bool | None  # None: the retailer shows no stock mark per product
    checked: str


@dataclass(frozen=True)
class TyreListing:
    """One size of one tyre: the unit the simulator fits to a wheel."""

    id: str
    product: TyreProduct
    position: str  # "front", "rear" or "front/rear"
    size: str
    li: int | None
    ss: str | None
    type: str
    design: tuple[float, float] | None  # E.T.R.T.O. design section width and overall diameter, mm
    offers: tuple[Offer, ...]
    raw: dict[str, Any]

    @property
    def name(self) -> str:
        rating = f" {self.li or ''}{self.ss or ''}".rstrip()
        return f"{self.product.name} {self.size}{rating} {self.type}".strip()

    @property
    def fits_front(self) -> bool:
        return "front" in self.position

    @property
    def fits_rear(self) -> bool:
        return "rear" in self.position

    @property
    def radius_mm(self) -> float:
        """Unloaded radius: half the maker's design diameter when published, otherwise the nominal size."""
        return self.design[1] / 2 if self.design else tyre_radius_from_code(self.size)

    @property
    def crown_radius_mm(self) -> float:
        """Half the section width (design width when published): the round-profile approximation of section 4."""
        width = self.design[0] if self.design else parse_tyre_size(self.size).width_mm
        return width / 2

    @property
    def load_kg(self) -> float | None:
        return None if self.li is None else tyre_tables()[0].get(str(self.li))

    @property
    def speed_kmh(self) -> float | None:
        return None if self.ss is None else tyre_tables()[1].get(self.ss)

    @property
    def available_in_morocco(self) -> bool:
        return any(o.in_stock is not False for o in self.offers)

    @property
    def best_price_mad(self) -> float | None:
        prices = [o.price_mad for o in self.offers if o.price_mad is not None]
        return min(prices) if prices else None


@cache
def tyre_tables() -> tuple[dict[str, float], dict[str, float]]:
    data = load_json("tyres.json")
    load = {k: float(v) for k, v in data["load_index_kg"].items() if k != "source"}
    speed = {k: float(v) for k, v in data["speed_symbol_kmh"].items() if k != "source"}
    return load, speed


@cache
def tyre_products() -> dict[str, TyreProduct]:
    result = {}
    for raw in load_json("tyres.json")["tyres"]:
        split = raw.get("road_offroad_pct")
        result[raw["id"]] = TyreProduct(
            id=raw["id"], brand=raw["brand"], model=raw["model"],
            road_offroad_pct=None if split is None else (int(split[0]), int(split[1])),
            note=raw.get("note", ""), mixing=raw.get("mixing"),
        )
    return result


@cache
def tyre_listings() -> tuple[TyreListing, ...]:
    products = tyre_products()
    result = []
    for raw in load_json("tyres.json")["listings"]:
        design = raw.get("design")
        result.append(TyreListing(
            id=raw["id"], product=products[raw["tyre"]], position=raw["position"], size=raw["size"],
            li=raw.get("li"), ss=raw.get("ss"), type=raw.get("type", ""),
            design=None if design is None else (float(design[0]), float(design[1])),
            offers=tuple(Offer(o["retailer"], o["source"][0], o.get("price_mad"), o.get("in_stock"), o["checked"])
                         for o in raw.get("offers", [])),
            raw=raw,
        ))
    return tuple(result)


def tyre_listing(listing_id: str) -> TyreListing:
    for listing in tyre_listings():
        if listing.id == listing_id:
            return listing
    raise KeyError(listing_id)


def listings_for(size_code: str, position: str) -> list[TyreListing]:
    """Every listed tyre of exactly this size that the maker allows in this position."""
    wanted = parse_tyre_size(size_code)
    return [t for t in tyre_listings()
            if parse_tyre_size(t.size) == wanted and position in t.position]


@dataclass(frozen=True)
class TyreChoice:
    front: TyreListing
    rear: TyreListing


def original_tyres(bike: Bike) -> TyreChoice:
    oe = bike.raw["oe_listings"]
    return TyreChoice(tyre_listing(oe["front"]), tyre_listing(oe["rear"]))
