"""Acceleration: the engine curve, the derived drag area, shifting, launch control and the wheelie limit."""

from dataclasses import replace

import pytest

from kammcircle import catalogue
from kammcircle.rider import RiderSetup
from kammcircle.sim import acceleration_parameters, braking_parameters, run_acceleration, suspension_parameters
from kammcircle.sim.acceleration import RPM, Engine

near = pytest.approx
BIKES = ("re-himalayan-450-2026", "re-scram-411")


def build(bike_id, mu=1.0, setup=None):
    bike = catalogue.bike(bike_id)
    setup = setup or RiderSetup()
    spec, notes = acceleration_parameters(bike, setup)
    p, _ = braking_parameters(bike, setup, mu)
    s, _ = suspension_parameters(bike, setup)
    return bike, spec, notes, p, s


@pytest.mark.parametrize("bike_id", BIKES)
def test_engine_curve_passes_through_the_published_figures(bike_id):
    bike, spec, *_ = build(bike_id)
    drive, e = bike.raw["drivetrain"], spec.engine
    assert e.torque(drive["max_torque_rpm"]) == near(drive["max_torque_nm"], abs=1e-9)
    assert e.power_kw(drive["max_power_rpm"]) == near(drive["max_power_kw"], abs=1e-6)
    peak = max(range(int(e.idle_rpm), int(e.limit_rpm)), key=e.power_kw)
    assert peak == near(drive["max_power_rpm"], abs=20)  # the power curve peaks where the maker says
    assert max(e.torque(n) for n in range(int(e.idle_rpm), int(e.limit_rpm))) == near(drive["max_torque_nm"], abs=0.01)
    assert all(e.torque(n) > 0 for n in range(int(e.idle_rpm), int(e.limit_rpm), 50))
    assert e.torque(e.limit_rpm) == 0.0


@pytest.mark.parametrize("bike_id", BIKES)
def test_the_derived_drag_area_reproduces_the_reported_top_speed(bike_id):
    bike, spec, notes, p, s = build(bike_id)
    pt = spec.powertrain(shift_rpm=spec.engine.limit_rpm - 200, launch_rpm=spec.engine.peak_torque_rpm * 0.8)
    sim = run_acceleration(p, s, pt, speed_kmh=80, target_kmh=None, cda=spec.cda, crr=spec.crr, max_time=120, dt=0.001)
    assert sim.outcome == "top speed"
    assert sim.v * 3.6 == near(bike.raw["top_speed_kmh"]["value"], abs=2.5)
    assert "derived" in {n.name: n.basis for n in notes}["Drag area CdA"]


def test_shifts_happen_at_the_shift_speed_and_launch_control_limits_wheelspin():
    _, spec, _, p, s = build("re-himalayan-450-2026")
    e = spec.engine
    controlled = spec.powertrain(shift_rpm=8000, launch_rpm=4400)
    sim = run_acceleration(p, s, controlled, target_kmh=100, cda=spec.cda, crr=spec.crr)
    assert sim.outcome == "reached"
    gears = [g for _, g in controlled.shifts]
    assert gears == list(range(2, 2 + len(gears)))  # one gear at a time, in order
    top_of_third = 8000 / spec.gearbox.overall(3) * RPM * p.rear_radius * 3.6
    assert (gears[-1] == 4) == (top_of_third < 100)  # 3rd runs out before 100 km/h at an 8000 rpm shift
    for t_shift, _ in controlled.shifts:
        before = [x for x in sim.trace if x.t < t_shift][-1]
        assert before.rpm == near(8000, abs=150)
    summary = sim.acceleration_summary()
    assert summary["wheelspin_s"] < 0.3
    assert 5.0 < summary["t_100"] < 9.0  # one published (unverified) figure is 6.1 s
    free = spec.powertrain(shift_rpm=8000, launch_rpm=4400)
    spun = run_acceleration(p, s, free, target_kmh=100, throttle_control=False, cda=spec.cda, crr=spec.crr)
    assert spun.acceleration_summary()["wheelspin_s"] > 1.0
    assert spun.acceleration_summary()["t_100"] > summary["t_100"]
    assert e.idle_rpm == 1300


def test_a_rolling_start_picks_a_gear_that_suits_the_speed():
    _, spec, _, p, s = build("re-himalayan-450-2026")
    pt = spec.powertrain(shift_rpm=8500, launch_rpm=4000)
    sim = run_acceleration(p, s, pt, speed_kmh=60, target_kmh=100, cda=spec.cda, crr=spec.crr)
    assert sim.outcome == "reached"
    assert pt.shifts == [] or pt.shifts[0][1] >= 3
    assert sim.trace[1].gear >= 2  # the first sample is taken before the gear is chosen


def test_an_engine_strong_enough_lifts_the_front_and_throttle_control_keeps_it_down():
    _, spec, _, p, s = build("re-himalayan-450-2026")
    strong = replace(spec.engine, peak_torque_nm=120.0, peak_power_kw=90.0)
    assert Engine(**{**strong.__dict__}).torque(strong.peak_torque_rpm) == 120.0
    spec3 = replace(spec, engine=strong)
    wild = run_acceleration(p, s, spec3.powertrain(8500, 5000), target_kmh=80, throttle_control=False)
    assert any("wheelie" in e for _, e in wild.events) or wild.outcome == "looped over"
    tamed = run_acceleration(p, s, spec3.powertrain(8500, 5000), target_kmh=80, throttle_control=True)
    assert tamed.acceleration_summary()["max_wheelie_mm"] < 60
    assert tamed.outcome == "reached"


def test_acceleration_moves_load_to_the_rear_and_squats_it():
    _, spec, _, p, s = build("re-himalayan-450-2026")
    sim = run_acceleration(p, s, spec.powertrain(8500, 4400), target_kmh=45, cda=spec.cda, crr=spec.crr)
    mid = [x for x in sim.trace if 1.0 < x.t < 1.5]
    assert all(x.nr > p.static_rear_load for x in mid)
    assert all(x.nf < p.static_front_load for x in mid)
    assert all(x.pitch < 0 for x in mid)  # nose up
    assert RPM == near(0.10472, abs=1e-5)
