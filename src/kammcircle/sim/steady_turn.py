"""Steady turning on tyres that slip and camber: the trim of a motorcycle on a circle at constant speed.

The motorcycle is two rigid frames, the rear frame (with its riders and load) and the steered front frame, and two
wheels whose tyres have a round cross-section of crown radius ρ: each contact point lies on the road directly below the
centre of the tyre's cross-section (Sharp, Evangelou & Limebeer 2004, §3). In axes that turn with the motorcycle at the
yaw rate Ω about a vertical line through the turn centre, every part is at rest, so the trim is a static balance of
the weight, centrifugal force and d'Alembert moment −Ω×H of every body (H includes each wheel's spin), the tyres'
forces and aligning moments from the Magic Formula (:class:`~kammcircle.sim.tyre.MotorcycleTyre`), air drag and the
driving force that holds the speed. The six balance equations (force and moment) fix the lean, the steer angle, the rear
tyre's sideslip, both tyre loads and the driving force for a given speed and radius (or speed and lean); the pitch angle
keeps both tyres on the road. The torque the rider holds on the handlebars is what the front frame and wheel then need
to balance about the steering axis.

A freely rolling wheel needs no torque about its axle, so its tyre's longitudinal force is set by that balance: a
cambered tyre's aligning moment has a component along the axle, which the tyre must react with a small drag force
(Sharp et al.'s Figure 20 shows it at the front). Rolling resistance is added as a force at each contact.

Axes follow SAE J670e as in :mod:`kammcircle.sim.lateral`: x forward, y to the right, z down, origin at the rear contact
point; lean, steer and torque are positive to the right. The solver works on right-hand turns; a left-hand turn is the
mirror image. A slow acceleration or deceleration along the path can be added (quasi-steady, as in Sharp et al.'s runs);
braking is shared between the wheels by a fixed front share.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .lateral import WhippleParameters
from .tyre import MotorcycleTyre

G = 9.81

Vec = tuple[float, float, float]
Mat = tuple[Vec, Vec, Vec]
DOWN: Vec = (0.0, 0.0, 1.0)
ZERO: Vec = (0.0, 0.0, 0.0)


# ─── small vector algebra (pure Python, like the rest of the physics) ───────


def _add(*vs: Vec) -> Vec:
    x = y = z = 0.0
    for v in vs:
        x += v[0]
        y += v[1]
        z += v[2]
    return (x, y, z)


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a: Vec, s: float) -> Vec:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a: Vec) -> Vec:
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def _mv(m: Mat, v: Vec) -> Vec:
    return (_dot(m[0], v), _dot(m[1], v), _dot(m[2], v))


def _transpose(m: Mat) -> Mat:
    return ((m[0][0], m[1][0], m[2][0]), (m[0][1], m[1][1], m[2][1]), (m[0][2], m[1][2], m[2][2]))


def _mm(a: Mat, b: Mat) -> Mat:
    bt = _transpose(b)
    return tuple(tuple(_dot(a[i], bt[j]) for j in range(3)) for i in range(3))  # type: ignore[return-value]


def rotation(axis: Vec, angle: float) -> Mat:
    """Rotation by ``angle`` about the unit vector ``axis`` (right-hand rule; Rodrigues' formula)."""
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    t = 1.0 - c
    return ((c + x * x * t, x * y * t - z * s, x * z * t + y * s),
            (y * x * t + z * s, c + y * y * t, y * z * t - x * s),
            (z * x * t - y * s, z * y * t + x * s, c + z * z * t))


def _inertia(xx: float, yy: float, zz: float, xz: float) -> Mat:
    return ((xx, 0.0, xz), (0.0, yy, 0.0), (xz, 0.0, zz))


# ─── the model ───────────────────────────────────────────────────────────────


class BeyondGrip(ValueError):
    """No steady turn exists: a tyre would need more force than it can give, or the balance has no solution."""


@dataclass(frozen=True)
class Body:
    mass: float
    position: Vec  # centre of mass in rear-frame axes (front frame: unsteered), m, z down
    inertia: Mat  # about the centre of mass, same axes, kg m²


@dataclass(frozen=True)
class Wheel:
    radius: float  # outer radius: hub height with the motorcycle upright, m
    crown: float  # crown radius of the tyre's cross-section, m
    mass: float
    spin_inertia: float
    diametral_inertia: float
    tyre: MotorcycleTyre


@dataclass(frozen=True)
class TrimModel:
    wheelbase: float
    trail: float
    rake: float  # steering-axis tilt from the vertical, rad
    rear_body: Body  # rear frame with riders and load
    front_body: Body  # steered front frame without its wheel
    rear: Wheel
    front: Wheel
    drag_area: float = 0.0  # Cd·A, m²; drag acts at the centre of mass
    air_density: float = 1.225
    rolling_resistance: float = 0.0  # share of each tyre's load
    front_brake_share: float = 0.7  # of a braking force, when slowing in the turn
    g: float = G

    @property
    def mass(self) -> float:
        return self.rear_body.mass + self.front_body.mass + self.rear.mass + self.front.mass

    def with_tyres(self, front: MotorcycleTyre, rear: MotorcycleTyre) -> TrimModel:
        return replace(self, front=replace(self.front, tyre=front), rear=replace(self.rear, tyre=rear))


def model_from_whipple(p: WhippleParameters, front_tyre: MotorcycleTyre, rear_tyre: MotorcycleTyre, *,
                       front_crown: float, rear_crown: float, rear_offset: float = 0.0, drag_area: float = 0.0,
                       air_density: float = 1.225, rolling_resistance: float = 0.0,
                       front_brake_share: float = 0.7) -> TrimModel:
    """The trim model of the motorcycle described by the benchmark's 25 parameters, with tyres of the given crown radii.
    ``rear_offset`` moves the rear frame's centre of mass sideways (positive to the right, the inside of a right turn),
    as a rider hanging off does."""
    return TrimModel(
        wheelbase=p.w, trail=p.c, rake=p.lam,
        rear_body=Body(p.m_b, (p.x_b, rear_offset, p.z_b), _inertia(p.i_bxx, p.i_byy, p.i_bzz, p.i_bxz)),
        front_body=Body(p.m_h, (p.x_h, 0.0, p.z_h), _inertia(p.i_hxx, p.i_hyy, p.i_hzz, p.i_hxz)),
        rear=Wheel(p.r_r, rear_crown, p.m_r, p.i_ryy, p.i_rxx, rear_tyre),
        front=Wheel(p.r_f, front_crown, p.m_f, p.i_fyy, p.i_fxx, front_tyre),
        drag_area=drag_area, air_density=air_density, rolling_resistance=rolling_resistance,
        front_brake_share=front_brake_share,
    )


# ─── geometry: where everything is for a given lean and steer ───────────────


@dataclass(frozen=True)
class Pose:
    lean: float
    steer: float
    pitch: float
    rear_rot: Mat  # rear-frame axes to yaw axes
    front_rot: Mat  # front-frame axes to yaw axes
    rear_hub: Vec
    front_hub: Vec
    rear_axle: Vec  # unit vectors along the wheel spindles (to the wheel's right)
    front_axle: Vec
    rear_contact: Vec
    front_contact: Vec
    axis_point: Vec  # the steering axis: a point on it and its direction, pointing down
    axis_dir: Vec
    rear_cog: Vec
    front_cog: Vec


def _contact(hub: Vec, axle: Vec, radius: float, crown: float) -> Vec:
    """The point of a round-section tyre that touches a flat road: below the crown circle's lowest point."""
    down_in_plane = _unit(_sub(DOWN, _mul(axle, _dot(DOWN, axle))))
    return _add(hub, _mul(down_in_plane, radius - crown), _mul(DOWN, crown))


def pose(m: TrimModel, lean: float, steer: float, pitch_guess: float = 0.0) -> Pose:
    """Positions and orientations for a lean and steer angle, with the pitch that puts both tyres on the road."""
    w, c, lam = m.wheelbase, m.trail, m.rake
    rear_hub_body: Vec = (0.0, 0.0, -m.rear.radius)
    axis_point_body: Vec = (w + c, 0.0, 0.0)
    axis_body: Vec = (math.sin(lam), 0.0, math.cos(lam))
    steer_rot = rotation(axis_body, steer)

    def steered(p: Vec) -> Vec:
        return _add(axis_point_body, _mv(steer_rot, _sub(p, axis_point_body)))

    front_hub_body = steered((w, 0.0, -m.front.radius))
    front_axle_body = _mv(steer_rot, (0.0, 1.0, 0.0))
    rr, rho_r = m.rear.radius, m.rear.crown
    rear_hub: Vec = (0.0, (rr - rho_r) * math.sin(lean), -rho_r - (rr - rho_r) * math.cos(lean))
    roll = rotation((1.0, 0.0, 0.0), lean)

    def front_contact_height(theta: float) -> tuple[float, Mat, Vec, Vec, Vec]:
        rot = _mm(roll, rotation((0.0, 1.0, 0.0), theta))
        hub = _add(rear_hub, _mv(rot, _sub(front_hub_body, rear_hub_body)))
        axle = _mv(rot, front_axle_body)
        contact = _contact(hub, axle, m.front.radius, m.front.crown)
        return contact[2], rot, hub, axle, contact

    theta = pitch_guess
    for _ in range(30):
        f, *_ = front_contact_height(theta)
        if abs(f) < 1e-13:
            break
        h = 1e-7
        slope = (front_contact_height(theta + h)[0] - front_contact_height(theta - h)[0]) / (2 * h)
        if slope == 0 or not math.isfinite(slope):
            raise BeyondGrip("no pitch angle puts both tyres on the road")
        theta -= f / slope
    else:
        raise BeyondGrip("no pitch angle puts both tyres on the road")
    _, rot, front_hub, front_axle, front_contact = front_contact_height(theta)

    def to_yaw(p: Vec) -> Vec:
        return _add(rear_hub, _mv(rot, _sub(p, rear_hub_body)))

    return Pose(
        lean=lean, steer=steer, pitch=theta, rear_rot=rot, front_rot=_mm(rot, steer_rot),
        rear_hub=rear_hub, front_hub=front_hub, rear_axle=_mv(rot, (0.0, 1.0, 0.0)), front_axle=front_axle,
        rear_contact=_contact(rear_hub, _mv(rot, (0.0, 1.0, 0.0)), rr, rho_r), front_contact=front_contact,
        axis_point=to_yaw(axis_point_body), axis_dir=_mv(rot, axis_body),
        rear_cog=to_yaw(m.rear_body.position), front_cog=to_yaw(steered(m.front_body.position)),
    )


# ─── the balance ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TyreState:
    load: float  # N, the road pushing up
    side_force: float  # N, + towards the turn centre (the tyre's own lateral axis, horizontal)
    longitudinal_force: float  # N, + driving
    aligning_moment: float  # N m about the vertical, + turning the wheel into the turn
    slip_angle: float  # rad, + when the tyre's path points outside its heading (side force inwards)
    camber: float  # rad, + leaning into the turn
    slip_ratio: float
    camber_share: float  # share of the side force due to camber (eq. 7's argument)
    peak_side_force: float  # N, Dy: the most this tyre gives sideways at this camber and load
    peak_longitudinal_force: float  # N, Dx at this load
    spin_rate: float  # rad/s

    @property
    def grip_used(self) -> float:
        """Share of the friction circle in use: √((Fx/Dx)² + (Fy/Dy)²). The published combined-slip functions were
        fitted at zero camber and let a cambered tyre exceed this circle, so the simulator treats 1 as the limit."""
        if self.peak_side_force <= 0 or self.peak_longitudinal_force <= 0:
            return math.inf
        return math.hypot(self.longitudinal_force / self.peak_longitudinal_force,
                          self.side_force / self.peak_side_force)


TORQUE_PARTS = ("tyre_load", "tyre_side", "tyre_moment", "tyre_longitudinal", "gyroscopic", "weight", "inertia")


@dataclass(frozen=True)
class Trim:
    speed: float  # m/s, of the rear contact point
    radius: float  # m, of the rear contact point's path
    yaw_rate: float
    acceleration: float  # m/s² along the path
    lean: float  # rad, rear frame
    steer: float  # rad, handlebars about the steering axis
    pitch: float  # rad
    ground_steer: float  # rad, angle between the wheels' headings on the road
    front: TyreState
    rear: TyreState
    drive_force: float  # N, + driving (the rear), − braking (shared)
    drag: float  # N
    steering_torque: float  # N m the rider holds on the bars, + turning them into the turn
    torque_parts: dict[str, float] = field(default_factory=dict)  # what each load does to the bars (sum = −torque)
    pose: Pose | None = None

    @property
    def lateral_g(self) -> float:
        return self.speed * self.yaw_rate / G


def _no_slip_spin(vel_contact: Vec, axle: Vec, hub: Vec, contact: Vec, heading: Vec) -> float:
    """Spin rate about the axle (relative to the turning axes) for which the tyre's material at the contact point does
    not slide lengthways."""
    return -_dot(vel_contact, heading) / _dot(_cross(axle, _sub(contact, hub)), heading)


class _Balance:
    """Evaluates the six balance equations for one set of unknowns; keeps the details of the last evaluation."""

    def __init__(self, m: TrimModel, speed: float, acceleration: float) -> None:
        self.m, self.v, self.ax = m, speed, acceleration
        self.pitch = 0.0

    def evaluate(self, lean: float, steer: float, yaw_rate: float, beta_r: float, n_f: float, n_r: float,
                 control: float, details: bool = False) -> tuple[list[float], dict]:
        m, v, ax = self.m, self.v, self.ax
        ps = pose(m, lean, steer, self.pitch)
        self.pitch = ps.pitch
        alpha_r = math.atan(beta_r)
        ground_vel: Vec = (v * math.cos(alpha_r), -v * math.sin(alpha_r), 0.0)
        rate = ax / v if v > 0 else 0.0
        omega: Vec = (0.0, 0.0, yaw_rate)

        def vel(p: Vec) -> Vec:
            return _add(ground_vel, _cross(omega, p))

        def inertial_force(mass: float, p: Vec) -> Vec:
            vp = vel(p)
            accel = _add(_cross(omega, vp), _mul(vp, rate))
            return _add(_mul(DOWN, mass * m.g), _mul(accel, -mass))

        def body_moment(inertia_body: Mat, rot: Mat) -> Vec:
            inertia = _mm(_mm(rot, inertia_body), _transpose(rot))
            h = _mv(inertia, omega)
            return _mul(_add(_cross(omega, h), _mul(h, rate)), -1.0)

        force_sum, moment_sum = ZERO, ZERO
        loads: dict[str, tuple[Vec, Vec, Vec]] = {}  # name: (point, force, couple)
        for name, body, rot, pos in (("rear_body", m.rear_body, ps.rear_rot, ps.rear_cog),
                                     ("front_body", m.front_body, ps.front_rot, ps.front_cog)):
            f = inertial_force(body.mass, pos)
            mo = body_moment(body.inertia, rot)
            loads[name] = (pos, f, mo)

        tyres: dict[str, TyreState] = {}
        if control >= 0:
            ctrl = {"front": 0.0, "rear": control}
        else:
            ctrl = {"front": m.front_brake_share * control, "rear": (1.0 - m.front_brake_share) * control}
        for name, wheel, hub, axle, contact, load in (
                ("rear", m.rear, ps.rear_hub, ps.rear_axle, ps.rear_contact, n_r),
                ("front", m.front, ps.front_hub, ps.front_axle, ps.front_contact, n_f)):
            heading = _unit(_cross(axle, DOWN))
            lateral = _cross(DOWN, heading)
            vc = vel(contact)
            v_long = _dot(vc, heading)
            beta = beta_r if name == "rear" else -_dot(vc, lateral) / abs(v_long)
            camber = math.asin(max(-1.0, min(1.0, _dot(axle, DOWN))))
            spin = _no_slip_spin(vc, axle, hub, contact, heading) if v > 0 else 0.0
            w_vec = _add(omega, _mul(axle, spin))
            h_wheel = _add(_mul(w_vec, wheel.diametral_inertia),
                           _mul(axle, (wheel.spin_inertia - wheel.diametral_inertia) * _dot(w_vec, axle)))
            wheel_moment = _mul(_add(_cross(omega, h_wheel), _mul(h_wheel, rate)), -1.0)
            arm = _sub(contact, hub)
            lever = _dot(_cross(arm, heading), axle)  # the rolling radius: axle moment per newton of Fx
            tyre = wheel.tyre
            fx, fy, mz = tyre.forces(0.0, beta, camber, load)
            kappa = 0.0
            for _ in range(3):  # the free-rolling drag depends on Mz, which depends weakly on the slip it needs
                free = -_dot(_add(_cross(arm, _add(_mul(lateral, fy), _mul(DOWN, -load))), _mul(DOWN, mz),
                                  wheel_moment), axle) / lever
                fx_needed = free - m.rolling_resistance * load + ctrl[name]
                k = tyre.slip_for_longitudinal_force(fx_needed, beta, load)
                if k is None:
                    raise BeyondGrip(f"the {name} tyre cannot give the {abs(fx_needed):.0f} N it needs lengthways")
                kappa = k
                fx, fy, mz = tyre.forces(kappa, beta, camber, load)
            force = _add(_mul(heading, fx), _mul(lateral, fy), _mul(DOWN, -load))
            loads[name + "_wheel"] = (hub, inertial_force(wheel.mass, hub), wheel_moment)
            loads[name + "_tyre"] = (contact, force, _mul(DOWN, mz))
            if details:
                tyres[name] = TyreState(
                    load=load, side_force=fy, longitudinal_force=fx, aligning_moment=mz, slip_angle=math.atan(beta),
                    camber=camber, slip_ratio=kappa, camber_share=tyre.camber_share(beta, camber, load),
                    peak_side_force=tyre.peak_side_force(camber, load),
                    peak_longitudinal_force=tyre.longitudinal.peak_force(load), spin_rate=spin)
                loads[name + "_gyro"] = (hub, ZERO, _mul(_cross(omega, _mul(axle, wheel.spin_inertia * spin)), -1.0))

        masses = [(m.rear_body.mass, ps.rear_cog), (m.front_body.mass, ps.front_cog), (m.rear.mass, ps.rear_hub),
                  (m.front.mass, ps.front_hub)]
        total = sum(mass for mass, _ in masses)
        cog = _mul(_add(*[_mul(p, mass) for mass, p in masses]), 1.0 / total)
        vcog = vel(cog)
        speed_cog = math.sqrt(_dot(vcog, vcog))
        drag = 0.5 * m.air_density * m.drag_area * speed_cog * speed_cog
        drag_force = _mul(_unit(vcog), -drag) if speed_cog > 0 else ZERO
        loads["drag"] = (cog, drag_force, ZERO)

        for name in ("rear_body", "front_body", "rear_wheel", "front_wheel", "rear_tyre", "front_tyre", "drag"):
            point, f, couple = loads[name]
            force_sum = _add(force_sum, f)
            moment_sum = _add(moment_sum, _cross(point, f), couple)
        scale_f = total * m.g
        scale_m = scale_f * m.wheelbase
        residual = [force_sum[0] / scale_f, force_sum[1] / scale_f, force_sum[2] / scale_f,
                    moment_sum[0] / scale_m, moment_sum[1] / scale_m, moment_sum[2] / scale_m]
        info = {"pose": ps, "loads": loads, "tyres": tyres, "drag": drag, "cog": cog} if details else {}
        return residual, info


def _solve_linear(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-300:
            raise BeyondGrip("the balance equations are singular here")
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            factor = m[r][col] / m[col][col]
            if factor:
                for k in range(col, n + 1):
                    m[r][k] -= factor * m[col][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][k] * x[k] for k in range(r + 1, n))) / m[r][r]
    return x


def _newton(fun, u0: list[float], steps: list[float], tol: float = 1e-11, max_iter: int = 60) -> list[float]:
    u = list(u0)
    r = fun(u)
    norm = max(abs(x) for x in r)
    for _ in range(max_iter):
        if norm < tol:
            return u
        jac = [[0.0] * len(u) for _ in r]
        for j, h in enumerate(steps):
            up = list(u)
            up[j] += h
            rp = fun(up)
            for i in range(len(r)):
                jac[i][j] = (rp[i] - r[i]) / h
        du = _solve_linear(jac, [-x for x in r])
        t = 1.0
        while True:
            trial = [u[i] + t * du[i] for i in range(len(u))]
            try:
                rt = fun(trial)
                nt = max(abs(x) for x in rt)
            except (BeyondGrip, ValueError, ZeroDivisionError, OverflowError):
                nt = math.inf
            if nt < norm or t < 1e-6:
                break
            t *= 0.5
        if not math.isfinite(nt) or nt >= norm:
            raise BeyondGrip("no steady turn: the balance does not converge")
        u, r, norm = trial, rt, nt
    if norm < 1e-8:
        return u
    raise BeyondGrip("no steady turn: the balance does not converge")


def ground_steer(ps: Pose) -> float:
    """Angle between the front and rear wheels' headings on the road, rad, + to the right."""
    front = _cross(ps.front_axle, DOWN)
    rear = _cross(ps.rear_axle, DOWN)
    return math.atan2(front[1], front[0]) - math.atan2(rear[1], rear[0])


def kinematic_steer(m: TrimModel, lean: float, target: float) -> float:
    """The handlebar angle that turns the front wheel's heading on the road by ``target`` at this lean."""
    steer = target / math.cos(m.rake)
    for _ in range(40):
        f = ground_steer(pose(m, lean, steer)) - target
        if abs(f) < 1e-13:
            break
        h = 1e-7
        slope = (ground_steer(pose(m, lean, steer + h)) - ground_steer(pose(m, lean, steer - h))) / (2 * h)
        steer -= f / slope
    return steer


def _initial(m: TrimModel, speed: float, lateral: float) -> tuple[float, float, float, float]:
    """Lean, steer and loads from the point-mass picture, as a start for Newton's method."""
    lean = math.atan(lateral / m.g)
    rho = 0.5 * (m.rear.crown + m.front.crown)
    h = -m.rear_body.position[2]
    if h > rho:
        lean += math.asin(min(1.0, rho * math.sin(lean) / (h - rho)))
    x_cog = (m.rear_body.mass * m.rear_body.position[0] + m.front_body.mass * m.front_body.position[0]
             + m.front.mass * m.wheelbase) / m.mass
    n_f = m.mass * m.g * x_cog / m.wheelbase
    return lean, n_f, m.mass * m.g - n_f, x_cog


def solve(m: TrimModel, speed: float, *, radius: float | None = None, lean: float | None = None,
          acceleration: float = 0.0, guess: Trim | None = None) -> Trim:
    """The steady right-hand turn at ``speed`` (m/s, rear contact) on a circle of ``radius`` (m, rear contact path),
    or at a given ``lean`` (rad) of the rear frame. Raises :class:`BeyondGrip` when no such turn exists.

    ``guess``, a nearby solution, speeds the search up. Without one, a hard case (low speed, large steer) that does
    not converge from the point-mass estimate is reached by continuation from an easier turn: a faster one at the same
    lean, or a wider one at the same speed."""
    if (radius is None) == (lean is None):
        raise ValueError("give either the radius or the lean")
    if speed <= 0:
        raise ValueError("the speed must be positive")
    try:
        return _solve(m, speed, radius, lean, acceleration, guess)
    except BeyondGrip:
        if guess is not None:
            raise
    # continuation: start from an easier turn and walk back to the one asked for
    steps = 10
    if lean is not None:
        start = max(2.0 * speed, 15.0)
        path = [start * (speed / start) ** (i / steps) for i in range(steps + 1)]
        last = _solve(m, path[0], None, lean, acceleration, None)
        for v in path[1:]:
            last = _solve(m, v, None, lean, acceleration, last)
        return last
    start = 8.0 * radius  # type: ignore[operator]
    path = [start * (radius / start) ** (i / steps) for i in range(steps + 1)]  # type: ignore[operator]
    last = _solve(m, speed, path[0], None, acceleration, None)
    for r in path[1:]:
        last = _solve(m, speed, r, None, acceleration, last)
    return last


def _solve(m: TrimModel, speed: float, radius: float | None, lean: float | None, acceleration: float,
           guess: Trim | None) -> Trim:
    bal = _Balance(m, speed, acceleration)
    weight = m.mass * m.g
    w = m.wheelbase
    if guess is not None:
        bal.pitch = guess.pitch
        start_lean, start_steer, beta0 = guess.lean, guess.steer, math.tan(guess.rear.slip_angle)
        n_f0, n_r0, ctrl0 = guess.front.load, guess.rear.load, guess.drive_force
        start_rate = guess.yaw_rate
    else:
        lateral = speed * speed / radius if radius is not None else m.g * math.tan(lean)  # type: ignore[arg-type]
        start_lean, n_f0, n_r0, _ = _initial(m, speed, lateral)
        if lean is not None:
            start_lean = lean
        start_rate = speed / radius if radius is not None else lateral / speed
        start_steer = kinematic_steer(m, start_lean, math.atan(w * start_rate / speed))
        beta0 = 0.0
        ctrl0 = 0.5 * m.air_density * m.drag_area * speed * speed + m.rolling_resistance * weight + m.mass * acceleration

    if radius is not None:
        rate = speed / radius

        def fun(u: list[float]) -> list[float]:
            return bal.evaluate(u[0], u[1], rate, u[2], u[3] * weight, u[4] * weight, u[5] * weight)[0]

        u0 = [start_lean, start_steer, beta0, n_f0 / weight, n_r0 / weight, ctrl0 / weight]
        u = _newton(fun, u0, [1e-7, 1e-8, 1e-8, 1e-7, 1e-7, 1e-7])
        lean_s, steer_s, beta_s, nf, nr, ctrl = u[0], u[1], u[2], u[3] * weight, u[4] * weight, u[5] * weight
    else:
        lean_s = lean  # type: ignore[assignment]

        def fun(u: list[float]) -> list[float]:
            return bal.evaluate(lean_s, u[1], u[0] * speed / w, u[2], u[3] * weight, u[4] * weight, u[5] * weight)[0]

        u0 = [start_rate * w / speed, start_steer, beta0, n_f0 / weight, n_r0 / weight, ctrl0 / weight]
        u = _newton(fun, u0, [1e-8, 1e-8, 1e-8, 1e-7, 1e-7, 1e-7])
        rate = u[0] * speed / w
        steer_s, beta_s, nf, nr, ctrl = u[1], u[2], u[3] * weight, u[4] * weight, u[5] * weight
        radius = speed / rate if rate > 0 else math.inf

    _, info = bal.evaluate(lean_s, steer_s, rate, beta_s, nf, nr, ctrl, details=True)
    ps: Pose = info["pose"]
    tyres: dict[str, TyreState] = info["tyres"]
    for name, state in tyres.items():
        if state.load <= 0:
            raise BeyondGrip(f"the {name} tyre would leave the road")
        tyre = (m.front if name == "front" else m.rear).tyre
        beta = math.tan(state.slip_angle)
        h = 1e-6
        rising = (tyre.side_force(beta + h, state.camber, state.load)
                  - tyre.side_force(beta - h, state.camber, state.load)) > 0
        if not rising:
            raise BeyondGrip(f"the {name} tyre is past its peak side force: it slides")
        if state.grip_used >= 1.0:
            raise BeyondGrip(f"the {name} tyre would need more than its grip ({state.grip_used:.0%} of its friction "
                             "circle): it slides")

    # the handlebars: every load on the front frame and wheel, about the steering axis
    loads = info["loads"]
    axis_p, axis_d = ps.axis_point, ps.axis_dir

    def about_axis(point: Vec, force: Vec, couple: Vec = ZERO) -> float:
        return _dot(_add(_cross(_sub(point, axis_p), force), couple), axis_d)

    contact, tyre_force, tyre_couple = loads["front_tyre"]
    front = tyres["front"]
    heading = _unit(_cross(ps.front_axle, DOWN))
    lateral = _cross(DOWN, heading)
    hub, wheel_force, wheel_couple = loads["front_wheel"]
    fb_point, fb_force, fb_couple = loads["front_body"]
    gyro = loads["front_gyro"][2]
    weight_parts = (about_axis(fb_point, _mul(DOWN, m.front_body.mass * m.g))
                    + about_axis(hub, _mul(DOWN, m.front.mass * m.g)))
    total_front = (about_axis(contact, tyre_force, tyre_couple) + about_axis(hub, wheel_force, wheel_couple)
                   + about_axis(fb_point, fb_force, fb_couple))
    parts = {
        "tyre_load": about_axis(contact, _mul(DOWN, -front.load)),
        "tyre_side": about_axis(contact, _mul(lateral, front.side_force)),
        "tyre_moment": about_axis(contact, ZERO, tyre_couple),
        "tyre_longitudinal": about_axis(contact, _mul(heading, front.longitudinal_force)),
        "gyroscopic": _dot(gyro, axis_d),
        "weight": weight_parts,
    }
    parts["inertia"] = total_front - sum(parts.values())
    return Trim(speed=speed, radius=radius, yaw_rate=rate, acceleration=acceleration, lean=lean_s, steer=steer_s,
                pitch=ps.pitch, ground_steer=ground_steer(ps), front=tyres["front"], rear=tyres["rear"],
                drive_force=ctrl, drag=info["drag"], steering_torque=-total_front, torque_parts=parts, pose=ps)


def peak_friction(m: TrimModel) -> float:
    """The lower of the two tyres' peak side-force coefficients at their nominal loads."""
    return min(m.front.tyre.mu_scale * m.front.tyre.pdy1, m.rear.tyre.mu_scale * m.rear.tyre.pdy1)


def grip_limit_speed(m: TrimModel, radius: float, *, acceleration: float = 0.0, tol: float = 0.05) -> float:
    """The highest speed at which a steady turn of this radius still exists, m/s, found by bisection from the
    point-mass estimate √(√(μ² − a²)·g·r)."""
    mu = peak_friction(m)
    along = abs(acceleration) / m.g
    if along >= mu:
        return 0.0
    estimate = math.sqrt(math.sqrt(mu * mu - along * along) * m.g * radius)

    def feasible(v: float, guess: Trim | None) -> Trim | None:
        try:
            if guess is None:
                return solve(m, v, radius=radius, acceleration=acceleration)
            return _solve(m, v, radius, None, acceleration, guess)  # near a known turn: no continuation needed
        except BeyondGrip:
            return None

    lo = 0.85 * estimate
    best = feasible(lo, None)
    while best is None:
        lo *= 0.8
        if lo < 0.5:
            return 0.0
        best = feasible(lo, None)
    hi = 1.08 * estimate
    while True:
        trial = feasible(hi, best)
        if trial is None:
            break
        lo, best, hi = hi, trial, hi * 1.08
        if hi > 200:
            return lo
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        trial = feasible(mid, best)
        if trial is None:
            hi = mid
        else:
            lo, best = mid, trial
    return lo


def sweep_speed(m: TrimModel, lean: float, speeds: list[float], *, acceleration: float = 0.0) -> list[Trim | None]:
    """Steady turns at one lean over a range of speeds (tighter or wider circles), solved by continuation; None where
    no turn exists."""
    out: list[Trim | None] = []
    last: Trim | None = None
    for v in speeds:
        try:
            last = _solve(m, v, None, lean, acceleration, last)
        except BeyondGrip:
            try:
                last = _solve(m, v, None, lean, acceleration, None) if last is not None else None
            except BeyondGrip:
                last = None
        out.append(last)
    return out


def sweep_lateral(m: TrimModel, speed: float, lateral_gs: list[float], *, acceleration: float = 0.0
                  ) -> list[Trim | None]:
    """Steady turns at one speed over a range of lateral accelerations (in g, at the rear contact), by continuation."""
    out: list[Trim | None] = []
    last: Trim | None = None
    for a in lateral_gs:
        radius = speed * speed / (a * m.g)
        try:
            last = _solve(m, speed, radius, None, acceleration, last)
        except BeyondGrip:
            last = None
        out.append(last)
    return out
