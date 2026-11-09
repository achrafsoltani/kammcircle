"""In-plane braking dynamics: the motorcycle and rider as one rigid body on two spinning wheels.

Degrees of freedom: the front axle's position and speed along the road, the body's pitch about the front axle once
the rear wheel lifts, and each wheel's spin. Each step solves the contact loads exactly for the current tyre forces
(two unknowns with both wheels down; three with the rear in the air), then integrates. Wheel spin is integrated
semi-implicitly through the tyre's slip stiffness, which keeps the stiff tyre–wheel loop stable at a 0.5 ms step.

Sign conventions: x forward, z up; pitch θ and wheel spin ω are positive in the sense of forward rolling, so a
positive θ lifts the rear. Derivation and assumptions: docs/physics.md, section 11.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .tyre import LongitudinalTyre

V_EPS = 1.0  # m/s: slip ratio regularised below walking pace
V_STOP = 0.3  # m/s: the run ends here; the last few centimetres are extrapolated
HEAVY_SLIP = -0.5  # slip ratio beyond which the tyre leaves a mark


@dataclass(frozen=True)
class ABSSettings:
    release_factor: float = 1.3
    reapply_factor: float = 1.0
    release_rate: float = 10.0
    apply_rate: float = 3.0


@dataclass(frozen=True)
class BrakingParameters:
    wheelbase: float  # m
    front_radius: float  # m
    rear_radius: float  # m
    mass: float  # kg, motorcycle and rider
    cog_ahead_of_rear: float  # b, m, from the rear contact patch
    cog_height: float  # h, m
    pitch_inertia: float  # kg m², about the combined centre of gravity
    front_wheel_inertia: float  # kg m², spin
    rear_wheel_inertia: float  # kg m², spin
    tyre: LongitudinalTyre
    front_brake_max: float  # N m at full lever
    rear_brake_max: float  # N m at full pedal
    abs_settings: ABSSettings = ABSSettings()
    g: float = 9.81

    @property
    def weight(self) -> float:
        return self.mass * self.g

    @property
    def static_front_load(self) -> float:
        return self.weight * self.cog_ahead_of_rear / self.wheelbase

    @property
    def static_rear_load(self) -> float:
        return self.weight - self.static_front_load

    @property
    def lift_deceleration_g(self) -> float:
        """Deceleration, in g, at which the rear wheel unloads (wheel inertia ignored): (L − b) / h."""
        return (self.wheelbase - self.cog_ahead_of_rear) / self.cog_height


@dataclass
class ABSChannel:
    """A generic slip-band anti-lock controller for one wheel; not any manufacturer's algorithm.

    It releases brake torque while the wheel slips beyond ``release_factor`` × the tyre's peak slip, and re-applies it,
    up to the rider's demand, once the slip has recovered to ``reapply_factor`` × the peak slip.
    """

    enabled: bool
    release_factor: float = 1.3
    reapply_factor: float = 1.0
    release_rate: float = 10.0  # share of the maximum torque removed per second
    apply_rate: float = 3.0  # share of the maximum torque restored per second
    applied: float = 0.0
    releasing: bool = False
    regulating: bool = False  # from the first release until the rider's demand is met again
    cycles: int = 0

    def update(self, commanded: float, kappa: float, peak_slip: float, max_torque: float, dt: float) -> float:
        if not self.enabled:
            self.applied = commanded
            return self.applied
        if kappa < self.release_factor * peak_slip:  # peak_slip is negative
            if not self.releasing:
                self.cycles += 1
            self.releasing = self.regulating = True
            self.applied = max(0.0, self.applied - self.release_rate * max_torque * dt)
        else:
            if kappa > self.reapply_factor * peak_slip:
                self.releasing = False
            if not self.regulating:
                self.applied = commanded  # normal braking: the demand passes straight through
            elif not self.releasing:
                self.applied += self.apply_rate * max_torque * dt
                if self.applied >= commanded:
                    self.regulating = False
        self.applied = min(self.applied, commanded)
        return self.applied

    @property
    def intervening(self) -> bool:
        return self.enabled and self.regulating


@dataclass
class Sample:
    t: float
    x: float
    v: float
    a: float
    nf: float
    nr: float
    kf: float
    kr: float
    theta: float
    lever_f: float
    lever_r: float
    torque_f: float
    torque_r: float
    abs_f: bool
    abs_r: bool


@dataclass
class Summary:
    brake_speed_kmh: float
    stopping_distance: float  # m, from the first touch of a brake
    stopping_time: float  # s
    mean_decel_g: float
    peak_decel_g: float
    max_rear_lift_mm: float
    front_locked_s: float
    rear_locked_s: float
    abs_cycles_front: int
    abs_cycles_rear: int
    outcome: str  # "stopped", "pitched over" or "time limit"


class BrakingSim:
    def __init__(
        self, params: BrakingParameters, speed_kmh: float, *, abs_front: bool = True, abs_rear: bool = True,
        dt: float = 0.0005, record_every: int = 4,
    ) -> None:
        self.p = params
        self.dt = dt
        self.record_every = record_every
        v0 = speed_kmh / 3.6
        self.speed0 = v0
        self.t = 0.0
        self.x = 0.0
        self.v = v0
        self.a = 0.0
        self.theta = 0.0
        self.theta_dot = 0.0
        self.grounded = True
        self.wf = v0 / params.front_radius
        self.wr = v0 / params.rear_radius
        self.angle_f = 0.0
        self.angle_r = 0.0
        self.locked_f = False
        self.locked_r = False
        self.nf = params.static_front_load
        self.nr = params.static_rear_load
        self.kf = 0.0
        self.kr = 0.0
        self.lever_f = 0.0
        self.lever_r = 0.0
        settings = params.abs_settings
        self.abs_f = ABSChannel(abs_front, settings.release_factor, settings.reapply_factor,
                                settings.release_rate, settings.apply_rate)
        self.abs_r = ABSChannel(abs_rear, settings.release_factor, settings.reapply_factor,
                                settings.release_rate, settings.apply_rate)
        self.brake_start: tuple[float, float, float] | None = None  # t, x, v
        self.stopped = False
        self.outcome = ""
        self.extra_distance = 0.0
        self.events: list[tuple[float, str]] = []
        self.trace: list[Sample] = []
        self.skids_f: list[list[float]] = []  # [x_start, x_end] intervals of the front contact patch
        self.skids_r: list[list[float]] = []
        self.peak_decel = 0.0
        self.max_theta = 0.0
        self.locked_time_f = 0.0
        self.locked_time_r = 0.0
        self._step_count = 0
        self._peak_table = self._build_peak_table()
        self._record()

    # ─── geometry helpers ────────────────────────────────────────────────────

    @property
    def rear_contact_x(self) -> float:
        return self.x - self.p.wheelbase * math.cos(self.theta)

    @property
    def rear_lift(self) -> float:
        """Height of the rear contact patch above the road, in metres."""
        return self.p.wheelbase * math.sin(self.theta)

    def _build_peak_table(self) -> list[tuple[float, float]]:
        loads = [100.0 + 250.0 * i for i in range(17)]
        return [(n, self.p.tyre.peak_braking_slip(n)) for n in loads]

    def peak_slip(self, load: float) -> float:
        table = self._peak_table
        if load <= table[0][0]:
            return table[0][1]
        for (n0, k0), (n1, k1) in zip(table, table[1:]):
            if load <= n1:
                return k0 + (k1 - k0) * (load - n0) / (n1 - n0)
        return table[-1][1]

    # ─── one integration step ────────────────────────────────────────────────

    def step(self, lever_f: float, lever_r: float) -> None:
        if self.stopped:
            return
        p, dt, tyre = self.p, self.dt, self.p.tyre
        self.lever_f = lever_f = min(max(lever_f, 0.0), 1.0)
        self.lever_r = lever_r = min(max(lever_r, 0.0), 1.0)
        if self.brake_start is None and (lever_f > 0 or lever_r > 0):
            self.brake_start = (self.t, self.x, self.v)

        v_den = max(abs(self.v), V_EPS)
        kf = -1.0 if self.locked_f else max(-1.0, min(1.0, (self.wf * p.front_radius - self.v) / v_den))
        kr = -1.0 if self.locked_r else max(-1.0, min(1.0, (self.wr * p.rear_radius - self.v) / v_den))
        load_f = max(self.nf, 50.0)
        load_r = max(self.nr, 50.0)
        phi_f = tyre.coefficient(kf, load_f)
        phi_r = tyre.coefficient(kr, load_r) if self.grounded else 0.0

        torque_f = self.abs_f.update(lever_f * p.front_brake_max, kf, self.peak_slip(load_f), p.front_brake_max, dt)
        torque_r = self.abs_r.update(lever_r * p.rear_brake_max, kr, self.peak_slip(load_r), p.rear_brake_max, dt)

        # A locked wheel stays locked while the brake can hold the tyre's pull on it.
        if self.locked_f and torque_f < p.front_radius * abs(phi_f) * load_f:
            self._set_lock("f", False)
        if self.locked_r and torque_r < p.rear_radius * abs(phi_r) * load_r:
            self._set_lock("r", False)
        rolling_f, rolling_r = not self.locked_f, not self.locked_r

        if self.grounded:
            nf, nr = self._solve_grounded(phi_f, phi_r, torque_f, torque_r, rolling_f, rolling_r)
            if nr < 0.0:
                self.grounded = False
                phi_r = 0.0
                self.events.append((self.t, "Rear wheel lifts off the road"))
        front_unloaded = False
        if self.grounded:
            a = (phi_f * nf + phi_r * nr) / p.mass
            theta_dd = 0.0
        else:
            nf, a, theta_dd = self._solve_lifted(phi_f, torque_f, torque_r, rolling_f, rolling_r)
            front_unloaded = nf <= 0.0
            nr = 0.0
        ff, fr = phi_f * nf, phi_r * nr
        decel_cog = -(ff + fr) / p.mass  # what the rider feels; equals −a while both wheels are down

        self.wf = self._spin(self.wf, "f", ff, nf, kf, torque_f, p.front_radius, p.front_wheel_inertia, v_den)
        self.wr = self._spin(self.wr, "r", fr, nr, kr, torque_r, p.rear_radius, p.rear_wheel_inertia, v_den)

        self.v += a * dt
        self.x += self.v * dt
        if not self.grounded:
            self.theta_dot += theta_dd * dt
            self.theta += self.theta_dot * dt
            if self.theta <= 0.0:
                self.theta = 0.0
                self.theta_dot = 0.0
                self.grounded = True
                self.events.append((self.t, "Rear wheel lands"))
            self.max_theta = max(self.max_theta, self.theta)

        self.angle_f += self.wf * dt
        self.angle_r += self.wr * dt
        self.nf, self.nr, self.kf, self.kr, self.a = nf, nr, kf, kr, -decel_cog
        self._torques = (torque_f, torque_r)
        self.peak_decel = max(self.peak_decel, decel_cog)
        self.locked_time_f += dt if self.locked_f else 0.0
        self.locked_time_r += dt if self.locked_r else 0.0
        self._track_skid(self.skids_f, self.x, kf <= HEAVY_SLIP and nf > 0)
        self._track_skid(self.skids_r, self.rear_contact_x, kr <= HEAVY_SLIP and nr > 0)
        self.t += dt
        self._step_count += 1

        if not self.grounded and (front_unloaded or self._past_point_of_no_return()):
            # The body now carries enough pitch energy to lift its centre of gravity over the front axle even if
            # the brake were released: the motorcycle goes over the front wheel.
            self.events.append((self.t, "Pitched over the front wheel (past the point of no return)"))
            self._finish("pitched over")
        elif self.v <= V_STOP:
            if decel_cog > 0:
                self.extra_distance = self.v * self.v / (2 * decel_cog)
            self.events.append((self.t, "Stopped"))
            self._finish("stopped")
        if self._step_count % self.record_every == 0 or self.stopped:
            self._record()

    def run_for(self, duration: float, lever_f: float, lever_r: float) -> None:
        for _ in range(max(1, round(duration / self.dt))):
            self.step(lever_f, lever_r)

    # ─── the two contact phases ──────────────────────────────────────────────

    def _solve_grounded(self, phi_f, phi_r, torque_f, torque_r, rolling_f, rolling_r) -> tuple[float, float]:
        """Both wheels down, no pitch: vertical balance and the angular-momentum balance about the CoG.

        (L − b)·Nf − b·Nr + h·(Ff + Fr) + Σ I·dω/dt = 0, with I·dω/dt = −R·F − T for a rolling wheel, 0 if locked.
        """
        p = self.p
        b, h, L = p.cog_ahead_of_rear, p.cog_height, p.wheelbase
        c1 = (L - b) + h * phi_f - (p.front_radius * phi_f if rolling_f else 0.0)
        c2 = -b + h * phi_r - (p.rear_radius * phi_r if rolling_r else 0.0)
        rhs = (torque_f if rolling_f else 0.0) + (torque_r if rolling_r else 0.0)
        nf = (rhs - c2 * p.weight) / (c1 - c2)
        return nf, p.weight - nf

    def _solve_lifted(self, phi_f, torque_f, torque_r, rolling_f, rolling_r) -> tuple[float, float, float]:
        """Rear wheel in the air: the body pitches about the front axle. Returns (Nf, axle acceleration, θ'')."""
        p = self.p
        gx, gz = -(p.wheelbase - p.cog_ahead_of_rear), p.cog_height - p.front_radius
        s, c = math.sin(self.theta), math.cos(self.theta)
        big_p = -gx * s + gz * c  # d(G_x)/dθ
        big_q = -gx * c - gz * s  # d(G_z)/dθ, also the CoG's distance behind the front contact patch
        r_fz = -(p.front_radius - gx * s + gz * c)  # front contact patch relative to the CoG, vertical
        k = big_q - r_fz * phi_f - (p.front_radius * phi_f if rolling_f else 0.0)
        rhs = (torque_f if rolling_f else 0.0) + (torque_r if rolling_r and self.wr > 0.0 else 0.0)
        td2 = self.theta_dot ** 2
        theta_dd = (rhs - k * p.mass * (p.g - big_p * td2)) / (p.pitch_inertia + k * p.mass * big_q)
        nf = p.mass * (p.g + big_q * theta_dd - big_p * td2)
        if nf <= 0.0:
            return 0.0, 0.0, theta_dd  # the front tyre unloads: the caller ends the run
        a = phi_f * nf / p.mass - big_p * theta_dd - big_q * td2
        return nf, a, theta_dd

    def _past_point_of_no_return(self) -> bool:
        """True once ½·I_A·θ'² reaches m·g·(height the CoG still has to climb to sit above the front axle).

        I_A is the pitch inertia about the front axle. From here the stoppie becomes a flip whatever the rider does.
        """
        p = self.p
        gx, gz = -(p.wheelbase - p.cog_ahead_of_rear), p.cog_height - p.front_radius
        d2 = gx * gx + gz * gz
        cog_above_axle = -gx * math.sin(self.theta) + gz * math.cos(self.theta)
        if self.theta_dot <= 0.0:
            return cog_above_axle >= math.sqrt(d2)
        energy = 0.5 * (p.pitch_inertia + p.mass * d2) * self.theta_dot ** 2
        return energy >= p.mass * p.g * (math.sqrt(d2) - cog_above_axle)

    # ─── wheels ──────────────────────────────────────────────────────────────

    def _spin(self, omega, wheel, force, load, kappa, torque, radius, inertia, v_den) -> float:
        """I·dω/dt = −R·F − T, with F linearised in ω through the slip stiffness (implicit on the stable side)."""
        if getattr(self, f"locked_{wheel}"):
            return 0.0
        stiffness = max(self.p.tyre.slope(kappa, max(load, 50.0)), 0.0) * load * radius / v_den  # dF/dω
        omega_new = omega + self.dt * (-radius * force - torque) / (inertia + self.dt * radius * stiffness)
        if omega_new <= 0.0:
            if torque > 0.0:
                self._set_lock(wheel, True)
            return 0.0
        return omega_new

    def _set_lock(self, wheel: str, locked: bool) -> None:
        if getattr(self, f"locked_{wheel}") == locked:
            return
        setattr(self, f"locked_{wheel}", locked)
        if self.v > 2.0:  # below walking pace a brief lock is part of coming to rest, not an event
            if wheel == "f":
                text = ("Front wheel locks: a real motorcycle loses its steering and usually falls; this model keeps "
                        "it upright" if locked else "Front wheel turns again")
            else:
                text = "Rear wheel locks" if locked else "Rear wheel turns again"
            self.events.append((self.t, text))

    # ─── bookkeeping ─────────────────────────────────────────────────────────

    @staticmethod
    def _track_skid(intervals: list[list[float]], x: float, skidding: bool) -> None:
        if skidding:
            if intervals and intervals[-1][1] is None:
                return
            intervals.append([x, None])
        elif intervals and intervals[-1][1] is None:
            intervals[-1][1] = x

    def _finish(self, outcome: str) -> None:
        self.stopped = True
        self.outcome = outcome
        for intervals, x in ((self.skids_f, self.x), (self.skids_r, self.rear_contact_x)):
            if intervals and intervals[-1][1] is None:
                intervals[-1][1] = x

    def stop_at_time_limit(self) -> None:
        if not self.stopped:
            self.events.append((self.t, "Time limit reached"))
            self._finish("time limit")
            self._record()

    def _record(self) -> None:
        torque_f, torque_r = getattr(self, "_torques", (0.0, 0.0))
        self.trace.append(Sample(
            t=self.t, x=self.x, v=self.v, a=self.a, nf=self.nf, nr=self.nr, kf=self.kf, kr=self.kr,
            theta=self.theta, lever_f=self.lever_f, lever_r=self.lever_r,
            torque_f=torque_f / self.p.front_brake_max, torque_r=torque_r / self.p.rear_brake_max,
            abs_f=self.abs_f.intervening, abs_r=self.abs_r.intervening,
        ))

    def summary(self) -> Summary:
        if self.brake_start is None:
            t0, x0, v0 = self.t, self.x, self.v
        else:
            t0, x0, v0 = self.brake_start
        distance = self.x + self.extra_distance - x0
        mean = v0 * v0 / (2 * distance * self.p.g) if distance > 0 and self.outcome == "stopped" else 0.0
        return Summary(
            brake_speed_kmh=v0 * 3.6,
            stopping_distance=distance,
            stopping_time=self.t - t0,
            mean_decel_g=mean,
            peak_decel_g=self.peak_decel / self.p.g,
            max_rear_lift_mm=1000 * self.p.wheelbase * math.sin(self.max_theta),
            front_locked_s=self.locked_time_f,
            rear_locked_s=self.locked_time_r,
            abs_cycles_front=self.abs_f.cycles,
            abs_cycles_rear=self.abs_r.cycles,
            outcome=self.outcome or "running",
        )


@dataclass
class LeverRamp:
    """The rider's hands and foot: each lever travels its full range in ``squeeze_time`` seconds."""

    squeeze_time: float = 0.3
    front: float = 0.0
    rear: float = 0.0

    def update(self, target_front: float, target_rear: float, dt: float) -> None:
        rate = dt / max(self.squeeze_time, 1e-3)
        self.front += max(-rate, min(rate, target_front - self.front))
        self.rear += max(-rate, min(rate, target_rear - self.rear))


@dataclass
class BrakingRun:
    sim: BrakingSim
    levers: LeverRamp = field(default_factory=LeverRamp)


def run_braking(
    params: BrakingParameters, speed_kmh: float, front: float, rear: float, *, squeeze_time: float = 0.3,
    abs_front: bool = True, abs_rear: bool = True, brake_at: float = 0.0, max_time: float = 20.0,
    dt: float = 0.0005,
) -> BrakingSim:
    """Cruise at ``speed_kmh`` until ``brake_at`` seconds, then squeeze to the given lever positions and hold."""
    sim = BrakingSim(params, speed_kmh, abs_front=abs_front, abs_rear=abs_rear, dt=dt)
    levers = LeverRamp(squeeze_time)
    while not sim.stopped and sim.t < max_time:
        braking = sim.t >= brake_at
        levers.update(front if braking else 0.0, rear if braking else 0.0, dt)
        sim.step(levers.front, levers.rear)
    sim.stop_at_time_limit()
    return sim
