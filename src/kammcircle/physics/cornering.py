"""Steady cornering: lean angle, grip limit, the friction circle, rider position and hard-part clearance.

Model: steady speed on a constant radius over a flat road. Unless a function says otherwise, the bike and
rider are a single point mass on a zero-width tyre. Derivations and worked numbers are in ``docs/physics.md``.
"""

from __future__ import annotations

import math

from .units import G, deg2rad, kmh_to_ms, ms_to_kmh, rad2deg


def lateral_g(speed_kmh: float, radius_m: float) -> float:
    """Lateral acceleration, in g, of a steady turn: a = v² / r."""
    if radius_m <= 0:
        raise ValueError("radius_m must be positive")
    v = kmh_to_ms(speed_kmh)
    return v * v / (G * radius_m)


def lean_angle_deg(speed_kmh: float, radius_m: float) -> float:
    """Ideal lean angle: tan θ = v² / (g·r), so 45° corresponds to 1 g.

    Measured leans usually come out larger, mainly because a real tyre has width (see
    :func:`lean_angle_with_tyre_deg`); a rider who hangs off the inside lets the bike itself lean less (see
    :func:`bike_lean_for_rider_offset_deg`).
    """
    return rad2deg(math.atan(lateral_g(speed_kmh, radius_m)))


def lean_angle_with_tyre_deg(
    speed_kmh: float, radius_m: float, crown_radius_mm: float, cog_height_mm: float
) -> float:
    """Lean angle of the wheel plane when the tyre has a round cross-section of radius ``t``.

    φ = φ0 + asin( t·sin φ0 / (h − t) ), where φ0 is the ideal lean, t the tyre crown radius and h the
    height of the combined centre of gravity above the ground with the bike upright.

    Derivation: as the bike leans, the contact point moves to the inside of the wheel plane, directly below
    the centre of the tyre's cross-section. The road's force must still point at the centre of gravity, so
    the line from the contact point to the CoG leans at φ0. The law of sines in the triangle formed by the
    contact point, the crown centre and the CoG gives the expression above.
    """
    if crown_radius_mm < 0:
        raise ValueError("crown_radius_mm cannot be negative")
    if cog_height_mm <= crown_radius_mm:
        raise ValueError("cog_height_mm must exceed crown_radius_mm")
    phi0 = math.atan(lateral_g(speed_kmh, radius_m))
    extra = math.asin(crown_radius_mm * math.sin(phi0) / (cog_height_mm - crown_radius_mm))
    return rad2deg(phi0 + extra)


def combined_cog_height_mm(
    bike_mass_kg: float, bike_cog_height_mm: float, rider_mass_kg: float, rider_cog_height_mm: float
) -> float:
    """Height of the combined (bike + rider) centre of gravity, bike upright, rider centred."""
    total = bike_mass_kg + rider_mass_kg
    if total <= 0:
        raise ValueError("total mass must be positive")
    return (bike_mass_kg * bike_cog_height_mm + rider_mass_kg * rider_cog_height_mm) / total


def max_lean_deg(mu: float) -> float:
    """Grip-limited maximum lean with no braking: tan θmax = μ."""
    return rad2deg(math.atan(mu))


def grip_usage(lat_g: float, brake_g: float, mu: float) -> float:
    """Share of the friction circle in use: √(lateral² + braking²) / μ. At 1 or more the tyre slides."""
    if mu <= 0:
        raise ValueError("mu must be positive")
    return math.hypot(lat_g, brake_g) / mu


def max_corner_speed_kmh(radius_m: float, mu: float, brake_g: float = 0.0) -> float:
    """Highest steady speed through radius r while braking at ``brake_g``, which uses part of the circle."""
    if brake_g >= mu:
        return 0.0
    lat_available = math.sqrt(mu * mu - brake_g * brake_g)
    return ms_to_kmh(math.sqrt(lat_available * G * radius_m))


def bike_lean_for_rider_offset_deg(
    *,
    combined_lean_deg: float,
    bike_mass_kg: float,
    bike_cog_height_mm: float,
    rider_mass_kg: float,
    rider_cog_height_mm: float,
    rider_offset_mm: float,
) -> float:
    """Bike lean when the rider moves off the bike's plane, for a fixed combined lean.

    The corner fixes the combined lean. In the bike's frame the combined CoG is a fixed vector, so
    φ_bike = φ_combined − atan( m_r·s / (m_b·h_b + m_r·h_r) ).

    ``rider_offset_mm`` (s): positive moves the rider's CoG towards the inside of the turn (hanging off on
    tarmac: the bike leans less); negative moves it towards the outside (standing on the outside peg on
    gravel: the bike leans more).
    """
    offset = math.atan2(
        rider_mass_kg * rider_offset_mm,
        bike_mass_kg * bike_cog_height_mm + rider_mass_kg * rider_cog_height_mm,
    )
    return combined_lean_deg - rad2deg(offset)


def clearance_angle_deg(peg_height_mm: float, peg_lateral_mm: float) -> float:
    """Lean at which the footpeg tip touches the road: h·cos θ − w·sin θ = 0, so θ = atan(h / w).

    Measure the peg tip's height h and its lateral distance w from the tyre centreline with the rider aboard
    and the bike upright. Tyre width is ignored, so the real angle is a few degrees larger.
    """
    if peg_height_mm <= 0 or peg_lateral_mm <= 0:
        raise ValueError("peg geometry must be positive")
    return rad2deg(math.atan2(peg_height_mm, peg_lateral_mm))


def lean_from_lateral_g_deg(lat_g: float) -> float:
    """Ideal lean for a given lateral acceleration in g."""
    return rad2deg(math.atan(lat_g))


def lateral_g_from_lean(lean_deg: float) -> float:
    """Inverse of :func:`lean_from_lateral_g_deg`."""
    return math.tan(deg2rad(lean_deg))
