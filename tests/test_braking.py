"""Braking simulation: the tyre fit, conservation-type checks, the classic limits, and the event logic."""

from dataclasses import replace

import pytest

from kammcircle import catalogue
from kammcircle.rider import RiderSetup
from kammcircle.sim import BrakingParameters, BrakingSim, LongitudinalTyre, braking_parameters, run_braking

near = pytest.approx


@pytest.fixture(scope="module")
def himalayan():
    return catalogue.bike("re-himalayan-450-2026")


def params(bike, mu=1.0, **changes) -> BrakingParameters:
    p, _ = braking_parameters(bike, RiderSetup(), mu)
    return replace(p, **changes) if changes else p


# ─── tyre model ─────────────────────────────────────────────────────────────


def test_tyre_reproduces_the_published_fit_at_nominal_load():
    tyre = LongitudinalTyre()
    assert tyre.coefficient(0.0, 1600) == 0.0
    peak = tyre.peak_braking_slip(1600)
    assert -0.13 < peak < -0.09
    assert -tyre.coefficient(peak, 1600) == near(1.2017, abs=0.002)  # Dx = pDx1·Fz at Fz0, sin(·) = 1
    locked = -tyre.coefficient(-1.0, 1600)
    assert 0.7 < locked < 0.9  # Lambourn & Wesley measured 0.7–0.9 locked, ≈ 1.2 peak, on dry surfaces


def test_tyre_slope_matches_finite_differences():
    tyre = LongitudinalTyre()
    for kappa in (-0.6, -0.12, -0.03, 0.04, 0.2):
        h = 1e-6
        numeric = (tyre.coefficient(kappa + h, 2000) - tyre.coefficient(kappa - h, 2000)) / (2 * h)
        assert tyre.slope(kappa, 2000) == near(numeric, rel=1e-5)


def test_surface_scaling_sets_the_peak_and_keeps_the_slip_stiffness():
    base, wet = LongitudinalTyre(), LongitudinalTyre().for_surface(0.6)
    assert -wet.coefficient(wet.peak_braking_slip(1600), 1600) == near(0.6, abs=0.002)
    assert wet.slope(-1e-6, 1600) == near(base.slope(-1e-6, 1600), rel=1e-3)


def test_load_sensitivity_lowers_the_peak_coefficient():
    tyre = LongitudinalTyre()
    light = -tyre.coefficient(tyre.peak_braking_slip(800), 800)
    heavy = -tyre.coefficient(tyre.peak_braking_slip(3000), 3000)
    assert heavy < light


# ─── dynamics ───────────────────────────────────────────────────────────────


def test_free_rolling_keeps_speed_and_zero_slip(himalayan):
    sim = BrakingSim(params(himalayan), 90)
    sim.run_for(2.0, 0.0, 0.0)
    assert sim.v == near(25.0, abs=1e-9)
    assert sim.kf == near(0.0, abs=1e-9) and sim.kr == near(0.0, abs=1e-9)
    assert sim.nf + sim.nr == near(sim.p.weight, rel=1e-12)
    assert sim.nf == near(sim.p.static_front_load, rel=1e-9)


def test_steady_braking_load_transfer_matches_the_textbook_formula(himalayan):
    p = params(himalayan)
    sim = BrakingSim(p, 100, abs_front=False, abs_rear=False)
    sim.run_for(0.8, 0.45, 0.15)  # moderate, no lock
    decel = -sim.a
    textbook = (p.weight * p.cog_ahead_of_rear + p.mass * decel * p.cog_height) / p.wheelbase
    assert 0.5 * p.g < decel < 0.8 * p.g
    assert sim.nf == near(textbook, rel=0.02)  # the remainder is the wheels' spin inertia
    assert not sim.locked_f and not sim.locked_r


def test_abs_braking_reaches_the_grip_limit_without_locking(himalayan):
    for mu in (1.0, 0.6):
        sim = run_braking(params(himalayan, mu), 100, 1.0, 1.0)
        s = sim.summary()
        assert s.outcome == "stopped"
        assert s.peak_decel_g == near(mu, rel=0.05)
        assert s.mean_decel_g > 0.85 * mu
        assert s.front_locked_s < 0.1


def test_stopping_distance_agrees_with_the_mean_deceleration(himalayan):
    sim = run_braking(params(himalayan), 80, 1.0, 1.0, squeeze_time=0.05)
    s = sim.summary()
    v0 = 80 / 3.6
    assert s.stopping_distance == near(v0 * v0 / (2 * s.mean_decel_g * 9.81), rel=1e-9)
    # No braking can beat v²/(2·μ·g) with the tyre's best coefficient (at the lightest load) ...
    tyre = sim.p.tyre
    best_mu = -tyre.coefficient(tyre.peak_braking_slip(100.0), 100.0)
    assert s.stopping_distance > v0 * v0 / (2 * best_mu * 9.81)
    # ... and the generic ABS, with both levers fully on, stays within 10 % of a skilled rider's best fixed split
    # that never locks a wheel (front 52 %, rear 16 %, found by a grid search over the levers on this setup).
    skilled = run_braking(sim.p, 80, 0.52, 0.16, squeeze_time=0.05, abs_front=False, abs_rear=False).summary()
    assert skilled.front_locked_s == 0 and skilled.rear_locked_s == 0
    assert skilled.stopping_distance < s.stopping_distance < 1.10 * skilled.stopping_distance


def test_a_locked_front_wheel_brakes_worse_than_abs(himalayan):
    locked = run_braking(params(himalayan, 0.6), 80, 1.0, 0.0, abs_front=False, abs_rear=False)
    with_abs = run_braking(params(himalayan, 0.6), 80, 1.0, 0.0)
    assert locked.summary().front_locked_s > 1.0
    assert any("Front wheel locks" in e for _, e in locked.events)
    assert with_abs.summary().stopping_distance < locked.summary().stopping_distance


def test_rear_lift_threshold_follows_l_minus_b_over_h(himalayan):
    """The rear unloads when the deceleration reaches g·(L − b)/h: lift above it, never below."""
    base = params(himalayan, 1.3)
    threshold = base.lift_deceleration_g
    high_cog = replace(base, cog_height=(base.wheelbase - base.cog_ahead_of_rear) / 0.9)  # lifts above 0.9 g
    assert high_cog.lift_deceleration_g == near(0.9)
    lifted = run_braking(high_cog, 80, 1.0, 0.0)
    assert any("Rear wheel lifts" in e for _, e in lifted.events)
    lift_time = next(t for t, e in lifted.events if "Rear wheel lifts" in e)
    decel_at_lift = next(-s.a for s in lifted.trace if s.t >= lift_time - 1e-9) / 9.81
    assert decel_at_lift == near(0.9, abs=0.03)
    gentle = run_braking(base, 80, 0.7, 0.0)
    assert gentle.summary().peak_decel_g < threshold
    assert not any("lifts" in e for _, e in gentle.events)


def test_holding_full_front_brake_past_the_lift_point_goes_over(himalayan):
    sim = run_braking(params(himalayan, 1.3), 100, 1.0, 0.0)
    s = sim.summary()
    assert s.outcome == "pitched over"
    assert s.max_rear_lift_mm > 100
    assert [e for _, e in sim.events][-1].startswith("Pitched over")


def test_a_brief_stoppie_lands_when_the_rider_eases_off(himalayan):
    p = params(himalayan, 1.3)
    sim = BrakingSim(p, 100)
    lever = 0.0
    while not sim.stopped and sim.t < 6:
        lifted = not sim.grounded
        lever = max(0.0, lever - 0.01) if lifted else min(1.0, lever + 0.004)
        sim.step(lever, 0.0)
    texts = [e for _, e in sim.events]
    assert any("lifts" in e for e in texts) and any("lands" in e for e in texts)
    assert sim.summary().outcome == "stopped"


def test_rider_parameters_and_their_bases(himalayan):
    p, notes = braking_parameters(himalayan, RiderSetup(), 1.0)
    bases = {n.name: n.basis for n in notes}
    assert "example" in bases["Motorcycle's weight on the front wheel"]
    assert "Sharp" in bases["Wheel spin inertias"]
    scram, scram_notes = braking_parameters(catalogue.bike("re-scram-411"), RiderSetup(), 1.0)
    assert "measured" in {n.name: n.basis for n in scram_notes}["Motorcycle's weight on the front wheel"]
    mine, my_notes = braking_parameters(himalayan, RiderSetup(bike_front_weight_pct=50.0), 1.0)
    assert {n.name: n.basis for n in my_notes}["Motorcycle's weight on the front wheel"] == "your value"
    assert p.static_front_load + p.static_rear_load == near(p.weight)
    assert 0 < p.cog_ahead_of_rear < p.wheelbase


def test_time_step_convergence(himalayan):
    p = params(himalayan)
    coarse = run_braking(p, 100, 1.0, 1.0, dt=0.001).summary().stopping_distance
    fine = run_braking(p, 100, 1.0, 1.0, dt=0.00025).summary().stopping_distance
    assert coarse == near(fine, rel=0.01)
