"""Braking with suspension: equilibrium, energy conservation, dive, load transfer and the rigid limit."""

import math
from dataclasses import replace

import pytest

from kammcircle import catalogue
from kammcircle.rider import RiderSetup
from kammcircle.sim import LeverRamp, SuspendedBrakingSim, braking_parameters, run_braking, suspension_parameters
from kammcircle.sim.suspension import _rot

near = pytest.approx


@pytest.fixture(scope="module")
def himalayan():
    return catalogue.bike("re-himalayan-450-2026")


def build(bike, mu=1.0, setup=None, **susp_changes):
    setup = setup or RiderSetup()
    p, _ = braking_parameters(bike, setup, mu)
    s, _ = suspension_parameters(bike, setup)
    return p, (replace(s, **susp_changes) if susp_changes else s)


def ride(p, s, speed, front, rear, until=20.0, squeeze=0.3):
    sim = SuspendedBrakingSim(p, s, speed)
    levers = LeverRamp(squeeze)
    while not sim.stopped and sim.t < until:
        levers.update(front, rear, sim.dt)
        sim.step(levers.front, levers.rear)
    return sim


def energy(sim: SuspendedBrakingSim) -> float:
    """Kinetic plus potential energy of the whole model (springs, tyres, gravity, wheel spin)."""
    p, s, g = sim.p, sim.susp, sim.p.g
    x, z, th, sf, sr = sim.q
    xd, zd, thd, sfd, srd = sim.qd
    b_f = (sim.a_f0[0] + sf * sim.e_f[0], sim.a_f0[1] + sf * sim.e_f[1])
    b_r = (sim.a_r0[0], sim.a_r0[1] + sr)
    from kammcircle.sim.suspension import _drot

    def axle_velocity(b, e, sd):
        j, ej = _drot(th, b), _rot(th, e)
        return xd + j[0] * thd + ej[0] * sd, zd + j[1] * thd + ej[1] * sd

    vf, vr = axle_velocity(b_f, sim.e_f, sfd), axle_velocity(b_r, sim.e_r, srd)
    pf, pr = sim.front_axle_world(), sim.rear_axle_world()
    kinetic = (0.5 * sim.m_s * (xd * xd + zd * zd) + 0.5 * sim.i_s * thd * thd
               + 0.5 * sim.m_uf * (vf[0] ** 2 + vf[1] ** 2) + 0.5 * sim.m_ur * (vr[0] ** 2 + vr[1] ** 2)
               + 0.5 * p.front_wheel_inertia * sim.wf ** 2 + 0.5 * p.rear_wheel_inertia * sim.wr ** 2)
    depth_f, depth_r = max(0.0, p.front_radius - pf[1]), max(0.0, p.rear_radius - pr[1])
    potential = (g * (sim.m_s * z + sim.m_uf * pf[1] + sim.m_ur * pr[1])
                 + 0.5 * sim.k_f * sf * sf + 0.5 * sim.k_r * sr * sr
                 + 0.5 * s.tyre_k_front * depth_f ** 2 + 0.5 * s.tyre_k_rear * depth_r ** 2)
    return kinetic + potential


def test_static_equilibrium_holds_exactly(himalayan):
    p, s = build(himalayan)
    sim = SuspendedBrakingSim(p, s, 60)
    sim.run_for(1.0, 0.0, 0.0)
    assert sim.front_compression == near(s.front_sag, abs=1e-6)
    assert sim.rear_compression == near(s.rear_sag, abs=1e-6)
    assert sim.theta == near(0.0, abs=1e-9)
    assert sim.nf == near(p.static_front_load, rel=1e-6)
    assert sim.nf + sim.nr == near(p.weight, rel=1e-6)
    assert sim.v == near(60 / 3.6, abs=1e-6)


def test_energy_is_conserved_without_damping_or_friction(himalayan):
    """With no damping and no tyre grip the equations of motion conserve energy: the integrator's error must
    halve when the time step halves, and stay small. A strong check of the mass matrix, the velocity-product
    terms and every potential, including a wheel leaving the road (the sprung mass is dropped from 30 mm)."""
    p, s = build(himalayan, mu=1e-9, damping_ratio=0.0, tyre_damping_ratio=0.0, stop_c=0.0)
    drifts = []
    for dt in (0.0001, 0.00005):
        sim = SuspendedBrakingSim(p, s, 30, dt=dt)
        still = energy(sim)
        sim.q[1] += 0.03
        sim.qd[2] = 0.4
        start = energy(sim)
        worst = 0.0
        for _ in range(round(0.5 / dt)):
            sim.step(0.0, 0.0)
            worst = max(worst, abs(energy(sim) - start))
        assert not sim.stopped
        drifts.append(worst / (start - still))
    assert drifts[1] < 0.01
    assert drifts[0] / drifts[1] == near(2.0, rel=0.25)  # first-order convergence: no modelling error left


def test_braking_dives_the_fork_and_lifts_the_tail(himalayan):
    p, s = build(himalayan)
    sim = ride(p, s, 80, 0.45, 0.15, until=1.2)
    assert sim.front_compression > s.front_sag + 0.05
    assert sim.rear_compression < s.rear_sag
    assert math.degrees(sim.theta) > 2.0  # nose down


def test_steady_braking_load_transfer_matches_the_textbook_with_the_current_geometry(himalayan):
    p, s = build(himalayan)
    sim = ride(p, s, 100, 0.40, 0.10, until=1.5)
    decel = -sim.a
    fx, _ = sim.front_axle_world()
    rx, _ = sim.rear_axle_world()
    m = p.mass
    gx = (sim.m_s * sim.q[0] + sim.m_uf * fx + sim.m_ur * rx) / m
    gz = (sim.m_s * sim.q[1] + sim.m_uf * sim.front_axle_world()[1] + sim.m_ur * sim.rear_axle_world()[1]) / m
    wheelbase, b = fx - rx, gx - rx
    textbook = (p.weight * b + m * decel * gz) / wheelbase
    assert 0.4 * p.g < decel < 0.8 * p.g
    assert sim.nf == near(textbook, rel=0.04)  # the rest is pitch motion and the wheels' spin


def test_a_stiff_suspension_tends_to_the_rigid_model(himalayan):
    p, s = build(himalayan)
    stiff = replace(s, front_sag=0.001, rear_sag=0.001, damping_ratio=0.7, tyre_k_front=5e6, tyre_k_rear=5e6,
                    tyre_damping_ratio=0.7)
    suspended = ride(p, stiff, 80, 0.45, 0.15).summary()
    rigid = run_braking(p, 80, 0.45, 0.15).summary()
    assert suspended.outcome == rigid.outcome == "stopped"
    assert suspended.stopping_distance == near(rigid.stopping_distance, rel=0.001)


def test_lift_is_reported_only_when_the_rear_tyre_clears_the_road(himalayan):
    p, s = build(himalayan)
    gentle = ride(p, s, 80, 0.30, 0.10)
    assert not any("lifts" in e for _, e in gentle.events)
    p13, s13 = build(himalayan, mu=1.3)
    hard = ride(p13, s13, 100, 1.0, 0.0)
    assert any("lifts" in e for _, e in hard.events)
    assert hard.summary().max_rear_lift_mm > 10


def test_suspension_parameters_and_their_bases(himalayan):
    _, notes = suspension_parameters(himalayan, RiderSetup())
    bases = {n.name: n.basis for n in notes}
    assert "Touratech" in bases["Rider sag"]
    assert "Sharp" in bases["Unsprung masses"]
    assert "modelling choice" in bases["Suspension damping"]
    s, _ = suspension_parameters(himalayan, RiderSetup(front_sag_pct=25.0))
    assert s.front_sag == near(0.25 * 0.200)
