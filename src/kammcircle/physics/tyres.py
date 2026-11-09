"""Tyre size arithmetic from the sidewall code (for example "140/80 R17" or "90/90-21")."""

from __future__ import annotations

import re
from dataclasses import dataclass

MM_PER_INCH = 25.4

# The rim is always two digits (10 to 23 in); a load and speed index may follow ("17 69H" → "1769H").
_SIZE = re.compile(r"^(\d+)/(\d+)[-A-Z]*(\d{2})", re.IGNORECASE)


@dataclass(frozen=True)
class TyreSize:
    width_mm: int
    aspect_pct: int
    rim_in: int


def parse_tyre_size(code: str) -> TyreSize:
    """Parse "140/80 R 17", "90/90-21" or "150/70 B17 69H" into width, aspect ratio and rim diameter."""
    match = _SIZE.match(re.sub(r"\s+", "", str(code)))
    if not match:
        raise ValueError(f"Unrecognised tyre size: {code}")
    return TyreSize(int(match[1]), int(match[2]), int(match[3]))


def tyre_sidewall_mm(width_mm: float, aspect_pct: float) -> float:
    """Sidewall height = width × aspect ratio."""
    return width_mm * aspect_pct / 100


def tyre_diameter_mm(width_mm: float, aspect_pct: float, rim_in: float) -> float:
    """Nominal overall diameter = 2 × sidewall + rim. Real tyres differ by a few per cent."""
    return 2 * tyre_sidewall_mm(width_mm, aspect_pct) + MM_PER_INCH * rim_in


def tyre_radius_from_code(code: str) -> float:
    size = parse_tyre_size(code)
    return tyre_diameter_mm(size.width_mm, size.aspect_pct, size.rim_in) / 2
