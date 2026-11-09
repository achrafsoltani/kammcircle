"""A corner ridden in time on the benchmark lean-and-steer model (lateral.py): the rider leans the motorcycle in,
holds the turn and stands it up again with handlebar torque alone. To lean into a turn the rider first turns the
handlebars away from it, and this is countersteering. Nothing in the code forces that; it falls out of the equations.

The rider is a feedback controller in the form Sharp, Evangelou and Limebeer (2004, section 6) use: steer torque from
the lean-angle error and the lean rate, with the torque the steady turn needs fed forward in place of their integral
term (the linear model gives it exactly). The gains place a double root of the closed loop at −ω, with
ω = 3.89 ÷ (the roll-in time), and the rider's arms deliver the torque through a first-order lag.

Signs follow the model's axes: lean, steer, torque, heading and sideways position are positive to the right.
Constant speed; no tyre slip.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .lateral import (
    Coefficients,
    G,
    WhippleParameters,
    characteristic_polynomial,
    coefficients,
    poly_add,
    poly_derivative,
    poly_eval,
    poly_mul,
    poly_roots,
    steady_turn,
)

SETTLE = 3.89  # ω·t at which a critically damped response to a step reaches 90 %


@dataclass(frozen=True)
class Corner:
    speed_kmh: float
    radius: float  # m, of the rear wheel's path in the steady part
    angle_deg: float = 90.0  # change of heading through the corner
    direction: int = 1  # +1 right-hand, −1 left-hand
    roll_in_time: float = 1.0  # s, the time the rider's lean response is designed to reach 90 % of the lean
    approach: float = 0.5  # s of straight before the rider starts the turn


@dataclass(frozen=True)
class RiderGains:
    kp: float  # N m per rad of lean error
    kd: float  # N m per rad/s of lean rate
    omega: float  # the double root is at −ω
    roots: tuple[complex, ...]  # every root of the closed loop

    @property
    def margin(self) -> float:
        return -max(r.real for r in self.roots)


@dataclass
class CornerSample:
    t: float
    x: float  # m, rear contact, along the approach
    y: float  # m, rear contact, to the right of the approach line
    fx: float  # front contact
    fy: float
    heading: float  # degrees
    lean: float  # degrees
    lean_target: float
    steer: float  # degrees
    torque: float  # N m on the handlebars
    lateral_g: float


def rider_gains(k: Coefficients, v: float, omega: float, lag: float, g: float = G) -> RiderGains | None:
    """Gains of T = T_ff + kp·(φ − φ_target) + kd·φ' (delivered through 1/(lag·s + 1)) that give the closed loop
    (lag·s + 1)·det(A(s)) + A_φδ(s)·(kp + kd·s) = 0 a double root at s = −ω. The closed-loop polynomial is affine in
    kp and kd, so the two conditions p(−ω) = 0 and p'(−ω) = 0 are linear in them."""
    P = poly_mul([1.0, lag], characteristic_polynomial(k, v, g))
    A = k.entry(0, 1, v, g)
    s0 = -omega
    a0, da0 = poly_eval(A, s0).real, poly_eval(poly_derivative(A), s0).real
    if abs(a0) < 1e-9:
        return None
    u = -poly_eval(P, s0).real / a0
    kd = -(poly_eval(poly_derivative(P), s0).real + da0 * u) / a0
    kp = u - kd * s0
    roots = poly_roots(poly_add(P, poly_mul(A, [kp, kd])))
    return RiderGains(kp, kd, omega, tuple(roots))


def choose_gains(k: Coefficients, v: float, roll_in_time: float, lag: float, g: float = G) -> RiderGains:
    """The design nearest the wanted roll-in time whose other closed-loop roots are no slower than half the double
    root, so that the double root sets the pace. Candidates run from ω = 0.2 to about 60 rad/s (roll-in times from
    about 19 s down to 0.06 s); ValueError if none of them works."""
    wanted = SETTLE / roll_in_time
    candidates = [wanted] + sorted((0.2 * 1.05 ** i for i in range(118)), key=lambda w: abs(math.log(w / wanted)))
    for omega in candidates:
        gains = rider_gains(k, v, omega, lag, g)
        if gains is not None and gains.margin >= 0.5 * gains.omega:
            return gains
    raise ValueError(f"at {v * 3.6:.0f} km/h this rider cannot balance the motorcycle by steering alone")


class CornerSim:
    def __init__(self, p: WhippleParameters, corner: Corner, *, torque_lag: float = 0.1, settled: float = 0.9,
                 mu: float = 1.0, g: float = G, dt: float = 0.002, record_every: int = 5) -> None:
        self.p, self.corner, self.lag, self.settled, self.mu, self.g = p, corner, torque_lag, settled, mu, g
        self.dt, self.record_every = dt, record_every
        self.k = coefficients(p)
        self.v = corner.speed_kmh / 3.6
        K, C = self.k.stiffness(self.v, g), self.k.damping(self.v)
        self.K, self.C = K, C
        M = self.k.M
        det = M[0][0] * M[1][1] - M[0][1] * M[1][0]
        self.Minv = ((M[1][1] / det, -M[0][1] / det), (-M[1][0] / det, M[0][0] / det))
        self.turn = steady_turn(self.k, p, self.v, corner.radius, corner.direction, g)
        self.gains = choose_gains(self.k, self.v, corner.roll_in_time, torque_lag, g)
        # state: lean, steer, lean rate, steer rate, applied torque, heading, rear contact x and y
        self.state = [0.0] * 8
        self.t = 0.0
        self.phase = "approach"  # approach → turning in → holding → exiting → done
        self.events: list[tuple[float, str]] = []
        self.trace: list[CornerSample] = []
        self.turn_start: float | None = None
        self.time_to_lean: float | None = None
        self.distance_to_lean: float | None = None
        self.peak_countersteer = 0.0  # rad, steer away from the corner
        self.peak_push = 0.0  # N m, torque away from the corner (the push on the inside grip)
        self.peak_lateral_g = 0.0
        self.wide_rear = 0.0  # m the rear wheel's path moves away from the corner before it turns in
        self.wide_front = 0.0
        self.rollout_heading = self._rollout_heading()
        self.stopped = False
        self.outcome = ""
        self._slid = False
        self._steps = 0
        self._record()

    # ─── the rider ───────────────────────────────────────────────────────────

    def lean_target(self) -> float:
        return self.turn.lean if self.phase in ("turning in", "holding") else 0.0

    def _command(self, s: list[float], target: float, feedforward: float) -> float:
        return feedforward + self.gains.kp * (s[0] - target) + self.gains.kd * s[2]

    # ─── the motorcycle ──────────────────────────────────────────────────────

    def _derivative(self, s: list[float], target: float, feedforward: float) -> list[float]:
        phi, delta, dphi, ddelta, torque, psi = s[0], s[1], s[2], s[3], s[4], s[5]
        K, C, Mi = self.K, self.C, self.Minv
        f0 = -(C[0][0] * dphi + C[0][1] * ddelta + K[0][0] * phi + K[0][1] * delta)
        f1 = torque - (C[1][0] * dphi + C[1][1] * ddelta + K[1][0] * phi + K[1][1] * delta)
        p = self.p
        return [
            dphi, ddelta,
            Mi[0][0] * f0 + Mi[0][1] * f1,
            Mi[1][0] * f0 + Mi[1][1] * f1,
            (self._command(s, target, feedforward) - torque) / self.lag,
            (self.v * delta + p.c * ddelta) * math.cos(p.lam) / p.w,  # heading rate, eq. (B 6)
            self.v * math.cos(psi),  # eq. (B 8)
            self.v * math.sin(psi),
        ]

    def _rk4(self, s: list[float], target: float, feedforward: float, dt: float) -> list[float]:
        k1 = self._derivative(s, target, feedforward)
        k2 = self._derivative([a + 0.5 * dt * b for a, b in zip(s, k1)], target, feedforward)
        k3 = self._derivative([a + 0.5 * dt * b for a, b in zip(s, k2)], target, feedforward)
        k4 = self._derivative([a + dt * b for a, b in zip(s, k3)], target, feedforward)
        return [a + dt / 6 * (b + 2 * c + 2 * d + e) for a, b, c, d, e in zip(s, k1, k2, k3, k4)]

    def _rollout_heading(self) -> float:
        """Heading change while the rider stands the motorcycle up from the steady turn. The model is linear, so
        this is exact for the corner, and the rider starts the exit when that much of the corner is left."""
        turn = self.turn
        lean_rate = 0.0
        s = [turn.lean, turn.steer, lean_rate, 0.0, turn.torque, 0.0, 0.0, 0.0]
        t = 0.0
        while t < 30.0:
            s = self._rk4(s, 0.0, 0.0, self.dt)
            t += self.dt
            if abs(s[0]) < 1e-4 * abs(turn.lean) and abs(s[2]) < 1e-3 * abs(turn.lean):
                break
        return abs(s[5])

    def front_contact(self, s: list[float] | None = None) -> tuple[float, float]:
        s = s or self.state
        p, psi = self.p, s[5]
        side = -p.c * s[1] * math.cos(p.lam)  # the contact trails behind the steering axis, eq. (B 5)
        return (s[6] + p.w * math.cos(psi) - side * math.sin(psi), s[7] + p.w * math.sin(psi) + side * math.cos(psi))

    # ─── stepping ────────────────────────────────────────────────────────────

    def step(self) -> None:
        if self.stopped:
            return
        self._advance_phase()
        target = self.lean_target()
        feedforward = self.turn.torque if target else 0.0
        self.state = self._rk4(self.state, target, feedforward, self.dt)
        self.t += self.dt
        self._steps += 1
        s, d = self.state, self.corner.direction
        lateral_g = self.v * self._derivative(s, target, feedforward)[5] / self.g
        self.peak_lateral_g = max(self.peak_lateral_g, abs(lateral_g))
        if abs(lateral_g) > self.mu and not self._slid:
            self._slid = True
            self.events.append((self.t, f"The turn asks {abs(lateral_g):.2f} g of a surface that gives {self.mu:.2f}: "
                                        "the tyres would slide"))
        if self.phase in ("turning in", "holding"):
            self.peak_countersteer = max(self.peak_countersteer, -d * s[1])
            self.peak_push = max(self.peak_push, -d * s[4])
        if self.turn_start is not None and self.time_to_lean is None:
            self.wide_rear = max(self.wide_rear, -d * s[7])
            self.wide_front = max(self.wide_front, -d * self.front_contact()[1])
        if self._steps % self.record_every == 0:
            self._record(lateral_g)
        if self.t > 120:
            self._finish("time limit")

    def _advance_phase(self) -> None:
        s, corner = self.state, self.corner
        if self.phase == "approach" and self.t >= corner.approach - 1e-9:
            self.phase = "turning in"
            self.turn_start = self.t
            self.events.append((self.t, "The rider starts the turn"))
        elif self.phase == "turning in" and abs(s[0]) >= self.settled * abs(self.turn.lean):
            self.phase = "holding"
            self.time_to_lean = self.t - self.turn_start
            self.distance_to_lean = self.v * self.time_to_lean
            self.events.append((self.t, f"Leaned to {self.settled:.0%} of {math.degrees(abs(self.turn.lean)):.1f}° "
                                        f"after {self.time_to_lean:.2f} s"))
        if self.phase in ("turning in", "holding"):
            remaining = math.radians(corner.angle_deg) - corner.direction * s[5]
            if remaining <= self.rollout_heading:
                self.phase = "exiting"
                self.events.append((self.t, "The rider stands the motorcycle up"))
        elif self.phase == "exiting" and abs(s[0]) < 1e-3 * max(abs(self.turn.lean), 1e-3) and abs(s[2]) < 1e-3:
            self.phase = "done"
            self.events.append((self.t, f"Out of the corner, heading turned by {math.degrees(abs(s[5])):.1f}°"))
            self._finish("done")

    def _finish(self, outcome: str) -> None:
        self.stopped = True
        self.outcome = outcome
        self._record()

    def _record(self, lateral_g: float = 0.0) -> None:
        s = self.state
        fx, fy = self.front_contact()
        self.trace.append(CornerSample(self.t, s[6], s[7], fx, fy, math.degrees(s[5]), math.degrees(s[0]),
                                       math.degrees(self.lean_target()), math.degrees(s[1]), s[4], lateral_g))


def run_corner(p: WhippleParameters, corner: Corner, **kwargs) -> CornerSim:
    sim = CornerSim(p, corner, **kwargs)
    while not sim.stopped:
        sim.step()
    return sim
