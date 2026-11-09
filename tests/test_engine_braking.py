"""Engine braking on the suspended model, and the engine's drag and inertia (labelled stand-ins)."""

import math
from dataclasses import replace

import pytest

from kammcircle import catalogue
from kammcircle.rider import RiderSetup
from kammcircle.sim import (
    LeverRamp,
    SuspendedBrakingSim,
    acceleration_parameters,
    braking_parameters,
    run_acceleration,
    suspension_parameters,
)
from kammcircle.sim.engine_braking import EngineBrakingSim, coast_deceleration_g, over_revs

near = pytest.approx
BRAKE_AT = 0.6


def build(mu=1.0, bike_id="re-himalayan-450-2026"):
    bike = catalogue.bike(bike_id)
    setup = RiderSetup()
    spec, _ = acceleration_parameters(bike, setup)
    p, _ = braking_parameters(bike, setup, mu)
    s, _ = suspension_parameters(bike, setup)
    return spec, p, s


def stop(spec, p, s, gear, kmh, front, rear, brake_at=BRAKE_AT):
    """A scripted stop: steady riding, then the throttle shuts and the brakes come on together."""
    if gear:
        sim = EngineBrakingSim(p, s, spec.powertrain(math.inf, spec.engine.idle_rpm), gear, kmh,
                               declutch_rpm=spec.declutch_rpm, throttle_off_at=brake_at)
    else:
        sim = SuspendedBrakingSim(p, s, kmh)
    sim.cda, sim.crr, sim.air_density = spec.cda, spec.crr, spec.air_density
    levers = LeverRamp(0.3)
    while not sim.stopped and sim.t < 90:
        on = sim.t >= brake_at
        levers.update(front if on else 0.0, rear if on else 0.0, sim.dt)
        sim.step(levers.front, levers.rear)
    sim.stop_at_time_limit()
    return sim


def test_the_drag_rises_linearly_from_idle_to_the_rev_limit():
    spec, _, _ = build()
    e = spec.engine
    assert e.drag_torque(e.idle_rpm) == near(0.10 * 40)
    assert e.drag_torque(e.limit_rpm) == near(0.30 * 40)
    assert e.drag_torque(0.5 * (e.idle_rpm + e.limit_rpm)) == near(0.20 * 40)
    assert e.drag_torque(500) == e.drag_torque(e.idle_rpm) and e.drag_torque(20000) == e.drag_torque(e.limit_rpm)
    assert e.net_torque(5000, 1.0) == e.torque(5000)
    assert e.net_torque(5000, 0.0) == -e.drag_torque(5000)
    assert e.net_torque(5000, 0.5) == near(0.5 * (e.torque(5000) - e.drag_torque(5000)))


def test_the_drivetrain_losses_oppose_the_flow_of_power():
    spec, _, _ = build()
    pt = spec.powertrain(8000, 4400)
    ratio = spec.gearbox.overall(2)
    assert pt.at_wheel(10.0, ratio) == near(10.0 * ratio * spec.efficiency)
    assert pt.at_wheel(-10.0, ratio) == near(-10.0 * ratio / spec.efficiency)


def test_engine_braking_is_strongest_in_the_low_gears():
    spec, p, _ = build()
    pt = spec.powertrain(8000, 4400)
    usable = [g for g in range(1, len(spec.gearbox.gears) + 1) if not over_revs(pt, g, 40, p.rear_radius)]
    decels = [coast_deceleration_g(p, pt, g, 40) for g in usable]
    assert len(usable) >= 4 and all(a > b > 0 for a, b in zip(decels, decels[1:]))
    assert over_revs(pt, 1, 100, p.rear_radius) and math.isnan(coast_deceleration_g(p, pt, 1, 100))


def test_a_coast_in_gear_slows_by_the_engine_estimate_plus_the_road_load():
    spec, p, s = build()
    geared = stop(spec, p, s, 3, 70, 0.0, 0.0, brake_at=0.0)
    free = stop(spec, p, s, 0, 70, 0.0, 0.0, brake_at=0.0)

    def mean_decel(sim):
        a = [x for x in sim.trace if 0.4 <= x.t <= 0.9]
        return (a[0].v - a[-1].v) / (a[-1].t - a[0].t) / p.g, 0.5 * (a[0].v + a[-1].v) * 3.6

    engine_and_road, kmh = mean_decel(geared)
    road, _ = mean_decel(free)
    estimate = coast_deceleration_g(p, spec.powertrain(math.inf, 1300), 3, kmh)
    assert engine_and_road - road == near(estimate, rel=0.1)


def test_braking_in_gear_stops_shorter_from_the_same_brake_speed():
    spec, p, s = build()
    clutch = stop(spec, p, s, 0, 60, 0.4, 0.0)
    geared = stop(spec, p, s, 2, 60, 0.4, 0.0)
    a, b = clutch.summary(), geared.summary()
    assert b.brake_speed_kmh == near(a.brake_speed_kmh, abs=0.01)  # the throttle shut as the brakes came on (±1 step)
    assert a.outcome == b.outcome == "stopped"
    assert b.stopping_distance < a.stopping_distance - 1.0
    assert 0.05 < geared.engine_share < 0.5 and geared.peak_engine_torque > 50
    texts = [e for _, e in geared.events]
    assert any("clutch out in 2nd" in e for e in texts) and any(e.startswith("Clutch in at") for e in texts)
    declutch = next(t for t, e in geared.events if e.startswith("Clutch in at"))
    after = [x for x in geared.trace if x.t > declutch + 0.01]
    assert all(x.drive == 0.0 for x in after) and all(x.rpm == spec.engine.idle_rpm for x in after)


def test_a_gear_too_low_for_the_speed_waits_for_the_engine():
    spec, p, s = build()
    sim = stop(spec, p, s, 1, 120, 0.5, 0.0)
    texts = [e for _, e in sim.events]
    assert "would over-rev" in texts[0]
    engaged = next(x for x in sim.trace if x.drive < 0)
    limit_kmh = spec.engine.limit_rpm / spec.gearbox.overall(1) * 2 * math.pi / 60 * p.rear_radius * 3.6
    assert engaged.v * 3.6 <= limit_kmh + 0.5 and engaged.rpm <= spec.engine.limit_rpm


def test_first_gear_engine_braking_slides_the_rear_on_loose_ground_but_not_on_tarmac():
    """From 40 km/h on loose ground (μ 0.3), first gear's engine braking alone runs the rear tyre far past its peak
    slip; second gear does not, and nor does first on tarmac."""
    for mu, gear, slides in ((0.3, 1, True), (0.3, 2, False), (1.0, 1, False)):
        spec, p, s = build(mu)
        sim = stop(spec, p, s, gear, 40, 0.0, 0.0, brake_at=0.0)
        peak = p.tyre.peak_braking_slip(p.static_rear_load)
        worst = min(x.kr for x in sim.trace)
        assert (worst < 1.5 * peak) == slides, (mu, gear, worst, peak)


def test_the_engine_inertia_adds_to_the_rear_wheel_in_gear_and_slows_a_launch():
    spec, p, s = build()
    pt = spec.powertrain(8000, 4400)
    pt.clutch_engaged = True
    assert pt.reflected_inertia() == near(spec.engine.inertia * spec.gearbox.overall(1) ** 2)
    pt.shift_timer = 0.1
    assert pt.reflected_inertia() == 0.0  # mid-shift the engine is free of the wheel
    light = replace(spec, engine=replace(spec.engine, inertia=0.0))
    heavy = run_acceleration(p, s, spec.powertrain(8000, 4400), target_kmh=100, cda=spec.cda, crr=spec.crr)
    free = run_acceleration(p, s, light.powertrain(8000, 4400), target_kmh=100, cda=spec.cda, crr=spec.crr)
    assert heavy.acceleration_summary()["t_100"] > free.acceleration_summary()["t_100"] + 0.1
