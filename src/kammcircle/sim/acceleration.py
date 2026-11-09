"""Acceleration: an engine and gearbox driving the rear wheel of the suspended model.

The engine's full-throttle torque curve passes exactly through the published peak torque and peak power, with the
power curve flat at its published peak; its shape elsewhere is an assumption (docs/physics.md, section 15). The
clutch slips at a launch speed until the rear wheel catches up, the rider shifts at a set engine speed, and drive is
cut for the duration of each shift and at the rev limit. Aerodynamic drag and rolling resistance oppose the motion;
the drag area is back-solved from a reported top speed when no measured figure exists.

With the throttle part-open the engine gives a blend of its full-throttle torque and its closed-throttle drag
(friction and pumping), and with the clutch home its rotating parts add their inertia, multiplied by the square of the
overall ratio, to the rear wheel's. No figures for either are published; both are labelled stand-ins.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .braking import BrakingParameters
from .suspension import SuspendedBrakingSim, SuspensionParameters

RPM = 2 * math.pi / 60  # rad/s per rpm


@dataclass(frozen=True)
class Engine:
    peak_torque_nm: float
    peak_torque_rpm: float
    peak_power_kw: float
    peak_power_rpm: float
    idle_rpm: float
    limit_rpm: float
    idle_torque_share: float = 0.65
    drag_share_idle: float = 0.0  # closed-throttle drag at idle, as a share of the peak torque
    drag_share_limit: float = 0.0  # and at the rev limit; linear in between
    inertia: float = 0.0  # kg m², the rotating parts at crankshaft speed

    @property
    def _coefficients(self) -> tuple[float, float, float]:
        """a, b above peak torque (T = Tpk − a·d² − b·d³) and c below it (T = Tpk − c·d²)."""
        t_pk, n_t, n_p = self.peak_torque_nm, self.peak_torque_rpm, self.peak_power_rpm
        t_p = self.peak_power_kw * 1000 / (n_p * RPM)  # torque at peak power
        d = n_p - n_t
        b = (t_p / n_p - 2 * (t_pk - t_p) / d) / (d * d)  # from T(n_p) = t_p and dP/dn = 0 at n_p
        a = (t_pk - t_p - b * d ** 3) / (d * d)
        c = (1 - self.idle_torque_share) * t_pk / (n_t - self.idle_rpm) ** 2
        return a, b, c

    def torque(self, rpm: float) -> float:
        """Full-throttle torque in N m; zero at or beyond the rev limit."""
        if rpm >= self.limit_rpm:
            return 0.0
        a, b, c = self._coefficients
        d = rpm - self.peak_torque_rpm
        if d >= 0:
            return max(0.0, self.peak_torque_nm - a * d * d - b * d ** 3)
        return max(0.0, self.peak_torque_nm - c * d * d)

    def power_kw(self, rpm: float) -> float:
        return self.torque(rpm) * rpm * RPM / 1000

    def drag_torque(self, rpm: float) -> float:
        """Torque needed to turn the engine over with the throttle shut (friction and pumping), N m, positive."""
        x = min(max((rpm - self.idle_rpm) / (self.limit_rpm - self.idle_rpm), 0.0), 1.0)
        return (self.drag_share_idle + (self.drag_share_limit - self.drag_share_idle) * x) * self.peak_torque_nm

    def net_torque(self, rpm: float, throttle: float) -> float:
        """Crankshaft torque at a throttle opening between 0 (shut: the engine drags) and 1 (full)."""
        return throttle * self.torque(rpm) - (1.0 - throttle) * self.drag_torque(rpm)


@dataclass(frozen=True)
class Gearbox:
    primary: float
    gears: tuple[float, ...]
    secondary: float

    def overall(self, gear: int) -> float:
        """Engine revolutions per rear-wheel revolution in this gear (1-based)."""
        return self.primary * self.gears[gear - 1] * self.secondary


@dataclass
class Powertrain:
    engine: Engine
    gearbox: Gearbox
    efficiency: float
    shift_time: float
    shift_rpm: float
    launch_rpm: float
    gear: int = 1
    rpm: float = 0.0
    clutch_engaged: bool = False
    shift_timer: float = 0.0
    shifts: list[tuple[float, int]] = field(default_factory=list)
    limiting: bool = False

    @property
    def coupled(self) -> bool:
        """The clutch is home and no shift is under way, so the engine turns with the rear wheel."""
        return self.clutch_engaged and self.shift_timer <= 0.0

    def reflected_inertia(self) -> float:
        """The engine's rotating inertia as the rear wheel feels it: I·(overall ratio)² while coupled."""
        return self.engine.inertia * self.gearbox.overall(self.gear) ** 2 if self.coupled else 0.0

    def at_wheel(self, engine_torque: float, ratio: float) -> float:
        """Crankshaft torque carried to the rear wheel; the drivetrain's losses always oppose the flow of power."""
        return engine_torque * ratio * (self.efficiency if engine_torque > 0 else 1.0 / self.efficiency)

    def wheel_torque(self, wheel_omega: float, road_omega: float, throttle: float, dt: float, t: float) -> float:
        """Drive torque at the rear wheel for this step; updates gear, engine speed and clutch.

        ``road_omega`` is the wheel speed that the road speed alone would give: the rider lets the clutch home once
        the motorcycle, not a spinning tyre, has reached the launch speed.
        """
        ratio = self.gearbox.overall(self.gear)
        wheel_rpm = wheel_omega * ratio / RPM
        if self.shift_timer > 0.0:
            self.shift_timer -= dt
            self.rpm = max(wheel_rpm, self.engine.idle_rpm)
            return 0.0
        if not self.clutch_engaged:
            if road_omega * ratio / RPM >= self.launch_rpm:
                self.clutch_engaged = True
            else:  # the clutch slips: the engine holds the launch speed and passes on its torque there
                self.rpm = self.launch_rpm
                return self.efficiency * self.engine.torque(self.launch_rpm) * throttle * ratio
        self.rpm = max(wheel_rpm, self.engine.idle_rpm)
        if self.rpm >= self.shift_rpm and self.gear < len(self.gearbox.gears):
            self.gear += 1
            self.shift_timer = self.shift_time
            self.shifts.append((t, self.gear))
            return 0.0
        self.limiting = self.rpm >= self.engine.limit_rpm
        return self.at_wheel(self.engine.net_torque(self.rpm, throttle), ratio)


def drag_area_from_top_speed(engine: Engine, gearbox: Gearbox, top_kmh: float, mass: float, efficiency: float,
                             crr: float, rho: float, wheel_radius: float, g: float = 9.81) -> float:
    """CdA (m²) for which the power at the rear wheel, in the best gear, just balances drag and rolling resistance
    at the reported top speed."""
    v = top_kmh / 3.6
    wheel_rpm = v / wheel_radius / RPM
    power = max(engine.power_kw(wheel_rpm * gearbox.overall(n)) for n in range(1, len(gearbox.gears) + 1)) * 1000
    return (efficiency * power - crr * mass * g * v) / (0.5 * rho * v ** 3)


class AccelerationSim(SuspendedBrakingSim):
    """A launch or roll-on at a set throttle until a target speed (or the top speed) is reached."""

    def __init__(self, params: BrakingParameters, susp: SuspensionParameters, powertrain: Powertrain, *,
                 speed_kmh: float = 0.0, target_kmh: float | None = 100.0, throttle: float = 1.0,
                 throttle_control: bool = True, cda: float = 0.0, crr: float = 0.0, air_density: float = 1.225,
                 dt: float = 0.0005, record_every: int = 4) -> None:
        self.powertrain = powertrain
        self.requested_throttle = throttle
        self.throttle = throttle
        self.throttle_control = throttle_control
        self._throttle_factor = 1.0
        self.spin_time = 0.0
        self._traction_table = [(n, params.tyre.peak_traction_slip(n)) for n in (100.0 + 250.0 * i for i in range(17))]
        self.target = None if target_kmh is None else target_kmh / 3.6
        self.milestones: dict[int, float] = {}
        self.peak_accel = 0.0
        self._steady_since = None
        super().__init__(params, susp, speed_kmh, abs_front=False, abs_rear=False, dt=dt, record_every=record_every)
        self.cda, self.crr, self.air_density = cda, crr, air_density
        self.start = (self.t, self.x, self.v)
        if speed_kmh > 0:  # rolling start: in the gear that suits the speed, clutch home
            gearbox = powertrain.gearbox
            for gear in range(1, len(gearbox.gears) + 1):
                powertrain.gear = gear
                if self.wr * gearbox.overall(gear) / RPM < powertrain.shift_rpm:
                    break
            powertrain.clutch_engaged = True

    def _rear_inertia(self) -> float:
        return self.p.rear_wheel_inertia + self.powertrain.reflected_inertia()

    def _traction_peak(self, load: float) -> float:
        table = self._traction_table
        for (n0, k0), (n1, k1) in zip(table, table[1:]):
            if load <= n1:
                return k0 + (k1 - k0) * max(0.0, load - n0) / (n1 - n0)
        return table[-1][1]

    def _drive_torque(self, dt: float) -> float:
        # Throttle control (a skilled rider or traction control): ease off when the rear tyre slips past its peak
        # or the front wheel leaves the road, then feed the throttle back in.
        if self.throttle_control:
            peak = self._traction_peak(max(self.nr, 50.0))
            if self.kr > 1.15 * peak or self.max_front_lift_now > 0.005:
                self._throttle_factor = max(0.0, self._throttle_factor - 6.0 * dt)
            elif self.kr < 0.95 * peak:
                self._throttle_factor = min(1.0, self._throttle_factor + 2.0 * dt)
        self.throttle = self.requested_throttle * (self._throttle_factor if self.throttle_control else 1.0)
        if self.kr > 0.3:
            self.spin_time += dt
        return self.powertrain.wheel_torque(self.wr, max(self.v, 0.0) / self.p.rear_radius, self.throttle, dt, self.t)

    @property
    def max_front_lift_now(self) -> float:
        return max(0.0, self.front_axle_world()[1] - self.p.front_radius)

    def _check_end(self, rear_airborne: bool, nf: float, decel: float) -> None:
        accel = -decel
        self.peak_accel = max(self.peak_accel, accel)
        for kmh in (50, 100):
            if kmh not in self.milestones and self.v * 3.6 >= kmh and self.start[2] * 3.6 < kmh:
                self.milestones[kmh] = self.t - self.start[0]
                self.events.append((self.t, f"{kmh} km/h after {self.milestones[kmh]:.2f} s"))
        if self.front_airborne and self._past_loop_over():
            self.events.append((self.t, "Looped over backwards (the wheelie passed the point of no return)"))
            self._finish("looped over")
        elif self.target is not None and self.v >= self.target:
            self.events.append((self.t, f"Reached {self.target * 3.6:.0f} km/h"))
            self._finish("reached")
        elif self.target is None:
            if accel < 0.02:
                self._steady_since = self._steady_since if self._steady_since is not None else self.t
                if self.t - self._steady_since > 2.0:
                    self.events.append((self.t, f"Top speed {self.v * 3.6:.0f} km/h"))
                    self._finish("top speed")
            else:
                self._steady_since = None

    def _past_loop_over(self) -> bool:
        """Mirror of the stoppie test: pitch energy about the rear axle that can lift the CoG over it."""
        fx, fz = self.front_axle_world()
        rx, rz = self.rear_axle_world()
        m = self.p.mass
        gx = (self.m_s * self.q[0] + self.m_uf * fx + self.m_ur * rx) / m - rx
        gz = (self.m_s * self.q[1] + self.m_uf * fz + self.m_ur * rz) / m - rz
        if gx <= 0.0:
            return True
        thd = self.theta_dot
        if thd >= 0.0:  # not rotating nose-up
            return False
        inertia = (self.i_s + self.m_s * ((self.q[0] - rx) ** 2 + (self.q[1] - rz) ** 2)
                   + self.m_uf * ((fx - rx) ** 2 + (fz - rz) ** 2))
        return 0.5 * inertia * thd * thd >= m * self.p.g * (math.hypot(gx, gz) - gz)

    def acceleration_summary(self) -> dict[str, float | str | None]:
        return {
            "outcome": self.outcome or "running",
            "t_50": self.milestones.get(50),
            "t_100": self.milestones.get(100),
            "time": self.t - self.start[0],
            "distance": self.x - self.start[1],
            "speed_kmh": self.v * 3.6,
            "peak_accel_g": self.peak_accel / self.p.g,
            "max_wheelie_mm": 1000 * max(0.0, self.max_front_lift),
            "wheelspin_s": self.spin_time,
        }


def run_acceleration(params: BrakingParameters, susp: SuspensionParameters, powertrain: Powertrain, *,
                     speed_kmh: float = 0.0, target_kmh: float | None = 100.0, throttle: float = 1.0,
                     throttle_control: bool = True, cda: float = 0.0, crr: float = 0.0, air_density: float = 1.225,
                     max_time: float = 60.0, dt: float = 0.0005) -> AccelerationSim:
    sim = AccelerationSim(params, susp, powertrain, speed_kmh=speed_kmh, target_kmh=target_kmh, throttle=throttle,
                          throttle_control=throttle_control, cda=cda, crr=crr, air_density=air_density, dt=dt)
    while not sim.stopped and sim.t < max_time:
        sim.step(0.0, 0.0)
    sim.stop_at_time_limit()
    return sim
