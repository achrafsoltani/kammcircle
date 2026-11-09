"""Tyre temperature: the two-node heat balance, its steady state, its time scale against the makers' guidance, and the
grip window."""

import math
from dataclasses import replace

import pytest

from kammcircle import catalogue
from kammcircle.rider import RiderSetup
from kammcircle.sim.parameters import slip_heat, thermal_parameters
from kammcircle.sim.tyre_thermal import (
    GripWindow,
    TyreState,
    WarmUpRun,
    churchill_bernstein,
    run_warm_up,
    step,
    surface_temperature,
)

near = pytest.approx


def setup_for(bike_id="re-himalayan-450-2026"):
    ts, notes = thermal_parameters(catalogue.bike(bike_id), RiderSetup())
    return ts, notes


def ride(ts, *, air, road, kmh, style="gentle", start=None, minutes=30, window=None, dt=1.0):
    v = kmh / 3.6
    q = tuple(slip_heat(ts.tyre, n, ts.styles[style], v) for n in ts.loads)
    return run_warm_up(WarmUpRun(ts.front, ts.rear, ts.loads, q, window or ts.window, air, road, v,
                                 start=air if start is None else start, duration=minutes * 60, dt=dt))


def test_the_tyres_are_built_from_their_sizes():
    ts, notes = setup_for()
    f, r = ts.front, ts.rear
    assert f.band_area < r.band_area and f.tread_capacity < r.tread_capacity  # 90/90-21 against 140/80-17
    assert f.rim_radius == near(21 * 0.0254 / 2) and r.rim_radius == near(17 * 0.0254 / 2)
    for p, n in ((f, ts.loads[0]), (r, ts.loads[1])):
        assert 0.10 < p.contact_length(n) < 0.20  # m
    assert {n.name for n in notes} >= {"Grip window", "Cooling by the road", "Cooling by the air"}


def test_a_long_ride_settles_at_the_steady_state():
    ts, _ = setup_for()
    run = ride(ts, air=8, road=5, kmh=70, style="brisk", minutes=180)
    for state, steady in zip(run.states, run.steady()):
        assert state.tread == near(steady.tread, abs=0.01)
        assert state.carcass == near(steady.carcass, abs=0.01)
        assert state.surface == near(steady.surface, abs=0.01)


def test_heat_in_equals_heat_stored_plus_heat_lost():
    ts, _ = setup_for()
    p, load, v, air, road, dt = ts.rear, ts.loads[1], 80 / 3.6, 4.0, 1.0, 1.0
    q = slip_heat(ts.tyre, load, 0.3, v)
    s = TyreState(-3.0, -3.0, surface_temperature(p, -3.0, air, road, v, load, q))
    stored0 = p.tread_capacity * s.tread + p.carcass_capacity * s.carcass
    balance = 0.0
    for _ in range(900):
        surface = surface_temperature(p, s.tread, air, road, v, load, q)
        lost = (p.air_h(v) * p.band_area * (surface - air) + p.road_h(v, load) * p.band_area * (surface - road)
                + p.air_h(v) * p.sidewall_area * (s.carcass - air))
        balance += dt * (p.rolling_heat(v, load) + q - lost)
        s = step(p, s, dt, air=air, road=road, speed=v, load=load, slip_heat=q)
    stored = p.tread_capacity * s.tread + p.carcass_capacity * s.carcass - stored0
    assert stored == near(balance, rel=1e-9)


def test_tyres_warm_over_minutes_as_the_makers_say():
    """Michelin: reaching operating temperature takes 'a certain number of miles'. In mild weather the gentle
    warm-up covers two-thirds of its rise in a few minutes, not seconds and not an hour."""
    ts, _ = setup_for()
    run = ride(ts, air=15, road=15, kmh=60, minutes=60)
    for i in range(2):
        rise = run.steady()[i].tread - 15
        t63 = next(x.t for x in run.trace if x.tread[i] - 15 >= (1 - math.exp(-1)) * rise)
        assert 120 < t63 < 600


def test_cold_air_and_cold_road_each_keep_the_tyres_colder():
    ts, _ = setup_for()
    mild = ride(ts, air=20, road=25, kmh=60).steady()
    cold_air = ride(ts, air=5, road=25, kmh=60).steady()
    cold_road = ride(ts, air=20, road=0, kmh=60).steady()
    for i in range(2):
        assert cold_air[i].surface < mild[i].surface and cold_road[i].surface < mild[i].surface
        assert cold_road[i].surface - mild[i].surface < -3  # the road's conduction matters, not only the air


def test_speed_and_hard_riding_warm_the_tyres_and_slip_heats_the_surface_first():
    ts, _ = setup_for()
    slow, fast = ride(ts, air=10, road=10, kmh=40).steady(), ride(ts, air=10, road=10, kmh=100).steady()
    gentle, hard = ride(ts, air=10, road=10, kmh=80).steady(), ride(ts, air=10, road=10, kmh=80, style="hard").steady()
    for i in range(2):
        assert fast[i].surface > slow[i].surface  # rolling heat grows faster with speed than the cooling does
        assert hard[i].surface > gentle[i].surface
        assert hard[i].surface - hard[i].tread > gentle[i].surface - gentle[i].tread  # slip heat enters at the surface


def test_in_the_cold_gentle_riding_never_reaches_the_window_and_warmers_lose_their_heat():
    """Michelin: heated tyres 'would quickly lose their temperature in the cold'."""
    ts, _ = setup_for()
    cold = ride(ts, air=3, road=1, kmh=60, minutes=60)
    assert cold.reached == [None, None]
    assert all(0.8 <= g < 0.95 for g in cold.trace[-1].grip)
    warm = ride(ts, air=3, road=1, kmh=60, start=55, minutes=30)
    assert all(g > 0.99 for g in warm.trace[0].grip)
    assert all(s < 31 for s in warm.trace[0].surface)  # riding, the surface sits far below the warmed bulk at once
    assert all(e < s - 0.05 for e, s in zip(warm.trace[-1].grip, warm.trace[0].grip))


def test_the_grip_window_is_smooth_and_monotone_up_to_its_top():
    w = GripWindow()
    temps = [t / 2 for t in range(-60, 200)]
    values = [w.factor(t) for t in temps]
    assert w.factor(w.cold_temp) == near(w.cold_share)
    assert w.factor(w.window_low) == 1.0 and w.factor(w.window_high) == 1.0
    assert w.factor(w.window_low - 1e-9) == near(1.0, abs=1e-9)  # no step into the window
    rising = [v for t, v in zip(temps, values) if t <= w.window_low]
    assert all(b >= a for a, b in zip(rising, rising[1:]))
    assert w.factor(80) == near(1 - 0.005 * 20) and w.factor(500) == w.floor
    assert w.factor(-30) < w.cold_share and w.factor(-1000) == w.floor
    assert w.factor(w.temperature_for(0.9)) == near(0.9, abs=1e-9)
    narrow = replace(w, window_low=50.0)
    assert ride(setup_for()[0], air=20, road=25, kmh=60, window=narrow).reached == [None, None]


def test_the_convection_correlation_rises_with_the_wind():
    assert churchill_bernstein(0.0, 0.71) == near(0.3)
    values = [churchill_bernstein(re, 0.71) for re in (1e3, 1e4, 1e5, 1e6)]
    assert all(b > a for a, b in zip(values, values[1:]))
    ts, _ = setup_for()
    assert ts.rear.air_h(30.0) > ts.rear.air_h(10.0) > ts.rear.air_h(0.0) > 0
