"""Braking with suspension and compliant tyres.

Bodies: the sprung mass (motorcycle frame, engine and rider: surge, heave and pitch), the front unsprung mass
(wheel and fork lowers) sliding along the steering axis, and the rear unsprung mass (wheel and swingarm) moving
perpendicular to the frame. Each tyre is a radial spring and damper that can leave the road, so a stoppie happens
when the rear tyre's load reaches zero rather than by switching models. Generalised coordinates
q = (x, z, θ, s_f, s_r): the sprung centre of gravity, the pitch (positive nose down), and the front and rear
suspension compressions measured from full extension. Wheel spin is integrated as in the rigid model.

The equations M(q)·q'' = Q(q, q') come from the bodies' Jacobians (virtual work); docs/physics.md, section 11.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .braking import HEAVY_SLIP, V_EPS, V_STOP, BrakingParameters, BrakingSim

LIFT_REPORTED = 0.010  # m: a rear tyre that clears the road by less than this is unloaded, not lifted


@dataclass(frozen=True)
class SuspensionParameters:
    rake_deg: float
    front_travel: float  # m
    rear_travel: float  # m
    front_sag: float  # m, compression with the rider aboard
    rear_sag: float  # m
    front_unsprung: float  # kg
    rear_unsprung: float  # kg
    tyre_k_front: float  # N/m
    tyre_k_rear: float  # N/m
    damping_ratio: float
    tyre_damping_ratio: float
    stop_k: float  # N/m
    stop_c: float  # N s/m
    bike_mass: float
    bike_cog_x: float  # m ahead of the rear contact patch
    bike_cog_h: float  # m
    rider_mass: float
    rider_cog_x: float
    rider_cog_h: float
    bike_own_pitch_inertia: float
    rider_own_pitch_inertia: float
    extra_masses: tuple[tuple[float, float, float, float], ...] = ()  # pillion, luggage: (kg, x, h, own inertia)
    spring_load_front: float = 0.0  # N on the tyre with the rider alone, for sizing the springs (0: the loaded state)
    spring_load_rear: float = 0.0


def _rot(theta: float, v: tuple[float, float]) -> tuple[float, float]:
    """Body frame (x forward, z up) to world for a pitch θ, positive nose down."""
    c, s = math.cos(theta), math.sin(theta)
    return v[0] * c + v[1] * s, -v[0] * s + v[1] * c


def _drot(theta: float, v: tuple[float, float]) -> tuple[float, float]:
    """d(rot)/dθ applied to v."""
    c, s = math.cos(theta), math.sin(theta)
    return -v[0] * s + v[1] * c, -v[0] * c - v[1] * s


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for the small dense systems used here."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        p = m[col][col]
        for r in range(col + 1, n):
            f = m[r][col] / p
            if f:
                row, top = m[r], m[col]
                for k in range(col, n + 1):
                    row[k] -= f * top[k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][k] * x[k] for k in range(r + 1, n))) / m[r][r]
    return x


class SuspendedBrakingSim(BrakingSim):
    """The braking run with suspension; same interface as BrakingSim, plus suspension travel and pitch."""

    def __init__(self, params: BrakingParameters, susp: SuspensionParameters, speed_kmh: float, *,
                 abs_front: bool = True, abs_rear: bool = True, dt: float = 0.0005, record_every: int = 4) -> None:
        self.susp = susp
        p, g = params, params.g
        eps = math.radians(susp.rake_deg)
        self.e_f = (-math.sin(eps), math.cos(eps))  # along the steering axis, from the axle towards the head
        self.e_r = (0.0, 1.0)
        L, rf, rr = p.wheelbase, p.front_radius, p.rear_radius
        nf0, nr0 = p.static_front_load, p.static_rear_load
        m_uf, m_ur = susp.front_unsprung, susp.rear_unsprung
        self.m_uf, self.m_ur = m_uf, m_ur

        # Static configuration, rider aboard, pitch zero: front contact patch at x = 0.
        axle_f = (0.0, rf - nf0 / susp.tyre_k_front)
        axle_r = (-L, rr - nr0 / susp.tyre_k_rear)
        bike = (-(L - susp.bike_cog_x), susp.bike_cog_h)
        rider = (-(L - susp.rider_cog_x), susp.rider_cog_h)
        m_bs = susp.bike_mass - m_uf - m_ur
        bike_sprung = tuple((susp.bike_mass * bike[i] - m_uf * axle_f[i] - m_ur * axle_r[i]) / m_bs for i in (0, 1))
        # Sprung point masses: the motorcycle's sprung part, the rider, and any pillion or luggage.
        sprung = [(m_bs, bike_sprung, susp.bike_own_pitch_inertia),
                  (susp.rider_mass, rider, susp.rider_own_pitch_inertia)]
        sprung += [(m, (-(L - x), h), own) for m, x, h, own in susp.extra_masses]
        self.m_s = sum(m for m, _, _ in sprung)
        r_s = tuple(sum(m * pos[i] for m, pos, _ in sprung) / self.m_s for i in (0, 1))
        self.i_s = sum(own + m * ((pos[0] - r_s[0]) ** 2 + (pos[1] - r_s[1]) ** 2) for m, pos, own in sprung)

        # Springs without preload, sized for the sag with the rider alone; damping as a fraction of critical.
        # A pillion or luggage then compresses them further, as it would on the road.
        spring_f = susp.spring_load_front or nf0
        spring_r = susp.spring_load_rear or nr0
        self.k_f = (spring_f - m_uf * g) * math.cos(eps) / susp.front_sag
        self.k_r = (spring_r - m_ur * g) / susp.rear_sag
        self.c_f = 2 * susp.damping_ratio * math.sqrt(self.k_f * (spring_f - m_uf * g) / g)
        self.c_r = 2 * susp.damping_ratio * math.sqrt(self.k_r * (spring_r - m_ur * g) / g)
        self.ct_f = 2 * susp.tyre_damping_ratio * math.sqrt(susp.tyre_k_front * m_uf)
        self.ct_r = 2 * susp.tyre_damping_ratio * math.sqrt(susp.tyre_k_rear * m_ur)
        self.static_front_compression = (nf0 - m_uf * g) * math.cos(eps) / self.k_f
        self.static_rear_compression = (nr0 - m_ur * g) / self.k_r

        self.axle_f_static = (axle_f[0] - r_s[0], axle_f[1] - r_s[1])  # body frame, from the sprung CoG
        self.a_f0 = (self.axle_f_static[0] - self.static_front_compression * self.e_f[0],
                     self.axle_f_static[1] - self.static_front_compression * self.e_f[1])
        self.a_r0 = (axle_r[0] - r_s[0], axle_r[1] - r_s[1] - self.static_rear_compression)

        v0 = speed_kmh / 3.6
        self.q = [r_s[0], r_s[1], 0.0, self.static_front_compression, self.static_rear_compression]
        self.qd = [v0, 0.0, 0.0, 0.0, 0.0]
        self.rear_airborne = False
        self._lift_reported = False
        self.front_airborne = False
        self._front_lift_reported = False
        self.max_front_lift = 0.0
        self.cda = 0.0  # m², drag area of motorcycle and rider; 0 leaves aerodynamic drag out
        self.crr = 0.0  # rolling-resistance coefficient; 0 leaves it out
        self.air_density = 1.225
        self.drive_torque = 0.0  # N m at the rear wheel, from a powertrain when one is fitted
        self._flags: set[str] = set()
        super().__init__(params, speed_kmh, abs_front=abs_front, abs_rear=abs_rear, dt=dt, record_every=record_every)
        self.x, self.v = self.front_axle_world()[0], v0

    # ─── kinematics ──────────────────────────────────────────────────────────

    def _axles(self) -> tuple[tuple[float, float], tuple[float, float]]:
        _, _, _, sf, sr = self.q
        b_f = (self.a_f0[0] + sf * self.e_f[0], self.a_f0[1] + sf * self.e_f[1])
        b_r = (self.a_r0[0] + sr * self.e_r[0], self.a_r0[1] + sr * self.e_r[1])
        return b_f, b_r

    def front_axle_world(self) -> tuple[float, float]:
        b_f, _ = self._axles()
        w = _rot(self.q[2], b_f)
        return self.q[0] + w[0], self.q[1] + w[1]

    def rear_axle_world(self) -> tuple[float, float]:
        _, b_r = self._axles()
        w = _rot(self.q[2], b_r)
        return self.q[0] + w[0], self.q[1] + w[1]

    def body_point_world(self, bx: float, bz: float) -> tuple[float, float]:
        """A point fixed in the frame, given relative to the front axle's static position (body axes)."""
        w = _rot(self.q[2], (self.axle_f_static[0] + bx, self.axle_f_static[1] + bz))
        return self.q[0] + w[0], self.q[1] + w[1]

    @property
    def rear_contact_x(self) -> float:
        return self.rear_axle_world()[0]

    @property
    def rear_lift(self) -> float:
        return max(0.0, self.rear_axle_world()[1] - self.p.rear_radius)

    @property
    def front_compression(self) -> float:
        return self.q[3]

    @property
    def rear_compression(self) -> float:
        return self.q[4]

    # ─── forces ──────────────────────────────────────────────────────────────

    def _suspension_force(self, s: float, sd: float, k: float, c: float, travel: float) -> float:
        force = k * s + c * sd
        if s < 0.0:  # topped out
            force = self.susp.stop_k * s + self.susp.stop_c * sd
        elif s > travel:  # bottomed out
            force += self.susp.stop_k * (s - travel) + self.susp.stop_c * sd
        return force

    def step(self, lever_f: float, lever_r: float) -> None:
        if self.stopped:
            return
        p, s, dt, tyre, g = self.p, self.susp, self.dt, self.p.tyre, self.p.g
        self.lever_f = lever_f = min(max(lever_f, 0.0), 1.0)
        self.lever_r = lever_r = min(max(lever_r, 0.0), 1.0)
        if self.brake_start is None and (lever_f > 0 or lever_r > 0):
            self.brake_start = (self.t, self.x, self.v)

        x, z, th, sf, sr = self.q
        xd, zd, thd, sfd, srd = self.qd
        b_f, b_r = self._axles()
        jt_f, jt_r = _drot(th, b_f), _drot(th, b_r)  # ∂(axle)/∂θ
        ej_f, ej_r = _rot(th, self.e_f), _rot(th, self.e_r)  # ∂(axle)/∂s
        wf_pos, wr_pos = _rot(th, b_f), _rot(th, b_r)
        pf = (x + wf_pos[0], z + wf_pos[1])
        pr = (x + wr_pos[0], z + wr_pos[1])
        vf = (xd + jt_f[0] * thd + ej_f[0] * sfd, zd + jt_f[1] * thd + ej_f[1] * sfd)
        vr = (xd + jt_r[0] * thd + ej_r[0] * srd, zd + jt_r[1] * thd + ej_r[1] * srd)

        # Tyres: radial springs that can leave the road.
        def normal(depth: float, rate: float, k: float, c: float) -> float:
            return max(0.0, k * depth - c * rate) if depth > 0.0 else 0.0

        nf = normal(p.front_radius - pf[1], vf[1], s.tyre_k_front, self.ct_f)
        nr = normal(p.rear_radius - pr[1], vr[1], s.tyre_k_rear, self.ct_r)
        airborne = nr == 0.0 and p.rear_radius - pr[1] <= 0.0
        if airborne != self.rear_airborne:
            self.rear_airborne = airborne
            self.grounded = not airborne
            if not airborne and self._lift_reported:
                self.events.append((self.t, "Rear wheel lands"))
            self._lift_reported = False
        if airborne and not self._lift_reported and pr[1] - p.rear_radius > LIFT_REPORTED:
            self._lift_reported = True
            self.events.append((self.t, "Rear wheel lifts off the road"))
        front_airborne = nf == 0.0 and p.front_radius - pf[1] <= 0.0
        if front_airborne != self.front_airborne:
            self.front_airborne = front_airborne
            if not front_airborne and self._front_lift_reported:
                self.events.append((self.t, "Front wheel lands"))
            self._front_lift_reported = False
        if front_airborne and not self._front_lift_reported and pf[1] - p.front_radius > LIFT_REPORTED:
            self._front_lift_reported = True
            self.events.append((self.t, "Front wheel lifts off the road (wheelie)"))
        self.max_front_lift = max(self.max_front_lift, pf[1] - p.front_radius)

        v_den_f = max(abs(vf[0]), V_EPS)
        v_den_r = max(abs(vr[0]), V_EPS)
        kf = -1.0 if self.locked_f else max(-1.0, min(1.0, (self.wf * p.front_radius - vf[0]) / v_den_f))
        kr = -1.0 if self.locked_r else max(-1.0, min(1.0, (self.wr * p.rear_radius - vr[0]) / v_den_r))
        phi_f = tyre.coefficient(kf, max(nf, 50.0)) if nf > 0 else 0.0
        phi_r = tyre.coefficient(kr, max(nr, 50.0)) if nr > 0 else 0.0
        torque_f = self.abs_f.update(lever_f * p.front_brake_max, kf, self.peak_slip(max(nf, 50.0)), p.front_brake_max, dt)
        torque_r = self.abs_r.update(lever_r * p.rear_brake_max, kr, self.peak_slip(max(nr, 50.0)), p.rear_brake_max, dt)
        ff, fr = phi_f * nf, phi_r * nr
        drive = self.drive_torque = self._drive_torque(dt)
        if self.locked_f and torque_f < p.front_radius * abs(ff):
            self._set_lock("f", False)
        if self.locked_r and torque_r < p.rear_radius * abs(fr):
            self._set_lock("r", False)
        # Torque the brake passes to its carrier: the applied torque while the wheel turns, the holding torque
        # (just enough to stop the tyre spinning the wheel) while it is locked.
        tq_f = -p.front_radius * ff if self.locked_f else torque_f
        tq_r = -p.rear_radius * fr if self.locked_r else torque_r

        fs_f = self._suspension_force(sf, sfd, self.k_f, self.c_f, s.front_travel)
        fs_r = self._suspension_force(sr, srd, self.k_r, self.c_r, s.rear_travel)

        # Mass matrix and generalised forces: M·q'' = Q.
        jf = ((1.0, 0.0, jt_f[0], ej_f[0], 0.0), (0.0, 1.0, jt_f[1], ej_f[1], 0.0))
        jr = ((1.0, 0.0, jt_r[0], 0.0, ej_r[0]), (0.0, 1.0, jt_r[1], 0.0, ej_r[1]))
        m = [[0.0] * 5 for _ in range(5)]
        m[0][0] = m[1][1] = self.m_s
        m[2][2] = self.i_s
        for mass, j in ((self.m_uf, jf), (self.m_ur, jr)):
            for a in range(5):
                for b in range(5):
                    m[a][b] += mass * (j[0][a] * j[0][b] + j[1][a] * j[1][b])
        # Velocity-product accelerations of each axle: −rot(b)·θ'² + 2·rot'(e)·s'·θ'
        de_f, de_r = _drot(th, self.e_f), _drot(th, self.e_r)
        bias_f = (-wf_pos[0] * thd * thd + 2 * de_f[0] * sfd * thd, -wf_pos[1] * thd * thd + 2 * de_f[1] * sfd * thd)
        bias_r = (-wr_pos[0] * thd * thd + 2 * de_r[0] * srd * thd, -wr_pos[1] * thd * thd + 2 * de_r[1] * srd * thd)
        # Road load: rolling resistance at each axle, aerodynamic drag on the sprung mass.
        roll_f = self.crr * nf * (1.0 if vf[0] > 0 else -1.0 if vf[0] < 0 else 0.0)
        roll_r = self.crr * nr * (1.0 if vr[0] > 0 else -1.0 if vr[0] < 0 else 0.0)
        drag = 0.5 * self.air_density * self.cda * xd * abs(xd)
        force_f = (ff - roll_f - self.m_uf * bias_f[0], nf - self.m_uf * g - self.m_uf * bias_f[1])
        force_r = (fr - roll_r - self.m_ur * bias_r[0], nr - self.m_ur * g - self.m_ur * bias_r[1])
        q = [jf[0][a] * force_f[0] + jf[1][a] * force_f[1] + jr[0][a] * force_r[0] + jr[1][a] * force_r[1]
             for a in range(5)]
        q[0] -= drag
        q[1] -= self.m_s * g
        q[2] += tq_f + tq_r - drive  # the drive's reaction lifts the nose
        q[3] -= fs_f
        q[4] -= fs_r
        qdd = _solve(m, q)

        self.wf = self._spin(self.wf, "f", ff, nf, kf, torque_f, p.front_radius, p.front_wheel_inertia, v_den_f)
        self.wr = self._spin(self.wr, "r", fr, nr, kr, torque_r - drive, p.rear_radius, self._rear_inertia(), v_den_r)
        for i in range(5):
            self.qd[i] += qdd[i] * dt
            self.q[i] += self.qd[i] * dt

        x, z, th, sf, sr = self.q
        xd, zd, thd, sfd, srd = self.qd
        b_f, _ = self._axles()
        jt_f, ej_f = _drot(th, b_f), _rot(th, self.e_f)
        self.x = self.front_axle_world()[0]
        self.v = xd + jt_f[0] * thd + ej_f[0] * sfd
        self.theta, self.theta_dot = th, thd
        self.angle_f += self.wf * dt
        self.angle_r += self.wr * dt
        decel = -(ff + fr - roll_f - roll_r - drag) / p.mass
        self.nf, self.nr, self.kf, self.kr, self.a = nf, nr, kf, kr, -decel
        self._torques = (torque_f, torque_r)
        self.peak_decel = max(self.peak_decel, decel)
        self.max_theta = max(self.max_theta, th) if airborne else self.max_theta
        self.max_rear_lift = max(getattr(self, "max_rear_lift", 0.0), self.rear_lift)
        self.locked_time_f += dt if self.locked_f else 0.0
        self.locked_time_r += dt if self.locked_r else 0.0
        self._track_skid(self.skids_f, self.x, kf <= HEAVY_SLIP and nf > 0)
        self._track_skid(self.skids_r, self.rear_contact_x, kr <= HEAVY_SLIP and nr > 0)
        self._flag(sf > s.front_travel, "fork", "Fork bottoms out")
        self._flag(sr < 0.0, "rear-top", "Rear suspension fully extended")
        self.t += dt
        self._step_count += 1

        self._check_end(airborne, nf, decel)
        if self._step_count % self.record_every == 0 or self.stopped:
            self._record()

    def _drive_torque(self, dt: float) -> float:
        """Torque the powertrain applies to the rear wheel; none in a braking run."""
        return 0.0

    def _rear_inertia(self) -> float:
        """Spin inertia at the rear wheel, to which a coupled engine adds its own."""
        return self.p.rear_wheel_inertia

    def _check_end(self, rear_airborne: bool, nf: float, decel: float) -> None:
        if rear_airborne and self._past_point_of_no_return_suspended(nf):
            self.events.append((self.t, "Pitched over the front wheel (past the point of no return)"))
            self._finish("pitched over")
        elif self.v <= V_STOP:
            if decel > 0:
                self.extra_distance = self.v * self.v / (2 * decel)
            self.events.append((self.t, "Stopped"))
            self._finish("stopped")

    def _flag(self, condition: bool, key: str, text: str) -> None:
        if condition and key not in self._flags:
            self._flags.add(key)
            self.events.append((self.t, text))

    def _past_point_of_no_return_suspended(self, nf: float) -> bool:
        """The rigid model's energy test, applied to the whole machine about the front axle."""
        fx, fz = self.front_axle_world()
        rx, rz = self.rear_axle_world()
        m = self.p.mass
        gx = (self.m_s * self.q[0] + self.m_uf * fx + self.m_ur * rx) / m - fx
        gz = (self.m_s * self.q[1] + self.m_uf * fz + self.m_ur * rz) / m - fz
        d = math.hypot(gx, gz)
        if gx >= 0.0:
            return True
        thd = self.theta_dot
        if thd <= 0.0:
            return False
        inertia = (self.i_s + self.m_s * ((self.q[0] - fx) ** 2 + (self.q[1] - fz) ** 2)
                   + self.m_ur * ((rx - fx) ** 2 + (rz - fz) ** 2))
        return 0.5 * inertia * thd * thd >= m * self.p.g * (d - gz)

    def summary(self):
        summary = super().summary()
        summary.max_rear_lift_mm = 1000 * getattr(self, "max_rear_lift", 0.0)
        return summary
