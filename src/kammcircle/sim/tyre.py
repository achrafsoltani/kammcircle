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
