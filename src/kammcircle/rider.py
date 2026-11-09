"""The rider's and the bike's variables: the values a user measures or chooses, rather than catalogue data.

The defaults are example values, not data about any real rider or bike. Royal Enfield publishes no
centre-of-gravity heights and no lean angles, so the app asks for them and says when an example is in use.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class RiderSetup:
    rider_mass_kg: float = 80.0
    """Rider in riding gear."""
    rider_cog_height_mm: float = 1000.0
    """Height of the rider's centre of gravity above the road, seated, bike upright (example value)."""
    bike_cog_height_mm: float = 550.0
    """Height of the bike's own centre of gravity above the road (example value; unpublished)."""
    tyre_crown_radius_mm: float = 70.0
    """Radius of the tyre's cross-section at the crown; about half the section width."""
    peg_height_mm: float = 0.0
    """Footpeg tip height above the road, rider aboard, bike upright; 0 means not measured."""
    peg_lateral_mm: float = 0.0
    """Footpeg tip's lateral distance from the tyre centreline; 0 means not measured."""

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> RiderSetup:
        known = {f.name: f.type for f in fields(cls)}
        clean = {}
        for name, value in values.items():
            if name in known:
                try:
                    clean[name] = float(value)
                except (TypeError, ValueError):
                    continue
        return cls(**clean)

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @property
    def pegs_measured(self) -> bool:
        return self.peg_height_mm > 0 and self.peg_lateral_mm > 0

    def is_example(self, name: str) -> bool:
        """True while a field still holds its example default."""
        return getattr(self, name) == getattr(RiderSetup(), name)
