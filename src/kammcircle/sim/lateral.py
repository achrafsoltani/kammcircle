"""Lean and steer: the linearised Whipple model in the benchmark form of Meijaard, Papadopoulos, Ruina and Schwab
(2007), "Linearized dynamics equations for the balance and steer of a bicycle: a benchmark and review",
Proc. R. Soc. A 463, 1955–1982.

    M·q'' + v·C1·q' + (g·K0 + v²·K2)·q = f,      q = (φ, δ),   f = (Tφ, Tδ)            (eq. 5.3)

φ is the lean of the rear frame and δ the steer angle, both positive to the right; Tφ is a lean torque on the rear
frame and Tδ the torque the rider applies to the handlebars, positive urging them to the right. Axes follow SAE J670e:
x forward, y to the rider's right, z down, origin at the rear contact point, so heights are negative z. Every
coefficient comes from the paper's 25 design parameters (Table 1) through the expressions of its Appendix A, and the
tests reproduce its benchmark matrices and eigenvalues (Table 2).

The model has rigid frames and knife-edge wheels that roll without slipping: no tyre slip or width, no frame or fork
compliance, and the rider is rigid with the rear frame. It is linear, so it is exact for small lean and steer angles.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

G = 9.81

Matrix = tuple[tuple[float, float], tuple[float, float]]
Poly = list[float]  # coefficients in ascending powers of s


@dataclass(frozen=True)
class WhippleParameters:
    """The 25 design parameters of Meijaard et al. (2007), Table 1, in SI units and their axes (z down)."""

    w: float  # wheelbase
    c: float  # trail
    lam: float  # steer axis tilt from the vertical, rad (90° minus the head angle; the rake)
    r_r: float  # rear wheel: radius, mass, diametral and polar inertias
    m_r: float
    i_rxx: float
    i_ryy: float
    x_b: float  # rear body and frame assembly, rider included: centre of mass, mass, inertia about it
    z_b: float
    m_b: float
    i_bxx: float
    i_bxz: float
    i_byy: float
    i_bzz: float
    x_h: float  # front handlebar and fork assembly, without the wheel
    z_h: float
    m_h: float
    i_hxx: float
    i_hxz: float
    i_hyy: float
    i_hzz: float
    r_f: float  # front wheel
    m_f: float
    i_fxx: float
    i_fyy: float


# The benchmark bicycle of Table 1, used by the tests to check every coefficient against the published values.
BENCHMARK = WhippleParameters(
    w=1.02, c=0.08, lam=math.pi / 10,
    r_r=0.3, m_r=2.0, i_rxx=0.0603, i_ryy=0.12,
    x_b=0.3, z_b=-0.9, m_b=85.0, i_bxx=9.2, i_bxz=2.4, i_byy=11.0, i_bzz=2.8,
    x_h=0.9, z_h=-0.7, m_h=4.0, i_hxx=0.05892, i_hxz=-0.00756, i_hyy=0.06, i_hzz=0.00708,
    r_f=0.35, m_f=3.0, i_fxx=0.1405, i_fyy=0.28,
)


@dataclass(frozen=True)
class Coefficients:
    M: Matrix
    C1: Matrix
    K0: Matrix
    K2: Matrix
    m_t: float  # total mass
    x_t: float  # its centre of mass, ahead of the rear contact
    z_t: float  # and below the road (negative: above)
    s_r: float  # gyrostatic coefficients: wheel spin angular momentum per unit speed
    s_f: float
    s_a: float  # the static moment term of eq. (A 19)
    mu: float  # trail ratio c·cos λ / w

    def stiffness(self, v: float, g: float = G) -> Matrix:
        return tuple(tuple(g * self.K0[i][j] + v * v * self.K2[i][j] for j in range(2)) for i in range(2))  # type: ignore[return-value]

    def damping(self, v: float) -> Matrix:
        return tuple(tuple(v * self.C1[i][j] for j in range(2)) for i in range(2))  # type: ignore[return-value]

    def entry(self, i: int, j: int, v: float, g: float = G) -> Poly:
        """The (i, j) entry of M·s² + v·C1·s + K as a polynomial in s."""
        return [g * self.K0[i][j] + v * v * self.K2[i][j], v * self.C1[i][j], self.M[i][j]]


def coefficients(p: WhippleParameters) -> Coefficients:
    """Appendix A, equations (A 1)–(A 27)."""
    sl, cl = math.sin(p.lam), math.cos(p.lam)
    m_t = p.m_r + p.m_b + p.m_h + p.m_f  # (A 1)
    x_t = (p.x_b * p.m_b + p.x_h * p.m_h + p.w * p.m_f) / m_t  # (A 2)
    z_t = (-p.r_r * p.m_r + p.z_b * p.m_b + p.z_h * p.m_h - p.r_f * p.m_f) / m_t  # (A 3)
    i_txx = (p.i_rxx + p.i_bxx + p.i_hxx + p.i_fxx + p.m_r * p.r_r ** 2 + p.m_b * p.z_b ** 2 + p.m_h * p.z_h ** 2
             + p.m_f * p.r_f ** 2)  # (A 4)
    i_txz = p.i_bxz + p.i_hxz - p.m_b * p.x_b * p.z_b - p.m_h * p.x_h * p.z_h + p.m_f * p.w * p.r_f  # (A 5)
    i_rzz, i_fzz = p.i_rxx, p.i_fxx  # (A 6)
    i_tzz = i_rzz + p.i_bzz + p.i_hzz + i_fzz + p.m_b * p.x_b ** 2 + p.m_h * p.x_h ** 2 + p.m_f * p.w ** 2  # (A 7)
    m_a = p.m_h + p.m_f  # (A 8)
    x_a = (p.x_h * p.m_h + p.w * p.m_f) / m_a  # (A 9)
    z_a = (p.z_h * p.m_h - p.r_f * p.m_f) / m_a
    i_axx = p.i_hxx + p.i_fxx + p.m_h * (p.z_h - z_a) ** 2 + p.m_f * (p.r_f + z_a) ** 2  # (A 10)
    i_axz = p.i_hxz - p.m_h * (p.x_h - x_a) * (p.z_h - z_a) + p.m_f * (p.w - x_a) * (p.r_f + z_a)  # (A 11)
    i_azz = p.i_hzz + i_fzz + p.m_h * (p.x_h - x_a) ** 2 + p.m_f * (p.w - x_a) ** 2  # (A 12)
    u_a = (x_a - p.w - p.c) * cl - z_a * sl  # (A 13)
    i_all = m_a * u_a ** 2 + i_axx * sl ** 2 + 2 * i_axz * sl * cl + i_azz * cl ** 2  # (A 14)
    i_alx = -m_a * u_a * z_a + i_axx * sl + i_axz * cl  # (A 15)
    i_alz = m_a * u_a * x_a + i_axz * sl + i_azz * cl  # (A 16)
    mu = p.c / p.w * cl  # (A 17)
    s_r, s_f = p.i_ryy / p.r_r, p.i_fyy / p.r_f  # (A 18)
    s_t = s_r + s_f
    s_a = m_a * u_a + mu * m_t * x_t  # (A 19)
    m_pd = i_alx + mu * i_txz
    M = ((i_txx, m_pd), (m_pd, i_all + 2 * mu * i_alz + mu ** 2 * i_tzz))  # (A 20)
    K0 = ((m_t * z_t, -s_a), (-s_a, -s_a * sl))  # (A 22)
    K2 = ((0.0, (s_t - m_t * z_t) / p.w * cl), (0.0, (s_a + s_f * sl) / p.w * cl))  # (A 24)
    C1 = ((0.0, mu * s_t + s_f * cl + i_txz / p.w * cl - mu * m_t * z_t),
          (-(mu * s_t + s_f * cl), i_alz / p.w * cl + mu * (s_a + i_tzz / p.w * cl)))  # (A 26)
    return Coefficients(M, C1, K0, K2, m_t, x_t, z_t, s_r, s_f, s_a, mu)


# ─── polynomials ─────────────────────────────────────────────────────────────


def poly_mul(a: Poly, b: Poly) -> Poly:
    out = [0.0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] += x * y
    return out


def poly_add(a: Poly, b: Poly, scale: float = 1.0) -> Poly:
    out = [0.0] * max(len(a), len(b))
    for i, x in enumerate(a):
        out[i] += x
    for i, y in enumerate(b):
        out[i] += scale * y
    return out


def poly_eval(a: Poly, s: complex) -> complex:
    out: complex = 0.0
    for x in reversed(a):
        out = out * s + x
    return out


def poly_derivative(a: Poly) -> Poly:
    return [i * a[i] for i in range(1, len(a))] or [0.0]


def poly_roots(a: Poly) -> list[complex]:
    """All roots, by the Durand–Kerner iteration and a Newton polish on the original polynomial."""
    c = list(a)
    while len(c) > 1 and c[-1] == 0:
        c.pop()
    n = len(c) - 1
    if n < 1:
        return []
    monic = [x / c[-1] for x in c]
    radius = 1 + max(abs(x) for x in monic[:-1])
    z = [0.5 * radius * cmath.exp(1j * (2 * math.pi * k / n + 0.4)) for k in range(n)]
    for _ in range(2000):
        moved = 0.0
        for i in range(n):
            den: complex = 1.0
            for j in range(n):
                if j != i:
                    den *= z[i] - z[j]
            if den == 0:
                den = 1e-12
            step = poly_eval(monic, z[i]) / den
            z[i] -= step
            moved = max(moved, abs(step))
        if moved <= 1e-15 * radius:
            break
    deriv = poly_derivative(monic)
    for i in range(n):
        for _ in range(3):
            d = poly_eval(deriv, z[i])
            if d == 0:
                break
            step = poly_eval(monic, z[i]) / d
            if not math.isfinite(abs(step)) or abs(step) > 1e-6 * max(1.0, abs(z[i])):
                break
            z[i] -= step
    out = []
    for r in z:
        if abs(r.imag) <= 1e-9 * max(1.0, abs(r)):
            r = complex(r.real, 0.0)
        out.append(r)
    return sorted(out, key=lambda r: (r.real, r.imag))


def characteristic_polynomial(k: Coefficients, v: float, g: float = G) -> Poly:
    """det(M·s² + v·C1·s + g·K0 + v²·K2), eq. (6.5): quartic in s."""
    return poly_add(poly_mul(k.entry(0, 0, v, g), k.entry(1, 1, v, g)),
                    poly_mul(k.entry(0, 1, v, g), k.entry(1, 0, v, g)), -1.0)


def eigenvalues(k: Coefficients, v: float, g: float = G) -> list[complex]:
    return poly_roots(characteristic_polynomial(k, v, g))


# ─── the modes and the self-stable speed range ──────────────────────────────


@dataclass(frozen=True)
class Modes:
    v: float
    weave: complex | None  # the oscillatory root with positive imaginary part, if there is one
    capsize: float | None  # the real root nearest zero, when a weave pair exists
    castering: float | None  # the most negative real root, when a weave pair exists
    roots: tuple[complex, ...]

    @property
    def stable(self) -> bool:
        return all(r.real < 0 for r in self.roots)

    @property
    def weave_frequency_hz(self) -> float | None:
        return None if self.weave is None else self.weave.imag / (2 * math.pi)

    @property
    def weave_damping(self) -> float | None:
        return None if self.weave is None else -self.weave.real / abs(self.weave)


def modes(k: Coefficients, v: float, g: float = G) -> Modes:
    roots = eigenvalues(k, v, g)
    complex_roots = [r for r in roots if r.imag > 0]
    real_roots = sorted(r.real for r in roots if r.imag == 0)
    if complex_roots and len(real_roots) == 2:
        return Modes(v, complex_roots[0], max(real_roots), min(real_roots), tuple(roots))
    return Modes(v, None, None, None, tuple(roots))


def capsize_speed(k: Coefficients, g: float = G) -> float | None:
    """The speed at which det(g·K0 + v²·K2) = 0, where the capsize root crosses zero (a pitchfork bifurcation)."""
    K0, K2 = k.K0, k.K2
    num = g * (K0[0][1] * K0[1][0] - K0[0][0] * K0[1][1])
    den = K0[0][0] * K2[1][1] + K2[0][0] * K0[1][1] - K2[0][1] * K0[1][0] - K0[0][1] * K2[1][0]
    # with K2[0][0] = K2[1][0] = 0 the v⁴ term vanishes and det is linear in v²
    if den == 0 or num / den <= 0:
        return None
    return math.sqrt(num / den)


def _hurwitz(k: Coefficients, v: float, g: float) -> float:
    a0, a1, a2, a3, a4 = characteristic_polynomial(k, v, g)
    return a3 * a2 * a1 - a3 * a3 * a0 - a4 * a1 * a1


def weave_speed(k: Coefficients, g: float = G, v_max: float = 80.0, step: float = 0.05) -> float | None:
    """The lowest speed at which the weave pair crosses into the left half-plane (a Hopf bifurcation): bracketed on
    the weave root's real part, then refined on the Hurwitz determinant, which vanishes at the crossing."""
    previous: Modes | None = None
    v = step
    while v <= v_max:
        m = modes(k, v, g)
        if previous is not None and previous.weave is not None and m.weave is not None:
            if previous.weave.real > 0 >= m.weave.real:
                lo, hi = previous.v, v
                f_lo = _hurwitz(k, lo, g)
                for _ in range(200):
                    mid = 0.5 * (lo + hi)
                    f_mid = _hurwitz(k, mid, g)
                    if (f_mid > 0) == (f_lo > 0):
                        lo, f_lo = mid, f_mid
                    else:
                        hi = mid
                    if hi - lo < 1e-14:
                        break
                return 0.5 * (lo + hi)
        previous = m
        v += step
    return None


def self_stable_range(k: Coefficients, g: float = G, v_max: float = 80.0) -> tuple[float, float] | None:
    """(from, to) in m/s where every root has a negative real part, or None. The upper end is the capsize speed
    when the capsize root is the one that leaves; the range is open-ended (to = inf) if nothing leaves before v_max."""
    lo = weave_speed(k, g, v_max)
    if lo is None:
        return None
    hi = capsize_speed(k, g)
    if hi is not None and hi <= lo:
        return None
    probe = modes(k, lo + 0.01 if hi is None else 0.5 * (lo + hi), g)
    if not probe.stable:
        return None
    return lo, hi if hi is not None else math.inf


# ─── steady turning ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SteadyTurn:
    lean: float  # rad, positive to the right
    steer: float  # rad
    torque: float  # N m on the handlebars, positive urging them to the right
    radius: float  # m, of the rear contact's path


def steady_turn(k: Coefficients, p: WhippleParameters, v: float, radius: float, direction: int = 1,
                g: float = G) -> SteadyTurn:
    """The linear model's steady turn on a circle of the given radius (right-hand for direction +1): heading rate
    v·δ·cos λ / w (eq. B 6) fixes the steer angle, the lean equation with no lean torque fixes the lean, and the steer
    equation gives the torque the rider must hold."""
    K = k.stiffness(v, g)
    steer = direction * p.w / (radius * math.cos(p.lam))
    lean = -K[0][1] * steer / K[0][0]
    torque = K[1][0] * lean + K[1][1] * steer
    return SteadyTurn(lean, steer, torque, radius)
