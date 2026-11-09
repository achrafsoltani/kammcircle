"""Physics regression anchors (hand-checked values) and independent constructions of the derived formulas."""

import math

import pytest

from kammcircle import physics as P

near = pytest.approx


# ─── Regression anchors: hand-checked reference values ──────────────────────


def test_45_degrees_of_lean_is_1_g():
    v_1g = P.ms_to_kmh(math.sqrt(P.G * 50))
    assert P.lateral_g(v_1g, 50) == near(1, abs=1e-9)
    assert P.lean_angle_deg(v_1g, 50) == near(45, abs=1e-9)


def test_60_kmh_on_a_50_m_bend_needs_29_5_degrees():
    assert P.lateral_g(60, 50) == near(0.566, abs=0.001)
    assert P.lean_angle_deg(60, 50) == near(29.5, abs=0.05)


def test_grip_limited_lean_is_atan_mu():
    assert P.max_lean_deg(1.0) == near(45, abs=1e-9)
    assert P.max_lean_deg(1.2) == near(50.2, abs=0.05)
    assert P.max_lean_deg(0.6) == near(31.0, abs=0.05)
    assert P.max_lean_deg(0.3) == near(16.7, abs=0.05)


def test_friction_circle():
    assert P.grip_usage(0.6, 0.8, 1.0) == near(1.0, abs=1e-9)
    assert P.max_corner_speed_kmh(50, 1.0) == near(79.7, abs=0.1)
    assert P.max_corner_speed_kmh(50, 1.0, 0.6) == near(P.ms_to_kmh(math.sqrt(0.8 * P.G * 50)), abs=1e-9)
    assert P.max_corner_speed_kmh(50, 0.5, 0.5) == 0


def test_tyre_width_correction_collapses_to_ideal_for_a_zero_width_tyre():
    assert P.lean_angle_with_tyre_deg(60, 50, 0, 600) == near(P.lean_angle_deg(60, 50), abs=1e-9)
    assert P.lean_angle_with_tyre_deg(60, 50, 70, 600) > P.lean_angle_deg(60, 50)


def test_rider_offset_inside_less_outside_more_zero_same():
    base = dict(combined_lean_deg=30, bike_mass_kg=196, bike_cog_height_mm=550, rider_mass_kg=90, rider_cog_height_mm=1000)
    assert P.bike_lean_for_rider_offset_deg(**base, rider_offset_mm=0) == near(30, abs=1e-9)
    assert P.bike_lean_for_rider_offset_deg(**base, rider_offset_mm=150) < 30
    assert P.bike_lean_for_rider_offset_deg(**base, rider_offset_mm=-150) > 30


def test_clearance_angle_from_peg_geometry():
    assert P.clearance_angle_deg(300, 300) == near(45, abs=1e-9)


def test_tyre_sizes():
    assert P.parse_tyre_size("140/80 R 17") == P.TyreSize(140, 80, 17)
    assert P.parse_tyre_size("90/90-21") == P.TyreSize(90, 90, 21)
    assert P.parse_tyre_size("150/70 B17 69H") == P.TyreSize(150, 70, 17)
    assert P.tyre_diameter_mm(90, 90, 21) == near(695.4, abs=0.01)
    assert P.tyre_diameter_mm(140, 80, 17) == near(655.8, abs=0.01)
    assert P.tyre_diameter_mm(100, 90, 19) == near(662.6, abs=0.01)
    assert P.tyre_diameter_mm(120, 90, 17) == near(647.8, abs=0.01)
    assert P.tyre_sidewall_mm(120, 90) - P.tyre_sidewall_mm(120, 80) == near(12, abs=1e-9)
    with pytest.raises(ValueError):
        P.parse_tyre_size("twenty-one inch")


def test_himalayan_450_geometry_reproduces_published_rake_and_trail():
    radius = P.tyre_radius_from_code("90/90-21")
    assert radius == near(347.7, abs=0.01)
    offset = P.fork_offset_mm(26, radius, 124)
    assert offset == near(41.0, abs=0.1)
    assert P.trail_mm(26, radius, 41) == near(124, abs=0.5)


def test_lowering_30_mm_on_the_himalayan_450():
    base = dict(rake_deg=26, wheel_radius_mm=347.7, fork_offset_mm=41, wheelbase_mm=1510, ground_clearance_mm=230)
    rear = P.lowering_geometry(**base, rear_drop_mm=30)
    assert rear.rake_deg == near(27.14, abs=0.01)
    assert rear.trail_mm == near(132, abs=0.5)
    assert rear.ground_clearance_mm == near(215, abs=1e-9)
    front = P.lowering_geometry(**base, front_drop_mm=30)
    assert front.rake_deg == near(24.86, abs=0.01)
    assert front.trail_mm == near(116, abs=0.5)
    both = P.lowering_geometry(**base, rear_drop_mm=30, front_drop_mm=30)
    assert both.rake_deg == near(26, abs=1e-9)
    assert both.trail_mm == near(124, abs=0.5)
    assert both.ground_clearance_mm == near(200, abs=1e-9)


# ─── Independent constructions: check the formulas, not just their outputs ──


@pytest.mark.parametrize("speed, radius, t, h", [(60, 50, 70, 600), (100, 80, 60, 650), (40, 15, 75, 700)])
def test_tyre_width_lean_puts_the_road_force_through_the_cog(speed, radius, t, h):
    """Build the leaned bike explicitly and check that the contact-point-to-CoG line leans at atan(a/g)."""
    phi = math.radians(P.lean_angle_with_tyre_deg(speed, radius, t, h))
    # Crown centre C sits directly above the contact point P, at height t. The CoG lies in the wheel plane,
    # (h − t) from C, so the wheel plane leans at phi.
    cog_x = (h - t) * math.sin(phi)
    cog_y = t + (h - t) * math.cos(phi)
    effective = math.atan2(cog_x, cog_y)
    assert math.degrees(effective) == near(P.lean_angle_deg(speed, radius), abs=1e-9)


def test_tyre_width_hand_value():
    # φ0 = atan(0.5663) = 29.52°; asin(70·sin φ0 / 530) = 3.73°; φ ≈ 33.25°.
    assert P.lean_angle_with_tyre_deg(60, 50, 70, 600) == near(33.25, abs=0.02)


def test_tyre_width_rejects_impossible_geometry():
    with pytest.raises(ValueError):
        P.lean_angle_with_tyre_deg(60, 50, 700, 600)


@pytest.mark.parametrize("offset", [-250, -100, 0, 120, 300])
def test_rider_offset_keeps_the_combined_cog_on_the_combined_lean_line(offset):
    m_b, h_b, m_r, h_r, combined = 196, 550, 80, 1000, 32
    bike = math.radians(
        P.bike_lean_for_rider_offset_deg(
            combined_lean_deg=combined, bike_mass_kg=m_b, bike_cog_height_mm=h_b,
            rider_mass_kg=m_r, rider_cog_height_mm=h_r, rider_offset_mm=offset,
        )
    )
    # Bike frame: x towards the inside of the turn, y up the bike's plane. Rotate both CoGs by the bike lean.
    def world(x, y):
        return x * math.cos(bike) + y * math.sin(bike), -x * math.sin(bike) + y * math.cos(bike)

    bx, by = world(0, h_b)
    rx, ry = world(offset, h_r)
    cx, cy = (m_b * bx + m_r * rx) / (m_b + m_r), (m_b * by + m_r * ry) / (m_b + m_r)
    assert math.degrees(math.atan2(cx, cy)) == near(combined, abs=1e-9)


def test_combined_cog_height():
    assert P.combined_cog_height_mm(196, 550, 80, 1000) == near((196 * 550 + 80 * 1000) / 276)


def test_max_corner_speed_sits_exactly_on_the_friction_circle():
    for mu, brake in [(1.0, 0.0), (0.6, 0.3), (0.55, 0.5)]:
        v = P.max_corner_speed_kmh(60, mu, brake)
        assert P.grip_usage(P.lateral_g(v, 60), brake, mu) == near(1.0, abs=1e-9)


def test_lean_and_lateral_g_round_trip():
    for lean in (5, 29.5, 45, 52):
        assert P.lean_from_lateral_g_deg(P.lateral_g_from_lean(lean)) == near(lean, abs=1e-9)


def test_scram_411_fork_offset_is_back_solved_from_its_published_rake_and_trail():
    radius = P.tyre_radius_from_code("100/90-19 57S")
    assert radius == near(331.3, abs=0.01)
    assert P.fork_offset_mm(26.2, radius, 104.6) == near(52.4, abs=0.05)
