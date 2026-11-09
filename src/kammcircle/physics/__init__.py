"""Pure physics functions for motorcycle lean, grip, rider position, steering geometry and tyre sizes.

Every function is documented with its formula; derivations and worked numbers are in ``docs/physics.md``.
"""

from .cornering import (
    bike_lean_for_rider_offset_deg,
    clearance_angle_deg,
    combined_cog_height_mm,
    grip_usage,
    lateral_g,
    lateral_g_from_lean,
    lean_angle_deg,
    lean_angle_with_tyre_deg,
    lean_from_lateral_g_deg,
    max_corner_speed_kmh,
    max_lean_deg,
)
from .geometry import (
    LoweringResult,
    clearance_loss_mm,
    fork_offset_mm,
    lowering_geometry,
    pitch_change_deg,
    rake_after_lowering_deg,
    trail_mm,
)
from .tyres import TyreSize, parse_tyre_size, tyre_diameter_mm, tyre_radius_from_code, tyre_sidewall_mm
from .units import G, deg2rad, kmh_to_ms, ms_to_kmh, rad2deg

__all__ = [
    "G",
    "LoweringResult",
    "TyreSize",
    "bike_lean_for_rider_offset_deg",
    "clearance_angle_deg",
    "clearance_loss_mm",
    "combined_cog_height_mm",
    "deg2rad",
    "fork_offset_mm",
    "grip_usage",
    "kmh_to_ms",
    "lateral_g",
    "lateral_g_from_lean",
    "lean_angle_deg",
    "lean_angle_with_tyre_deg",
    "lean_from_lateral_g_deg",
    "lowering_geometry",
    "max_corner_speed_kmh",
    "max_lean_deg",
    "ms_to_kmh",
    "parse_tyre_size",
    "pitch_change_deg",
    "rad2deg",
    "rake_after_lowering_deg",
    "trail_mm",
    "tyre_diameter_mm",
    "tyre_radius_from_code",
    "tyre_sidewall_mm",
]
