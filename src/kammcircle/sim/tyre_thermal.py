"""Tyre temperature: how a tyre warms up and cools down while riding, and what that does to its grip.

Each tyre is two heat stores. The tread, a band as wide as the tyre and as deep as its tread, carries the grip; the
carcass is the casing under the tread and the sidewalls. Heat enters by two routes: rolling, because the rubber's
hysteresis turns the rolling-resistance work into heat inside the tyre, and slip, because the friction work at the
contact patch is released at the tread's surface. Heat leaves the tread's surface by forced convection to the air and
by conduction into the road while each part of the band is in contact, and leaves the carcass through the sidewalls.

The tread's surface is a massless node between the tread's bulk, the air and the road, so a hard stop warms it at once
while the bulk follows over minutes. The grip follows the surface temperature through a working window that no tyre
maker publishes for road tyres: its shape is a labelled stand-in, editable in the app.

Sources: tread rubber properties from Mousavi and Sandu (2020); forced convection from the Churchill–Bernstein
correlation for a cylinder in cross-flow (Incropera, eq. 7.54); air at 10 °C from the Engineering ToolBox and the ISA;
road contact as two semi-infinite bodies touching for the contact time (the classical result for transient conduction).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Air:
    conductivity: float = 0.0251  # W/m K at 10 °C
    kinematic_viscosity: float = 1.46e-5  # m²/s, ISA sea level (1.789e-5 Pa s ÷ 1.225 kg/m³)
    prandtl: float = 0.71
    still_speed: float = 0.5  # m/s of air movement assumed when the motorcycle stands still


def churchill_bernstein(re: float, pr: float) -> float:
    """Mean Nusselt number of a cylinder in cross-flow, valid for Re·Pr ≥ 0.2 (Incropera, eq. 7.54)."""
    return 0.3 + (0.62 * math.sqrt(re) * pr ** (1 / 3) / (1 + (0.4 / pr) ** (2 / 3)) ** 0.25
                  * (1 + (re / 282000.0) ** 0.625) ** 0.8)


@dataclass(frozen=True)
class GripWindow:
    """Share of a warm tyre's grip at a given tread-surface temperature (a stand-in: makers publish no curves)."""

    cold_temp: float = 0.0  # °C at which the grip has fallen to cold_share
    cold_share: float = 0.80
    window_low: float = 30.0  # °C: full grip from here…
    window_high: float = 60.0  # …to here
    hot_drop_per_k: float = 0.005  # share lost per kelvin above the window (overheating)
    floor: float = 0.5

    def factor(self, temp: float) -> float:
        if temp >= self.window_low:
            if temp <= self.window_high:
                return 1.0
            return max(self.floor, 1.0 - self.hot_drop_per_k * (temp - self.window_high))
        span = self.window_low - self.cold_temp
        x = (temp - self.cold_temp) / span
        if x >= 0.0:  # eases into the window with zero slope at its edge
            return self.cold_share + (1.0 - self.cold_share) * (1.0 - (1.0 - x) ** 2)
        # colder still: keep falling at the slope it had at the cold reference, so the curve has no corner
        return max(self.floor, self.cold_share + 2.0 * (1.0 - self.cold_share) * x)

    def temperature_for(self, share: float) -> float:
        """The lowest surface temperature at which the grip reaches ``share`` (≤ 1) of a warm tyre's."""
        if share <= self.factor(-1e9):
            return -math.inf
        lo, hi = -100.0, self.window_low
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if self.factor(mid) >= share:
                hi = mid
            else:
                lo = mid
        return hi


@dataclass(frozen=True)
class TyreThermalParameters:
    radius: float  # m, unloaded
    width: float  # m, section width
    rim_radius: float  # m
    tread_depth: float  # m
    casing_thickness: float  # m, under the tread
    sidewall_thickness: float  # m
    density: float  # kg/m³ of tread rubber
    specific_heat: float  # J/kg K
    conductivity: float  # W/m K
    road_effusivity: float  # W s^½ / m² K, √(k·ρ·c) of the road surface
    radial_stiffness: float  # N/m, for the contact length
    rolling_resistance: float  # share of the load
    hysteresis_to_tread: float  # share of the rolling-loss heat generated in the tread
    real_contact_share: float = 0.1  # share of the footprint where rubber actually touches the road
    air: Air = field(default_factory=Air)

    @property
    def band_area(self) -> float:
        return 2 * math.pi * self.radius * self.width

    @property
    def sidewall_area(self) -> float:
        return 2 * math.pi * (self.radius ** 2 - self.rim_radius ** 2)

    @property
    def tread_capacity(self) -> float:  # J/K
        return self.band_area * self.tread_depth * self.density * self.specific_heat

    @property
    def carcass_capacity(self) -> float:  # J/K
        volume = self.band_area * self.casing_thickness + self.sidewall_area * self.sidewall_thickness
        return volume * self.density * self.specific_heat

    @property
    def tread_to_carcass(self) -> float:  # W/K, through half the tread and half the casing
        return self.conductivity * self.band_area / (0.5 * self.tread_depth + 0.5 * self.casing_thickness)

    @property
    def internal_h(self) -> float:  # W/m² K from the middle of the tread to its surface
        return 2 * self.conductivity / self.tread_depth

    @property
    def rubber_effusivity(self) -> float:
        return math.sqrt(self.conductivity * self.density * self.specific_heat)

    def air_h(self, speed: float) -> float:
        """Forced convection on the tyre, treated as a cylinder of its own diameter in the riding wind."""
        a = self.air
        diameter = 2 * self.radius
        re = max(speed, a.still_speed) * diameter / a.kinematic_viscosity
        return churchill_bernstein(re, a.prandtl) * a.conductivity / diameter

    def contact_length(self, load: float) -> float:
        """Chord of a tyre pressed down by load ÷ radial stiffness."""
        deflection = min(max(load, 0.0) / self.radial_stiffness, 0.5 * self.radius)
        return 2 * math.sqrt(max(2 * self.radius * deflection - deflection ** 2, 0.0))

    def road_h(self, speed: float, load: float) -> float:
        """Conduction into the road, averaged over the band: each piece of tread touches the road for L/v once a
        revolution, and two semi-infinite bodies in contact for time t exchange 2·e·ΔT·√(t/π) per unit area, with
        e the effusivity of the pair in series. Only the real contact, a small share of the footprint where the rubber
        touches the tops of the road's roughness, conducts."""
        length = self.contact_length(load)
        if length <= 0.0:
            return 0.0
        speed = max(speed, self.air.still_speed)
        contact_time = length / speed
        e_pair = self.rubber_effusivity * self.road_effusivity / (self.rubber_effusivity + self.road_effusivity)
        h_contact = 2 * e_pair / math.sqrt(math.pi * contact_time)  # mean over the contact
        return self.real_contact_share * h_contact * length / (2 * math.pi * self.radius)  # band share in contact

    def rolling_heat(self, speed: float, load: float) -> float:
        """Rolling-resistance power, all of it turned into heat in the tyre (W)."""
        return self.rolling_resistance * max(load, 0.0) * max(speed, 0.0)


@dataclass
class TyreState:
    tread: float  # °C, bulk of the tread band
    carcass: float  # °C
    surface: float  # °C, tread surface: the grip temperature


def surface_temperature(p: TyreThermalParameters, tread: float, air: float, road: float, speed: float, load: float,
                        slip_heat: float) -> float:
    """The massless surface node: conduction from the tread's bulk, convection to the air, conduction to the road and
    the slip heat released at the surface balance."""
    hi, ha, hr = p.internal_h, p.air_h(speed), p.road_h(speed, load)
    q = slip_heat / p.band_area
    return (hi * tread + ha * air + hr * road + q) / (hi + ha + hr)


def step(p: TyreThermalParameters, s: TyreState, dt: float, *, air: float, road: float, speed: float, load: float,
         slip_heat: float) -> TyreState:
    """Advance one tyre by dt (s), explicit Euler (time constants are minutes; dt of a second is ample)."""
    rolling = p.rolling_heat(speed, load)
    surface = surface_temperature(p, s.tread, air, road, speed, load, slip_heat)
    into_tread = p.internal_h * p.band_area * (surface - s.tread)  # from the surface
    to_carcass = p.tread_to_carcass * (s.tread - s.carcass)
    sidewalls = p.air_h(speed) * p.sidewall_area * (s.carcass - air)
    tread = s.tread + dt * (p.hysteresis_to_tread * rolling + into_tread - to_carcass) / p.tread_capacity
    carcass = s.carcass + dt * ((1 - p.hysteresis_to_tread) * rolling + to_carcass - sidewalls) / p.carcass_capacity
    return TyreState(tread, carcass, surface_temperature(p, tread, air, road, speed, load, slip_heat))


def steady_state(p: TyreThermalParameters, *, air: float, road: float, speed: float, load: float,
                 slip_heat: float) -> TyreState:
    """The temperatures at which heat in balances heat out, for these steady conditions."""
    hi, ha, hr = p.internal_h, p.air_h(speed), p.road_h(speed, load)
    a = p.band_area
    k_surface = hi * a * (ha + hr) / (hi + ha + hr)  # bulk tread → air and road, through the surface
    t_env = (ha * air + hr * road) / (ha + hr)
    slip_in = slip_heat * hi / (hi + ha + hr)  # share of the slip heat that reaches the bulk
    g, ks = p.tread_to_carcass, p.air_h(speed) * p.sidewall_area
    rolling = p.rolling_heat(speed, load)
    # [k_surface + g, −g; −g, g + ks] · [T_t, T_c] = [β·P + slip_in + k_surface·t_env, (1 − β)·P + ks·air]
    a11, a12, a21, a22 = k_surface + g, -g, -g, g + ks
    b1 = p.hysteresis_to_tread * rolling + slip_in + k_surface * t_env
    b2 = (1 - p.hysteresis_to_tread) * rolling + ks * air
    det = a11 * a22 - a12 * a21
    tread = (b1 * a22 - a12 * b2) / det
    carcass = (a11 * b2 - a21 * b1) / det
    return TyreState(tread, carcass, surface_temperature(p, tread, air, road, speed, load, slip_heat))


# ─── a ride: both tyres warming up together ──────────────────────────────────


RIDING_STYLES = {  # mean share of the available grip in use, front and rear, over a ride (stand-ins)
    "gentle": 0.05,
    "brisk": 0.15,
    "hard": 0.35,
}


@dataclass
class WarmUpSample:
    t: float  # s
    distance: float  # m
    surface: tuple[float, float]  # front, rear (°C)
    tread: tuple[float, float]
    carcass: tuple[float, float]
    grip: tuple[float, float]  # share of a warm tyre's grip


@dataclass
class WarmUpRun:
    front: TyreThermalParameters
    rear: TyreThermalParameters
    loads: tuple[float, float]  # N, static
    slip_heat: tuple[float, float]  # W, from the riding style
    window: GripWindow
    air: float
    road: float
    speed: float  # m/s
    start: float  # °C
    duration: float = 1200.0  # s
    dt: float = 1.0
    record_every: int = 5
    trace: list[WarmUpSample] = field(default_factory=list)
    t: float = 0.0
    states: tuple[TyreState, TyreState] | None = None
    reached: list[float | None] = field(default_factory=lambda: [None, None])  # s when each tyre enters the window
    stopped: bool = False

    def __post_init__(self) -> None:
        if self.states is None:
            self.states = tuple(
                TyreState(self.start, self.start,
                          surface_temperature(p, self.start, self.air, self.road, self.speed, n, q))
                for p, n, q in zip((self.front, self.rear), self.loads, self.slip_heat))
        self._check_window()
        self._record()

    def step(self) -> None:
        if self.stopped:
            return
        self.states = tuple(
            step(p, s, self.dt, air=self.air, road=self.road, speed=self.speed, load=n, slip_heat=q)
            for p, s, n, q in zip((self.front, self.rear), self.states, self.loads, self.slip_heat))
        self.t += self.dt
        self._check_window()
        if round(self.t / self.dt) % self.record_every == 0:
            self._record()
        if self.t >= self.duration - 1e-9:
            self.stopped = True
            if self.trace[-1].t != self.t:
                self._record()

    def _check_window(self) -> None:
        for i, s in enumerate(self.states):
            if self.reached[i] is None and s.surface >= self.window.window_low:
                self.reached[i] = self.t

    def _record(self) -> None:
        f, r = self.states
        self.trace.append(WarmUpSample(self.t, self.speed * self.t, (f.surface, r.surface), (f.tread, r.tread),
                                       (f.carcass, r.carcass),
                                       (self.window.factor(f.surface), self.window.factor(r.surface))))

    def steady(self) -> tuple[TyreState, TyreState]:
        return tuple(steady_state(p, air=self.air, road=self.road, speed=self.speed, load=n, slip_heat=q)
                     for p, n, q in zip((self.front, self.rear), self.loads, self.slip_heat))

    def time_to_share(self, share: float) -> list[float | None]:
        """Seconds until each tyre's grip first reaches ``share`` of a warm tyre's, within the recorded run."""
        out: list[float | None] = []
        for i in range(2):
            out.append(next((x.t for x in self.trace if x.grip[i] >= share - 1e-12), None))
        return out


def run_warm_up(run: WarmUpRun) -> WarmUpRun:
    while not run.stopped:
        run.step()
    return run
