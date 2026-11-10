"""Longitudinal tyre force from the Magic Formula, with the motorcycle-tyre fit of Sharp, Evangelou and Limebeer.

Pure longitudinal slip (Sharp, Evangelou & Limebeer 2004, eqs. 1–6 and Table I, fitted to Pacejka's data for a
160/70 ZR17 tyre):

    dfz = (Fz − Fz0) / Fz0
    Fx  = Dx · sin( Cx · atan( Bx·κ − Ex·(Bx·κ − atan(Bx·κ)) ) )
    Dx  = λμ · (pDx1 + pDx2·dfz) · Fz
    Ex  = (pEx1 + pEx2·dfz + pEx3·dfz²) · (1 − pEx4·sgn κ)
    Kxκ = Fz · (pKx1 + pKx2·dfz) · exp(pKx3·dfz)
    Bx  = Kxκ / (Cx·Dx)

κ is the slip ratio (ωR − v) / |v|: 0 when rolling freely, −1 when the wheel is locked. λμ scales the peak friction to
a surface, in the way Pacejka's friction scaling factor does, and leaves the slip stiffness unchanged.

:class:`MotorcycleTyre` adds the same paper's side force in sideslip and camber (eqs. 7–13, Table II), aligning moment
(eqs. 14–22, Table III) and combined slip (eqs. 23–31, §4.4) for its 120/70 front and 180/55 rear tyres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class LongitudinalTyre:
    fz0: float = 1600.0
    cx: float = 1.6064
    pdx1: float = 1.2017
    pdx2: float = -0.0922
    pex1: float = 0.0263
    pex2: float = 0.27056
    pex3: float = -0.0769
    pex4: float = 1.1268
    pkx1: float = 25.94
    pkx2: float = -4.233
    pkx3: float = 0.3369
    mu_scale: float = 1.0

    @classmethod
    def from_data(cls, raw: dict[str, Any]) -> LongitudinalTyre:
        keys = {"Fz0_N": "fz0", "Cx": "cx", "pDx1": "pdx1", "pDx2": "pdx2", "pEx1": "pex1", "pEx2": "pex2",
                "pEx3": "pex3", "pEx4": "pex4", "pKx1": "pkx1", "pKx2": "pkx2", "pKx3": "pkx3"}
        return cls(**{field: float(raw[key]) for key, field in keys.items()})

    def for_surface(self, mu_peak: float) -> LongitudinalTyre:
        """The same tyre on a surface whose peak friction at the nominal load is ``mu_peak``."""
        return replace(self, mu_scale=mu_peak / self.pdx1)

    def _shape(self, kappa: float, fz: float) -> tuple[float, float, float]:
        dfz = (fz - self.fz0) / self.fz0
        mu = self.mu_scale * (self.pdx1 + self.pdx2 * dfz)
        sign = 1.0 if kappa > 0 else (-1.0 if kappa < 0 else 0.0)
        e = (self.pex1 + self.pex2 * dfz + self.pex3 * dfz * dfz) * (1.0 - self.pex4 * sign)
        stiffness = (self.pkx1 + self.pkx2 * dfz) * math.exp(self.pkx3 * dfz)  # Kxκ / Fz
        b = stiffness / (self.cx * mu)
        return mu, b, e

    def coefficient(self, kappa: float, fz: float) -> float:
        """Fx / Fz at slip ratio ``kappa`` and normal load ``fz`` (N)."""
        mu, b, e = self._shape(kappa, fz)
        u = b * kappa
        y = u - e * (u - math.atan(u))
        return mu * math.sin(self.cx * math.atan(y))

    def slope(self, kappa: float, fz: float) -> float:
        """d(Fx/Fz)/dκ, analytically, on the side of zero that ``kappa`` lies on."""
        mu, b, e = self._shape(kappa, fz)
        u = b * kappa
        y = u - e * (u - math.atan(u))
        dy = b * (1.0 - e * u * u / (1.0 + u * u))
        return mu * math.cos(self.cx * math.atan(y)) * self.cx / (1.0 + y * y) * dy

    def force(self, kappa: float, fz: float) -> float:
        return fz * self.coefficient(kappa, fz)

    def peak_force(self, fz: float) -> float:
        """Dx (eq. 3): the most driving or braking force the tyre gives at this load, N."""
        return self.mu_scale * (self.pdx1 + self.pdx2 * (fz - self.fz0) / self.fz0) * fz

    def slip_stiffness(self, fz: float) -> float:
        """Kxκ = dFx/dκ at κ = 0 (eq. 5), N per unit slip; not changed by the surface scaling."""
        dfz = (fz - self.fz0) / self.fz0
        return fz * (self.pkx1 + self.pkx2 * dfz) * math.exp(self.pkx3 * dfz)

    def peak_braking_slip(self, fz: float) -> float:
        """The (negative) slip ratio at which the braking force peaks, found by a fine search."""
        best_kappa, best = 0.0, 0.0
        kappa = -0.001
        while kappa > -0.6:
            c = -self.coefficient(kappa, fz)
            if c > best:
                best, best_kappa = c, kappa
            kappa -= 0.001
        return best_kappa

    def peak_traction_slip(self, fz: float) -> float:
        """The (positive) slip ratio at which the driving force peaks."""
        best_kappa, best = 0.0, 0.0
        kappa = 0.001
        while kappa < 0.6:
            c = self.coefficient(kappa, fz)
            if c > best:
                best, best_kappa = c, kappa
            kappa += 0.001
        return best_kappa


def _sgn(x: float) -> float:
    return 1.0 if x >= 0 else -1.0


@dataclass(frozen=True)
class MotorcycleTyre:
    """Forces and aligning moment of a motorcycle tyre in sideslip, camber and longitudinal slip.

    Sharp, Evangelou & Limebeer (2004): pure side force (eqs. 7–13, Table II), aligning moment (eqs. 14–22, Table III)
    and combined slip (eqs. 23–31 with the loss functions of §4.4). β is the sideslip, tan α = −v_y / |v_x| of the
    contact centre in the wheel's axes, γ the camber angle, both in radians; Fz the load in newtons. With β, γ and the
    force positive to the same side (SAE axes: y to the right, z down), a positive aligning moment turns the wheel
    towards that side. The fits are symmetric: zero offsets, so F(−β, −γ) = −F(β, γ) in pure slip.

    ``mu_scale`` scales the side force's peak (and the camber twisting moment with it) to a surface; the longitudinal
    tyre carries its own scale. Slip and camber stiffnesses are unchanged.
    """

    longitudinal: LongitudinalTyre
    fz0: float
    r0: float  # crown radius used by the moment formulas, m
    cy: float
    pdy1: float
    pdy2: float
    pdy3: float
    pey1: float
    pey2: float
    pey4: float
    pky1: float
    pky2: float
    pky3: float
    pky4: float
    pky5: float
    pky6: float
    pky7: float
    c_gamma: float
    e_gamma: float
    ct: float
    qbz1: float
    qbz2: float
    qbz5: float
    qbz6: float
    qbz9: float
    qbz10: float
    qdz1: float
    qdz2: float
    qdz3: float
    qdz4: float
    qdz8: float
    qdz9: float
    qdz10: float
    qdz11: float
    qez1: float
    qez2: float
    qez5: float
    qhz3: float
    qhz4: float
    rbx1: float
    rbx2: float
    cxa: float
    rby1: float
    rby2: float
    rby3: float
    cyk: float
    mu_scale: float = 1.0

    @classmethod
    def from_data(cls, tyre: dict[str, Any], combined: dict[str, Any], longitudinal: dict[str, Any]) -> MotorcycleTyre:
        """``tyre`` is one entry of ``tyre_cornering`` in sim-parameters.json, ``combined`` its ``combined_slip``
        block and ``longitudinal`` the ``tyre_longitudinal`` block (Table I), whose pDx1 and pDx2 are replaced by the
        tyre's own (§4.5)."""
        long_raw = dict(longitudinal, **{k: v for k, v in tyre["longitudinal"].items()})
        lat, mz = tyre["lateral"], tyre["aligning"]
        lateral_keys = {"Cy": "cy", "pDy1": "pdy1", "pDy2": "pdy2", "pDy3": "pdy3", "pEy1": "pey1", "pEy2": "pey2",
                        "pEy4": "pey4", "pKy1": "pky1", "pKy2": "pky2", "pKy3": "pky3", "pKy4": "pky4", "pKy5": "pky5",
                        "pKy6": "pky6", "pKy7": "pky7", "Cgamma": "c_gamma", "Egamma": "e_gamma"}
        moment_keys = {"Ct": "ct", "qBz1": "qbz1", "qBz2": "qbz2", "qBz5": "qbz5", "qBz6": "qbz6", "qBz9": "qbz9",
                       "qBz10": "qbz10", "qDz1": "qdz1", "qDz2": "qdz2", "qDz3": "qdz3", "qDz4": "qdz4",
                       "qDz8": "qdz8", "qDz9": "qdz9", "qDz10": "qdz10", "qDz11": "qdz11", "qEz1": "qez1",
                       "qEz2": "qez2", "qEz5": "qez5", "qHz3": "qhz3", "qHz4": "qhz4"}
        combined_keys = {"rBx1": "rbx1", "rBx2": "rbx2", "Cxalpha": "cxa", "rBy1": "rby1", "rBy2": "rby2",
                         "rBy3": "rby3", "Cykappa": "cyk"}
        values = {field: float(lat[key]) for key, field in lateral_keys.items()}
        values.update({field: float(mz[key]) for key, field in moment_keys.items()})
        values.update({field: float(combined[key]) for key, field in combined_keys.items()})
        return cls(longitudinal=LongitudinalTyre.from_data(long_raw), fz0=float(tyre["Fz0_N"]),
                   r0=float(tyre["R0_m"]), **values)

    def for_surface(self, mu_peak: float) -> MotorcycleTyre:
        """The same tyre on a surface whose peak friction at the nominal load is ``mu_peak``, sideways and lengthways."""
        return replace(self, mu_scale=mu_peak / self.pdy1,
                       longitudinal=self.longitudinal.for_surface(mu_peak))

    def with_crown_radius(self, r0: float) -> MotorcycleTyre:
        """The moment formulas scale with the crown radius R0; this sets it to another tyre's."""
        return replace(self, r0=r0)

    def scaled(self, share: float) -> MotorcycleTyre:
        """Every peak multiplied by ``share`` (a tyre not yet warm, for example)."""
        return replace(self, mu_scale=self.mu_scale * share,
                       longitudinal=replace(self.longitudinal, mu_scale=self.longitudinal.mu_scale * share))

    # ── pure side force (eqs. 7–13) ──────────────────────────────────────────

    def _dfz(self, fz: float) -> float:
        return (fz - self.fz0) / self.fz0

    def peak_side_force(self, gamma: float, fz: float) -> float:
        """Dy (eq. 8): the most side force the tyre gives at this camber and load, N."""
        return self.mu_scale * fz * self.pdy1 * math.exp(self.pdy2 * self._dfz(fz)) / (1.0 + self.pdy3 * gamma * gamma)

    def cornering_stiffness(self, gamma: float, fz: float) -> float:
        """Kyα (eq. 10), N per radian of sideslip."""
        g2 = gamma * gamma
        return (self.pky1 * self.fz0 * math.sin(self.pky2 * math.atan(fz / ((self.pky3 + self.pky4 * g2) * self.fz0)))
                / (1.0 + self.pky5 * g2))

    def camber_stiffness(self, fz: float) -> float:
        """Kyγ (eq. 12), N per radian of camber."""
        return (self.pky6 + self.pky7 * self._dfz(fz)) * fz

    def side_force(self, beta: float, gamma: float, fz: float) -> float:
        """Fy0 (eq. 7) in pure sideslip and camber, N."""
        if fz <= 0:
            return 0.0
        dy = self.peak_side_force(gamma, fz)
        ey = self.pey1 + self.pey2 * gamma * gamma + self.pey4 * gamma * _sgn(beta)
        x = self.cornering_stiffness(gamma, fz) / (self.cy * dy) * beta
        xg = self.camber_stiffness(fz) / (self.c_gamma * dy) * gamma
        slip = self.cy * math.atan(x - ey * (x - math.atan(x)))
        camber = self.c_gamma * math.atan(xg - self.e_gamma * (xg - math.atan(xg)))
        return dy * math.sin(slip + camber)

    def camber_share(self, beta: float, gamma: float, fz: float) -> float:
        """Share of the side force due to camber: the camber term's part of the sine's argument in eq. 7."""
        if fz <= 0:
            return 0.0
        dy = self.peak_side_force(gamma, fz)
        ey = self.pey1 + self.pey2 * gamma * gamma + self.pey4 * gamma * _sgn(beta)
        x = self.cornering_stiffness(gamma, fz) / (self.cy * dy) * beta
        xg = self.camber_stiffness(fz) / (self.c_gamma * dy) * gamma
        slip = self.cy * math.atan(x - ey * (x - math.atan(x)))
        camber = self.c_gamma * math.atan(xg - self.e_gamma * (xg - math.atan(xg)))
        total = slip + camber
        return camber / total if total != 0 else 0.0

    # ── aligning moment, pure (eqs. 14–22) and combined (eqs. 27–31) ─────────

    def aligning_moment(self, beta: float, gamma: float, fz: float, kappa: float = 0.0) -> float:
        """Mz about the vertical through the contact point, N m: the pneumatic trail's moment of the slip force
        (Mzt) plus the residual, mostly camber, twisting moment (Mzr)."""
        if fz <= 0:
            return 0.0
        dfz = self._dfz(fz)
        ag = abs(gamma)
        bt = (self.qbz1 + self.qbz2 * dfz) * (1.0 + self.qbz5 * ag + self.qbz6 * gamma * gamma)
        dt = fz * (self.r0 / self.fz0) * (self.qdz1 + self.qdz2 * dfz) * (1.0 + self.qdz3 * ag + self.qdz4 * gamma * gamma)
        et = (self.qez1 + self.qez2 * dfz) * (1.0 + self.qez5 * gamma * (2.0 / math.pi) * math.atan(bt * self.ct * beta))
        dy = self.peak_side_force(gamma, fz)
        br = self.qbz9 + self.qbz10 * self.cornering_stiffness(gamma, fz) / dy  # By·Cy = Kyα / Dy
        root = math.sqrt(1.0 + beta * beta)
        dr = (self.mu_scale * fz * self.r0 * ((self.qdz8 + self.qdz9 * dfz) * gamma
                                               + (self.qdz10 + self.qdz11 * dfz) * gamma * ag) / root)
        shr = (self.qhz3 + self.qhz4 * dfz) * gamma
        long_term = self.longitudinal.slip_stiffness(fz) * kappa / self.cornering_stiffness(0.0, fz)
        lam_t = math.hypot(beta, long_term) * _sgn(beta)
        lam_r = math.hypot(beta + shr, long_term) * _sgn(beta + shr)
        fy_no_camber = self.side_loss(kappa, beta) * self.side_force(beta, 0.0, fz)
        u = bt * lam_t
        mzt = -dt * math.cos(self.ct * math.atan(u - et * (u - math.atan(u)))) / root * fy_no_camber
        mzr = dr * math.cos(math.atan(br * lam_r))
        return mzt + mzr

    # ── combined slip (eqs. 23–26) ───────────────────────────────────────────

    def side_loss(self, kappa: float, beta: float) -> float:
        """cos[Cyκ·atan(Byκ·κ)] (eqs. 25–26): the share of the side force left at longitudinal slip κ."""
        byk = self.rby1 * math.cos(math.atan(self.rby2 * (beta - self.rby3)))
        return math.cos(self.cyk * math.atan(byk * kappa))

    def longitudinal_loss(self, kappa: float, beta: float) -> float:
        """cos[Cxα·atan(Bxα·β)] (eqs. 23–24): the share of the driving or braking force left at sideslip β."""
        bxa = self.rbx1 * math.cos(math.atan(self.rbx2 * kappa))
        return math.cos(self.cxa * math.atan(bxa * beta))

    def longitudinal_force(self, kappa: float, beta: float, fz: float) -> float:
        if fz <= 0:
            return 0.0
        return self.longitudinal_loss(kappa, beta) * self.longitudinal.force(kappa, fz)

    def forces(self, kappa: float, beta: float, gamma: float, fz: float) -> tuple[float, float, float]:
        """(Fx, Fy, Mz) in combined slip."""
        if fz <= 0:
            return 0.0, 0.0, 0.0
        fx = self.longitudinal_force(kappa, beta, fz)
        fy = self.side_loss(kappa, beta) * self.side_force(beta, gamma, fz)
        return fx, fy, self.aligning_moment(beta, gamma, fz, kappa)

    def slip_for_longitudinal_force(self, fx: float, beta: float, fz: float) -> float | None:
        """The slip ratio that gives a driving (+) or braking (−) force ``fx`` at sideslip β, or None if the tyre
        cannot give that much."""
        if fx == 0 or fz <= 0:
            return 0.0
        k_s = self.longitudinal.slip_stiffness(fz) * self.longitudinal_loss(0.0, beta)
        kappa = fx / k_s
        for _ in range(60):
            f = self.longitudinal_force(kappa, beta, fz) - fx
            h = 1e-7
            slope = (self.longitudinal_force(kappa + h, beta, fz) - self.longitudinal_force(kappa - h, beta, fz)) / (2 * h)
            if slope <= 0 or not math.isfinite(slope):
                return None  # past the peak: the force asked for is beyond the tyre
            step = f / slope
            kappa -= step
            if abs(kappa) > 0.6:
                return None
            if abs(step) < 1e-13:
                return kappa
        return None
