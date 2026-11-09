"""Steering geometry and the effect of lowering one or both ends of the bike.

Rake is the steering axis's angle from vertical; trail is the ground distance from where the steering axis
meets the road to the front contact patch, which sits behind it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .units import deg2rad, rad2deg


def trail_mm(rake_deg: float, wheel_radius_mm: float, fork_offset_mm: float) -> float:
    """Mechanical trail: (R·sin θ − d) / cos θ, with R the front tyre radius and d the fork offset."""
    t = deg2rad(rake_deg)
    return (wheel_radius_mm * math.sin(t) - fork_offset_mm) / math.cos(t)


def fork_offset_mm(rake_deg: float, wheel_radius_mm: float, trail: float) -> float:
    """Fork offset back-solved from a published rake and trail: d = R·sin θ − trail·cos θ."""
    t = deg2rad(rake_deg)
    return wheel_radius_mm * math.sin(t) - trail * math.cos(t)


def pitch_change_deg(rear_drop_mm: float, front_drop_mm: float, wheelbase_mm: float) -> float:
    """Chassis pitch caused by lowering, in degrees; positive is nose up (rear lower than front)."""
    if wheelbase_mm <= 0:
        raise ValueError("wheelbase_mm must be positive")
    return rad2deg(math.atan((rear_drop_mm - front_drop_mm) / wheelbase_mm))


def rake_after_lowering_deg(
    rake_deg: float, rear_drop_mm: float, front_drop_mm: float, wheelbase_mm: float
) -> float:
    """Rake after lowering: a rear drop adds rake (slower steering), a front drop removes it (quicker)."""
    return rake_deg + pitch_change_deg(rear_drop_mm, front_drop_mm, wheelbase_mm)


def clearance_loss_mm(rear_drop_mm: float, front_drop_mm: float, position_from_front: float = 0.5) -> float:
    """Approximate ground-clearance loss at a point along the wheelbase (0 = front axle, 1 = rear axle)."""
    return front_drop_mm * (1 - position_from_front) + rear_drop_mm * position_from_front


@dataclass(frozen=True)
class LoweringResult:
    rake_deg: float
    trail_mm: float
    ground_clearance_mm: float
    pitch_deg: float


def lowering_geometry(
    *,
    rake_deg: float,
    wheel_radius_mm: float,
    fork_offset_mm: float,
    wheelbase_mm: float,
    ground_clearance_mm: float,
    rear_drop_mm: float = 0.0,
    front_drop_mm: float = 0.0,
) -> LoweringResult:
    """Rake, trail and ground clearance after lowering the rear and/or the front.

    Not modelled: the change in linkage leverage ratio that a rear lowering link causes, sag, and the
    difference between rear-axle drop and seat drop.
    """
    pitch = pitch_change_deg(rear_drop_mm, front_drop_mm, wheelbase_mm)
    rake = rake_deg + pitch
    return LoweringResult(
        rake_deg=rake,
        trail_mm=trail_mm(rake, wheel_radius_mm, fork_offset_mm),
        ground_clearance_mm=ground_clearance_mm - clearance_loss_mm(rear_drop_mm, front_drop_mm),
        pitch_deg=pitch,
    )
