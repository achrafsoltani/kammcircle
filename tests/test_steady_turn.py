"""The cornering tyre (Sharp, Evangelou & Limebeer 2004, eqs. 7–31) and the steady-turn solver built on it.

Three independent anchors: the tyre fits against the paper's own figures (7, 8, 10, 11); the solver against the linear
benchmark of Meijaard et al. (2007) in the limit of thin, stiff tyres and small angles, and against the point-mass
tyre-width formula of the Cornering tab; and the whole model against the paper's Figure 20, a GSX-R1000 rebuilt from the
paper's appendix and held at 30° of lean from 7 to 30 m/s.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from kammcircle import catalogue
from kammcircle import physics as P
from kammcircle.rider import RiderSetup
from kammcircle.sim.lateral import BENCHMARK, coefficients, steady_turn
from kammcircle.sim.parameters import cornering_tyres, lateral_parameters, steady_turn_parameters
from kammcircle.sim.steady_turn import (
    BeyondGrip,
    Body,
    TrimModel,
    Wheel,
    grip_limit_speed,
    model_from_whipple,
    pose,
    rotation,
    solve,
    sweep_lateral,
    sweep_speed,
)
from kammcircle.sim.tyre import MotorcycleTyre

DEG = math.pi / 180


def tyres() -> tuple[MotorcycleTyre, MotorcycleTyre]:
    return cornering_tyres(1.3)  # the fits' own peak, as measured


def himalayan():
    return next(b for b in catalogue.bikes() if "himalayan" in b.id)


# ─── the tyre ────────────────────────────────────────────────────────────────


def test_side_force_and_moment_are_symmetric():
    for tyre in tyres():
        for beta, gamma, fz in ((0.03, 0.4, 1500), (-0.08, 0.7, 2600), (0.01, -0.2, 900)):
            assert tyre.side_force(beta, gamma, fz) == pytest.approx(-tyre.side_force(-beta, -gamma, fz), abs=1e-9)
            assert tyre.aligning_moment(beta, gamma, fz) == pytest.approx(-tyre.aligning_moment(-beta, -gamma, fz),
                                                                          abs=1e-9)


def test_slopes_at_the_origin_are_the_cornering_and_camber_stiffnesses():
    """dFy/dβ = Kyα (eq. 10) and dFy/dγ = Kyγ (eq. 12) at zero slip and camber: Dy·Cy·By and Dy·Cγ·Bγ."""
    h = 1e-7
    for tyre in tyres():
        for fz in (800.0, 1600.0, 3200.0):
            slope_beta = (tyre.side_force(h, 0, fz) - tyre.side_force(-h, 0, fz)) / (2 * h)
            slope_gamma = (tyre.side_force(0, h, fz) - tyre.side_force(0, -h, fz)) / (2 * h)
            assert slope_beta == pytest.approx(tyre.cornering_stiffness(0, fz), rel=1e-6)
            assert slope_gamma == pytest.approx(tyre.camber_stiffness(fz), rel=1e-6)


def test_side_force_peaks_at_the_fits_cap_of_1_3():
    """The 120/70 and 180/55 fits were constrained to Dy ≤ 1.3·Fz (§4.2); with camber the sine reaches its peak."""
    for tyre in tyres():
        for fz in (800.0, 1600.0, 2400.0):
            peak = max(tyre.side_force(b / 1000, 30 * DEG, fz) for b in range(-50, 400))
            assert peak == pytest.approx(1.3 * fz, rel=2e-3)


def test_camber_curves_cross_zero_where_figures_7_and_8_show():
    """At 1600 N and 45° camber both fits give zero side force at a sideslip of about −0.06 (read from the figures);
    camber thrust grows with camber."""
    for tyre in tyres():
        lo, hi = -0.25, 0.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            lo, hi = (lo, mid) if tyre.side_force(mid, 45 * DEG, 1600) > 0 else (mid, hi)
        assert -0.075 < 0.5 * (lo + hi) < -0.055
        thrust = [tyre.side_force(0, g * DEG, 1600) for g in (0, 10, 20, 30, 40, 45)]
        assert thrust == sorted(thrust) and thrust[0] == 0


@pytest.mark.parametrize("which, fz, camber, peak", [
    ("front", 2400, 0, 42), ("front", 2400, 45, 90), ("front", 3200, 0, 72), ("front", 3200, 45, 123),
    ("rear", 2400, 0, 45), ("rear", 2400, 45, 92), ("rear", 3200, 0, 65), ("rear", 3200, 45, 133),
])
def test_aligning_moment_peaks_match_figures_10_and_11(which, fz, camber, peak):
    tyre = tyres()[0 if which == "front" else 1]
    top = max(tyre.aligning_moment(b / 1000, camber * DEG, fz) for b in range(-200, 201))
    assert top == pytest.approx(peak, rel=0.08)


def test_published_constraints_hold_in_the_stated_ranges():
    """§4.2: Cy + Cγ < 2, Ey < 1 for camber under 70°; §4.3: Bt > 0, Et < 1 for loads under 11 kN, sideslip under
    45° and camber under 60°."""
    for tyre in tyres():
        assert tyre.cy + tyre.c_gamma < 2
        for g in range(-69, 70, 3):
            gamma = g * DEG
            for sign in (-1, 1):
                assert tyre.pey1 + tyre.pey2 * gamma ** 2 + tyre.pey4 * gamma * sign < 1
        for fz in (500, 2000, 6000, 10900):
            dfz = (fz - tyre.fz0) / tyre.fz0
            for g in range(-59, 60, 4):
                gamma = g * DEG
                bt = (tyre.qbz1 + tyre.qbz2 * dfz) * (1 + tyre.qbz5 * abs(gamma) + tyre.qbz6 * gamma ** 2)
                assert bt > 0
                for b in range(-44, 45, 4):
                    beta = math.tan(b * DEG)
                    et = (tyre.qez1 + tyre.qez2 * dfz) * (1 + tyre.qez5 * gamma * (2 / math.pi)
                                                          * math.atan(bt * tyre.ct * beta))
                    assert et < 1


def test_combined_slip_only_reduces_the_forces():
    for tyre in tyres():
        assert tyre.side_loss(0, 0.05) == 1 and tyre.longitudinal_loss(0, 0) == 1
        for kappa in (-0.1, -0.03, 0.02):
            for beta in (-0.05, 0.02, 0.1):
                assert 0 < tyre.side_loss(kappa, beta) <= 1
                assert 0 < tyre.longitudinal_loss(kappa, beta) <= 1
        fx = -900.0
        kappa = tyre.slip_for_longitudinal_force(fx, 0.02, 1500)
        assert kappa is not None and kappa < 0
        assert tyre.longitudinal_force(kappa, 0.02, 1500) == pytest.approx(fx, abs=1e-6)
        assert tyre.slip_for_longitudinal_force(-3000.0, 0.02, 1500) is None


def test_surface_scaling_keeps_the_stiffnesses_and_scales_the_peaks():
    front, _ = cornering_tyres(1.0)
    wet, _ = cornering_tyres(0.5)
    assert wet.peak_side_force(0.4, 1400) == pytest.approx(0.5 * front.peak_side_force(0.4, 1400))
    assert wet.longitudinal.peak_force(1400) == pytest.approx(0.5 * front.longitudinal.peak_force(1400))
    h = 1e-7
    assert ((wet.side_force(h, 0, 1400) - wet.side_force(-h, 0, 1400))
            == pytest.approx(front.side_force(h, 0, 1400) - front.side_force(-h, 0, 1400), rel=1e-6))


# ─── the steady turn: geometry and independent limits ───────────────────────


def stiff_thin(p, **kwargs) -> TrimModel:
    """Knife-edge wheels on tyres so stiff that they hardly slip, with no camber thrust or aligning moment."""
    base, _ = tyres()
    stiff = replace(base, pdy1=50.0, pky1=2.0e4, pky6=0.0, pky7=0.0, qdz1=0.0, qdz2=0.0, qdz8=0.0, qdz9=0.0,
                    qdz10=0.0, qdz11=0.0)
    return model_from_whipple(p, stiff, stiff, front_crown=0.0, rear_crown=0.0, **kwargs)


def test_contact_points_lie_on_the_road_below_the_crown():
    m, _ = steady_turn_parameters(himalayan(), RiderSetup())
    for lean, steer in ((0.0, 0.0), (0.5, 0.0), (0.6, 0.2), (-0.3, -0.4)):
        ps = pose(m, lean, steer)
        assert ps.rear_contact == pytest.approx((0, 0, 0), abs=1e-12)
        assert ps.front_contact[2] == pytest.approx(0, abs=1e-12)
        # the contact point sits ρ·sin γ inside the wheel plane
        offset = sum((ps.rear_contact[i] - ps.rear_hub[i]) * ps.rear_axle[i] for i in range(3))
        assert offset == pytest.approx(m.rear.crown * math.sin(lean), abs=1e-12)
    upright = pose(m, 0.0, 0.0)
    assert upright.pitch == pytest.approx(0, abs=1e-12)
    assert upright.front_contact[0] == pytest.approx(m.wheelbase, abs=1e-12)


@pytest.mark.parametrize("params, cases", [
    (BENCHMARK, [(3.0, 2000.0), (5.0, 2000.0), (10.0, 2000.0)]),
    (None, [(8.0, 3000.0), (20.0, 3000.0)]),
])
def test_matches_the_benchmark_steady_turn_with_thin_stiff_tyres(params, cases):
    """At small lean, with knife-edge wheels that do not slip, the nonlinear balance must reduce to the linear
    benchmark's steady turn (Meijaard et al. 2007): same lean, steer angle and handlebar torque."""
    if params is None:
        params, _, _ = lateral_parameters(himalayan(), RiderSetup())
    m = stiff_thin(params)
    k = coefficients(params)
    for v, radius in cases:
        trim = solve(m, v, radius=radius)
        linear = steady_turn(k, params, v, radius)
        assert trim.lean == pytest.approx(linear.lean, rel=1e-3)
        assert trim.steer == pytest.approx(linear.steer, rel=1e-3)
        assert trim.steering_torque == pytest.approx(linear.torque, rel=2e-3)


def test_lean_matches_the_tyre_width_formula_for_a_point_mass():
    """Equal crown radii, no wheel or body inertia, a wide circle: the roll balance is the Cornering tab's formula
    φ = φ0 + asin(t·sin φ0 / (h − t)), with φ0 from the centre of mass's own centripetal acceleration."""
    params, _, _ = lateral_parameters(himalayan(), RiderSetup())
    params = replace(params, i_rxx=0, i_ryy=0, i_fxx=0, i_fyy=0, i_bxx=0, i_bxz=0, i_byy=0, i_bzz=0,
                     i_hxx=0, i_hxz=0, i_hyy=0, i_hzz=0)
    base, _ = tyres()
    stiff = replace(base, pdy1=50.0, pky1=2.0e4, pky6=0.0, pky7=0.0, qdz1=0.0, qdz2=0.0, qdz8=0.0, qdz9=0.0,
                    qdz10=0.0, qdz11=0.0)
    crown = 0.06
    m = model_from_whipple(params, stiff, stiff, front_crown=crown, rear_crown=crown)
    for v, radius in ((40.0, 1000.0), (60.0, 1000.0)):
        trim = solve(m, v, radius=radius)
        ps = trim.pose
        parts = [(m.rear_body.mass, ps.rear_cog), (m.front_body.mass, ps.front_cog), (m.rear.mass, ps.rear_hub),
                 (m.front.mass, ps.front_hub)]
        cog = [sum(mass * p[i] for mass, p in parts) / m.mass for i in range(3)]
        alpha = trim.rear.slip_angle
        centre = (radius * math.sin(alpha), radius * math.cos(alpha))
        a_cog = trim.yaw_rate ** 2 * math.hypot(cog[0] - centre[0], cog[1] - centre[1])
        h = -(m.rear_body.mass * m.rear_body.position[2] + m.front_body.mass * m.front_body.position[2]
              - m.rear.mass * m.rear.radius - m.front.mass * m.front.radius) / m.mass
        phi0 = math.atan(a_cog / m.g)
        expected = phi0 + math.asin(crown * math.sin(phi0) / (h - crown))
        assert trim.lean == pytest.approx(expected, abs=2e-4)


def test_hanging_off_matches_the_body_position_formula():
    """Thin, stiff tyres and no inertia: moving the rider s to the inside lowers the bike's lean by
    atan(m_r·s / Σ m·h), the Body position tab's expression."""
    setup = RiderSetup()
    params, _, _ = lateral_parameters(himalayan(), setup)
    params = replace(params, i_rxx=0, i_ryy=0, i_fxx=0, i_fyy=0)
    s = 0.2
    v, radius = 30.0, 1200.0
    straight = solve(stiff_thin(params), v, radius=radius)
    off = solve(stiff_thin(params, rear_offset=setup.rider_mass_kg * s / params.m_b), v, radius=radius)
    ps = straight.pose
    sum_mh = -(params.m_b * params.z_b + params.m_h * params.z_h) + params.m_r * params.r_r + params.m_f * params.r_f
    assert straight.lean - off.lean == pytest.approx(math.atan(setup.rider_mass_kg * s / sum_mh), rel=0.01)
    assert ps is not None


# ─── the steady turn: Sharp et al.'s GSX-R1000 (Figure 20) ──────────────────


def gsxr1000(rider_lean: float = 0.045) -> TrimModel:
    """The Suzuki GSX-R1000 of Sharp, Evangelou & Limebeer (2004), Tables A.I–A.III and Figure 1: x forward from the
    rear contact, z down. The steering axis (ε = 0.4189 rad) passes through the upper front frame's centre of mass p3,
    which gives the machine's 97 mm trail. The rider's upper body (p10) leans in about the hip point p9 by Figure 20's
    0.045 rad. The rear tyre's crown radius is the appendix's 0.095 m (§4.3 says 0.09 m; 0.095 reproduces the figure,
    so the paper's model used it); the front's is 0.06 m."""
    eps, w, r_f, r_r = 0.4189, 1.410, 0.282, 0.297
    trail = 1.164 + 0.77 * math.tan(eps) - w
    sl, cl = math.sin(eps), math.cos(eps)

    def parallel(mass, p, c):
        dx, dy, dz = (p[i] - c[i] for i in range(3))
        return mass * (dy * dy + dz * dz), mass * (dx * dx + dz * dz), mass * (dx * dx + dy * dy), -mass * dx * dz

    def combine(parts):
        mass = sum(x[0] for x in parts)
        c = tuple(sum(x[0] * x[1][i] for x in parts) / mass for i in range(3))
        xx = yy = zz = xz = 0.0
        for m_i, p, (jx, jy, jz, jxz) in parts:
            a = parallel(m_i, p, c)
            xx, yy, zz, xz = xx + jx + a[0], yy + jy + a[1], zz + jz + a[2], xz + jxz + a[3]
        return Body(mass, c, ((xx, 0, xz), (0, yy, 0), (xz, 0, zz)))

    across, lateral, along = 1.341, 1.584, 0.4125  # Iff_str, principal axes across and along the forks
    upper = (across * cl * cl + along * sl * sl, lateral, across * sl * sl + along * cl * cl, (along - across) * sl * cl)
    front = combine([(9.99, (1.164, 0.0, -0.77), upper), (7.25, (1.365, 0.0, -0.324), (0, 0, 0, 0))])
    hip = (0.364, 0.0, -0.8438)
    torso = rotation((1.0, 0.0, 0.0), rider_lean)
    rel = (0.415 - hip[0], 0.0, -1.14 - hip[2])
    p10 = tuple(hip[i] + sum(torso[i][j] * rel[j] for j in range(3)) for i in range(3))
    rear = combine([(165.13, (0.6779, 0.0, -0.4724), (11.085, 22.013, 14.982, -3.691)),
                    (33.68, p10, (1.428, 1.347, 0.916, 0.443)),
                    (8.0, (0.196, 0.0, -0.3113), (0.02, 0.259, 0.259, 0.0))])
    front_tyre, rear_tyre = tyres()
    return TrimModel(wheelbase=w, trail=trail, rake=eps, rear_body=rear, front_body=front,
                     rear=Wheel(r_r, 0.095, 14.7, 0.638, 0.383, rear_tyre.with_crown_radius(0.095)),
                     front=Wheel(r_f, 0.06, 11.9, 0.484, 0.270, front_tyre), drag_area=0.48 * 0.65)


# Read from Figure 20 (p. 276) rendered at 300 dpi; precision about ±0.3 N m, ±10 N and ±0.003 rad.
# speed m/s: (steer rad, steer torque N m, front Mz, rear Mz, front Fy, rear Fy, front load, rear load)
FIGURE_20 = {
    7.3: (0.099, -13.0, 21.2, 19.6, 540, 662, 1150, 1300),
    11.0: (0.035, -10.4, 19.7, 20.0, 520, 655, 1145, 1315),
    15.0: (0.012, -9.3, 19.0, 20.2, 510, 655, 1130, 1320),
    19.0: (0.003, -8.8, 18.5, 20.4, 503, 660, 1120, 1330),
    22.5: (-0.002, -8.4, 18.1, 20.5, 495, 662, 1100, 1340),
    30.0: (-0.008, -7.8, 17.4, 20.9, 478, 672, 1070, 1365),
}


def test_reproduces_sharp_figure_20_at_30_degrees_of_lean():
    m = gsxr1000()
    trims = dict(zip(FIGURE_20, sweep_speed(m, 30 * DEG, list(FIGURE_20))))
    for v, (steer, torque, mz_f, mz_r, fy_f, fy_r, n_f, n_r) in FIGURE_20.items():
        t = trims[v]
        assert t is not None
        assert t.steer == pytest.approx(steer, abs=0.004), v
        assert t.steering_torque == pytest.approx(torque, abs=0.5), v
        assert t.front.aligning_moment == pytest.approx(mz_f, abs=0.8), v
        assert t.rear.aligning_moment == pytest.approx(mz_r, abs=0.8), v
        assert t.front.side_force == pytest.approx(fy_f, rel=0.04), v
        assert t.rear.side_force == pytest.approx(fy_r, rel=0.04), v
        assert t.front.load == pytest.approx(n_f, rel=0.03), v
        assert t.rear.load == pytest.approx(n_r, rel=0.03), v
        # "The steer torque required can be seen to be somewhat less than the front tyre aligning moment"
        assert abs(t.steering_torque) < t.front.aligning_moment
    # "[The steer angle] changes sign at just over 20 m/s"
    assert trims[19.0].steer > 0 > trims[22.5].steer


def test_a_slow_tight_turn_needs_no_starting_guess():
    m = gsxr1000()
    t = solve(m, 3.7, lean=30 * DEG)
    assert t.steer == pytest.approx(0.43, abs=0.05)  # Figure 20: the steer rises steeply at low speed
    assert t.steering_torque == pytest.approx(-17.2, abs=1.0)


# ─── the steady turn: behaviour on the catalogue motorcycle ─────────────────


def test_balance_closes_and_the_torque_parts_add_up():
    m, _ = steady_turn_parameters(himalayan(), RiderSetup())
    t = solve(m, 60 / 3.6, radius=50.0)
    assert sum(t.torque_parts.values()) == pytest.approx(-t.steering_torque, abs=1e-9)
    total = t.front.load + t.rear.load
    assert total == pytest.approx(m.mass * m.g, rel=1e-6)  # no aerodynamic lift in the model
    assert t.lateral_g == pytest.approx((60 / 3.6) ** 2 / (50 * m.g))
    assert 0 < t.rear.slip_angle < 2 * DEG and abs(t.front.slip_angle) < 1 * DEG
    assert t.lean > math.atan(t.lateral_g)  # tyre width and the wheels' gyroscopic moment both add lean


def test_braking_in_a_turn_stands_the_motorcycle_up():
    """The front tyre's braking force acts at a contact point that lies inside the steering axis, so it turns the bars
    into the turn: the rider has to push the inside grip harder to hold the line."""
    m, _ = steady_turn_parameters(himalayan(), RiderSetup())
    steady = solve(m, 60 / 3.6, radius=50.0)
    braking = solve(m, 60 / 3.6, radius=50.0, acceleration=-4.0)
    assert braking.torque_parts["tyre_longitudinal"] > steady.torque_parts["tyre_longitudinal"] + 10
    assert braking.steering_torque < steady.steering_torque - 10
    assert braking.front.grip_used > steady.front.grip_used


def test_grip_limit_is_close_to_the_friction_circle_and_raises_beyond_it():
    for mu in (1.0, 0.6, 0.3):
        m, _ = steady_turn_parameters(himalayan(), RiderSetup(), mu=mu)
        v = grip_limit_speed(m, 50.0)
        assert v == pytest.approx(math.sqrt(mu * m.g * 50.0), rel=0.03)
        assert solve(m, 0.97 * v, radius=50.0).rear.grip_used < 1
        with pytest.raises(BeyondGrip):
            solve(m, 1.05 * v, radius=50.0)


def test_cold_tyres_lower_the_grip_limit():
    warm, _ = steady_turn_parameters(himalayan(), RiderSetup())
    cold, _ = steady_turn_parameters(himalayan(), RiderSetup(), grip=(0.9, 0.85))
    assert grip_limit_speed(cold, 50.0) == pytest.approx(math.sqrt(0.85) * grip_limit_speed(warm, 50.0), rel=0.03)


def test_sweeps_cover_the_range():
    m, _ = steady_turn_parameters(himalayan(), RiderSetup())
    by_speed = sweep_speed(m, 30 * DEG, [v / 3.6 for v in range(20, 181, 20)])
    assert all(t is not None for t in by_speed)
    assert by_speed[0].steer > 0 > by_speed[-1].steer  # into the turn at low speed, slightly out at high speed
    by_g = sweep_lateral(m, 60 / 3.6, [0.2, 0.5, 0.8, 1.2])
    assert by_g[-1] is None and all(t is not None for t in by_g[:-1])
    assert by_g[0].rear.slip_angle < by_g[1].rear.slip_angle < by_g[2].rear.slip_angle


def test_tyre_width_and_wheel_spin_explain_the_extra_lean_on_the_example():
    """On the example Himalayan (front crown 45 mm, rear 70 mm), without wheel inertia the lean lies between the
    point-mass formula's values for the two crown radii; the wheels' gyroscopic moment then adds a little lean."""
    setup = RiderSetup()
    m, _ = steady_turn_parameters(himalayan(), setup)
    full = solve(m, 60 / 3.6, radius=50.0)
    still = replace(m, rear=replace(m.rear, spin_inertia=0, diametral_inertia=0),
                    front=replace(m.front, spin_inertia=0, diametral_inertia=0))
    no_spin = solve(still, 60 / 3.6, radius=50.0)
    h = P.combined_cog_height_mm(himalayan().mass_kg, setup.bike_cog_height_mm, setup.rider_mass_kg,
                                 setup.rider_cog_height_mm)
    narrow = P.lean_angle_with_tyre_deg(60, 50, m.front.crown * 1000, h)
    wide = P.lean_angle_with_tyre_deg(60, 50, m.rear.crown * 1000, h)
    assert narrow < math.degrees(no_spin.lean) < wide
    assert 0.2 < math.degrees(full.lean - no_spin.lean) < 1.0
