"""Lean and steer: the benchmark model against the published values of Meijaard et al. (2007), the motorcycle's
parameters, and a corner ridden by countersteering."""

import math

import pytest

from kammcircle import catalogue
from kammcircle.rider import RiderSetup
from kammcircle.sim.countersteer import Corner, choose_gains, run_corner
from kammcircle.sim.lateral import (
    BENCHMARK,
    capsize_speed,
    coefficients,
    eigenvalues,
    modes,
    self_stable_range,
    steady_turn,
    weave_speed,
)
from kammcircle.sim.parameters import combined, lateral_parameters, mass_points

near = pytest.approx
G = 9.81
BIKES = ("re-himalayan-450-2026", "re-scram-411")

# Meijaard et al. (2007), eqs. (6.1)–(6.4) and Table 2, to the published 14 decimals
PUBLISHED = {
    "M": ((80.81722, 2.31941332208709), (2.31941332208709, 0.29784188199686)),
    "K0": ((-80.95, -2.59951685249872), (-2.59951685249872, -0.80329488458618)),
    "K2": ((0.0, 76.59734589573222), (0.0, 2.65431523794604)),
    "C1": ((0.0, 33.86641391492494), (-0.85035641456978, 1.68540397397560)),
}
WEAVE = {  # v: (Re, Im)
    1: (3.52696170990070, 0.80774027519930), 2: (2.68234517512745, 1.68066296590675),
    3: (1.70675605663975, 2.31582447384325), 4: (0.41325331521125, 3.07910818603206),
    5: (-0.77534188219585, 4.46486771378823), 6: (-1.52644486584142, 5.87673060598709),
    7: (-2.13875644258362, 7.19525913329805), 8: (-2.69348683581097, 8.46037971396931),
    9: (-3.21675402252485, 9.69377351531791), 10: (-3.72016840437287, 10.90681139476287),
}
REAL = {  # v: (capsize, castering)
    0: (-3.13164324790656, -5.53094371765393), 1: (-3.13423125066578, -7.11008014637442),
    2: (-3.07158645641514, -8.67387984831735), 3: (-2.63366137253667, -10.35101467245920),
    4: (-1.42944427361326, -12.15861426576447), 5: (-0.32286642900409, -14.07838969279822),
    6: (-0.00406690076970, -16.08537123098026), 7: (0.10268170574766, -18.15788466125262),
    8: (0.14327879765713, -20.27940894394569), 9: (0.15790184030917, -22.43788559040858),
    10: (0.16105338653172, -24.62459635017404),
}


def test_the_coefficients_reproduce_the_benchmark_matrices():
    k = coefficients(BENCHMARK)
    for name, matrix in PUBLISHED.items():
        got = getattr(k, name)
        for i in range(2):
            for j in range(2):
                assert got[i][j] == near(matrix[i][j], abs=1e-12), (name, i, j)


@pytest.mark.parametrize("v", sorted(WEAVE))
def test_the_eigenvalues_reproduce_the_benchmark_table(v):
    m = modes(coefficients(BENCHMARK), float(v))
    assert m.weave.real == near(WEAVE[v][0], abs=1e-11)
    assert m.weave.imag == near(WEAVE[v][1], abs=1e-11)
    assert m.capsize == near(REAL[v][0], abs=1e-11)
    assert m.castering == near(REAL[v][1], abs=1e-11)


def test_at_rest_the_bicycle_falls_like_two_inverted_pendulums():
    roots = sorted(r.real for r in eigenvalues(coefficients(BENCHMARK), 0.0))
    assert roots == near([-5.53094371765393, -3.13164324790656, 3.13164324790656, 5.53094371765393], abs=1e-11)


def test_the_weave_and_capsize_speeds_reproduce_the_benchmark():
    k = coefficients(BENCHMARK)
    assert weave_speed(k) == near(4.29238253634111, abs=1e-9)
    assert capsize_speed(k) == near(6.02426201538837, abs=1e-9)
    assert self_stable_range(k) == near((4.29238253634111, 6.02426201538837), abs=1e-9)
    hopf = modes(k, 4.29238253634111)
    assert hopf.weave.imag == near(3.43503384866144, abs=1e-7)


@pytest.mark.parametrize("bike_id", BIKES)
def test_the_motorcycle_parts_add_up_to_the_loaded_motorcycle(bike_id):
    bike = catalogue.bike(bike_id)
    setup = RiderSetup(pillion_mass_kg=65, luggage_mass_kg=20)
    p, _, notes = lateral_parameters(bike, setup)
    k = coefficients(p)
    mass, b, h, _ = combined(mass_points(bike, setup))
    assert k.m_t == near(mass, rel=1e-12)
    assert k.x_t == near(b, abs=1e-12)
    assert -k.z_t == near(h, abs=1e-12)
    for i_xx, i_yy, i_zz, i_xz in ((p.i_bxx, p.i_byy, p.i_bzz, p.i_bxz), (p.i_hxx, p.i_hyy, p.i_hzz, p.i_hxz)):
        assert i_xx > 0 and i_zz > 0 and i_xx * i_zz > i_xz ** 2  # positive definite
        trace, root = i_xx + i_zz, math.sqrt((i_xx - i_zz) ** 2 + 4 * i_xz ** 2)
        principal = ((trace + root) / 2, i_yy, (trace - root) / 2)
        assert all(2 * x <= sum(principal) + 1e-9 for x in principal)  # triangle inequalities (Meijaard et al. §3)
    assert p.i_fyy <= 2 * p.i_fxx and p.i_ryy <= 2 * p.i_rxx
    assert any("Steered front frame" == n.name for n in notes)


@pytest.mark.parametrize("bike_id", BIKES)
def test_the_motorcycle_steadies_itself_in_a_band_of_speed_and_capsizes_slowly_above_it(bike_id):
    p, _, _ = lateral_parameters(catalogue.bike(bike_id), RiderSetup())
    k = coefficients(p)
    lo, hi = self_stable_range(k)
    assert 3 < lo < hi < 30  # m/s
    fast = modes(k, 30.0)
    assert fast.weave.real < 0 and fast.castering < fast.weave.real
    assert 0 < fast.capsize < 0.5  # a slow fall into the turn, which the rider corrects
    assert modes(k, 0.5 * (lo + hi)).stable and not modes(k, 0.8 * lo).stable


def test_the_linear_steady_turn_matches_the_exact_lean_for_gentle_corners():
    p, _, _ = lateral_parameters(catalogue.bike("re-himalayan-450-2026"), RiderSetup())
    k = coefficients(p)
    v, radius = 100 / 3.6, 600.0
    turn = steady_turn(k, p, v, radius)
    exact = math.atan(v * v / G / radius)
    gyroscopic = 1 + (k.s_r + k.s_f) / (k.m_t * -k.z_t)  # wheel spin asks for a little more lean
    assert turn.lean == near(exact * gyroscopic, rel=0.01)
    assert turn.steer == near(p.w / (radius * math.cos(p.lam)), rel=1e-12)
    assert steady_turn(k, p, v, radius, -1).torque == near(-turn.torque, abs=1e-12)


@pytest.mark.parametrize("bike_id", BIKES)
def test_the_rider_leans_in_by_steering_away_from_the_corner(bike_id):
    p, steering, _ = lateral_parameters(catalogue.bike(bike_id), RiderSetup())
    right = run_corner(p, Corner(60, 80, 90, 1, roll_in_time=1.0), torque_lag=steering.torque_lag)
    turning = [s for s in right.trace if s.t > right.turn_start]
    first = next(s for s in turning if abs(s.torque) > 0.05 * right.peak_push)
    assert first.torque < 0 and first.lean < 0.5  # the first push urges the bars left, for a right-hand corner
    first_steer = next(s for s in turning if abs(s.steer) > 0.01)
    assert first_steer.steer < 0  # and the front wheel turns left
    assert min(s.y for s in turning) < -0.02 and min(s.fy for s in turning) < -0.02  # both wheels run wide first
    assert right.wide_rear > 0.02 and right.wide_front > right.wide_rear
    assert right.peak_countersteer > 0 and right.peak_push > 1.0
    left = run_corner(p, Corner(60, 80, 90, -1, roll_in_time=1.0), torque_lag=steering.torque_lag)
    for a, b in zip(right.trace, left.trace):  # a mirror image
        assert (b.lean, b.steer, b.torque, b.y) == near((-a.lean, -a.steer, -a.torque, -a.y), abs=1e-9)


@pytest.mark.parametrize("angle", [30, 90, 180])
def test_the_corner_holds_its_radius_and_ends_on_the_new_heading(angle):
    p, steering, _ = lateral_parameters(catalogue.bike("re-himalayan-450-2026"), RiderSetup())
    sim = run_corner(p, Corner(70, 100, angle, 1, roll_in_time=0.8), torque_lag=steering.torque_lag)
    assert sim.outcome == "done"
    assert sim.trace[-1].heading == near(angle, abs=0.1)
    assert abs(sim.trace[-1].lean) < 0.05
    if angle >= 90:
        start = sim.turn_start + sim.time_to_lean + 1.0
        hold = [s for s in sim.trace if start < s.t < start + 1.0]
        turned = math.radians(hold[-1].heading - hold[0].heading)
        assert sim.v * (hold[-1].t - hold[0].t) / turned == near(100, rel=0.005)


def test_a_quicker_roll_in_takes_a_harder_push_and_a_wider_line():
    p, steering, _ = lateral_parameters(catalogue.bike("re-himalayan-450-2026"), RiderSetup())
    slow = run_corner(p, Corner(80, 120, 90, 1, roll_in_time=1.5), torque_lag=steering.torque_lag)
    quick = run_corner(p, Corner(80, 120, 90, 1, roll_in_time=0.5), torque_lag=steering.torque_lag)
    assert quick.time_to_lean < slow.time_to_lean
    assert quick.peak_push > 2 * slow.peak_push
    assert quick.peak_countersteer > slow.peak_countersteer
    assert quick.wide_rear > slow.wide_rear


def test_the_rider_gains_place_a_double_root_and_fail_honestly_at_walking_pace():
    p, steering, _ = lateral_parameters(catalogue.bike("re-himalayan-450-2026"), RiderSetup())
    k = coefficients(p)
    gains = choose_gains(k, 80 / 3.6, 1.0, steering.torque_lag)
    near_double = [r for r in gains.roots if abs(r + gains.omega) < 1e-3]
    assert len(near_double) == 2 and gains.margin > 0
    with pytest.raises(ValueError):
        choose_gains(k, 15 / 3.6, 1.0, steering.torque_lag)
