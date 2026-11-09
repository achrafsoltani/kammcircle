"""Rank front-and-rear tyre pairs for a motorcycle from the data held: the makers' road/off-road classifications,
load and speed ratings, Moroccan availability and price.

No maker publishes grip curves for these tyres, so the ranking never claims that one tyre brakes or corners better
than another; it matches each tyre's classification to the rider's share of unpaved riding and applies the hard
limits. The rules are in docs/physics.md, section 13.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import catalogue

G = 9.81


@dataclass(frozen=True)
class PairAdvice:
    front: catalogue.TyreListing
    rear: catalogue.TyreListing
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Advice:
    pairs: tuple[PairAdvice, ...]
    excluded: tuple[str, ...]  # one line per tyre left out, with the reason


def _class_score(listing: catalogue.TyreListing, unpaved_pct: float) -> tuple[float, str]:
    off = listing.product.offroad_pct
    if off is None:
        return 30.0, f"{listing.product.name}: no road/off-road split published"
    return max(0.0, 100.0 - 2.0 * abs(off - unpaved_pct)), f"{listing.product.name}: {100 - off}/{off} for your {unpaved_pct:.0f} % unpaved"


def _mixing_allowed(a: catalogue.TyreProduct, b: catalogue.TyreProduct) -> bool:
    family = {"mitas-enduro-trail-plus", "mitas-e07"}  # Mitas: E-07/E-07+ and Enduro Trail 60/40 and 50/50 mix
    return a.id in family and b.id in family


def rank_pairs(
    bike: catalogue.Bike, unpaved_pct: float, *, in_stock_only: bool = False, keep_ratings: bool = True,
    static_loads_n: tuple[float, float] | None = None,
) -> Advice:
    oe = catalogue.original_tyres(bike)
    excluded: list[str] = []

    def eligible(listing: catalogue.TyreListing, original: catalogue.TyreListing, load_n: float | None) -> bool:
        reason = None
        if keep_ratings:
            if listing.li is None or listing.ss is None:
                reason = "load or speed rating not stated"
            elif listing.li < (original.li or 0):
                reason = f"load index {listing.li} below the original {original.li}"
            elif (listing.speed_kmh or 0) < (original.speed_kmh or 0):
                reason = f"speed {listing.ss} ({listing.speed_kmh:.0f} km/h) below the original {original.ss} ({original.speed_kmh:.0f} km/h)"
        if reason is None and load_n is not None and listing.load_kg is not None and load_n / G > listing.load_kg:
            reason = f"your load at rest, {load_n / G:.0f} kg, exceeds its {listing.load_kg:.0f} kg rating"
        if reason is None and in_stock_only and not listing.available_in_morocco:
            reason = "not seen in stock in Morocco"
        if reason:
            excluded.append(f"{listing.name}: {reason}")
        return reason is None

    loads = static_loads_n or (None, None)
    fronts = [t for t in catalogue.listings_for(bike.front_tyre, "front") if eligible(t, oe.front, loads[0])]
    rears = [t for t in catalogue.listings_for(bike.rear_tyre, "rear") if eligible(t, oe.rear, loads[1])]

    pairs = []
    for front in fronts:
        for rear in rears:
            score_f, why_f = _class_score(front, unpaved_pct)
            score_r, why_r = _class_score(rear, unpaved_pct)
            score = (score_f + score_r) / 2
            reasons = [why_f] if front.product == rear.product else [why_f, why_r]
            if front.product == rear.product:
                score += 10
                reasons.append("matched front and rear")
            elif _mixing_allowed(front.product, rear.product):
                reasons.append("mixed models that the maker says may be mixed")
            else:
                score -= 10
                reasons.append("mixed models: check the makers' advice before mixing")
            available = [t for t in (front, rear) if t.available_in_morocco]
            score += 5 * len(available)
            if available:
                reasons.append("seen on sale in Morocco: " + ", ".join(
                    f"{t.product.name} {t.best_price_mad:.0f} DH" if t.best_price_mad else t.product.name for t in available))
            prices = [t.best_price_mad for t in (front, rear)]
            if all(p is not None for p in prices):
                score -= sum(prices) / 1000  # a tie-breaker, not a reason to prefer a tyre
                reasons.append(f"about {sum(prices):.0f} DH for the pair")
            pairs.append(PairAdvice(front, rear, round(score, 1), tuple(reasons)))
    pairs.sort(key=lambda a: -a.score)
    return Advice(tuple(pairs), tuple(excluded))
