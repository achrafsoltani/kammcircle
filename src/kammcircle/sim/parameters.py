"""Build simulation parameters from the catalogue bike, its tyres, the rider's variables (pillion and luggage
included) and the packaged model data, keeping a note of where every number comes from so that the app can show it."""

from __future__ import annotations

from dataclasses import dataclass

from .. import catalogue
from ..rider import RiderSetup
from .acceleration import Engine, Gearbox, Powertrain, drag_area_from_top_speed
from .braking import ABSSettings, BrakingParameters
from .suspension import SuspensionParameters
from .tyre import LongitudinalTyre

G = 9.81


@dataclass(frozen=True)
class ParameterNote:
    name: str
    value: str
    basis: str


@dataclass(frozen=True)
class MassPoint:
    name: str
    mass: float  # kg
    x: float  # m ahead of the rear contact patch
    h: float  # m above the road
    own_pitch_inertia: float  # kg m² about its own centre of gravity


def bike_front_share(bike: catalogue.Bike, setup: RiderSetup) -> tuple[float, str]:
    if not setup.is_example("bike_front_weight_pct"):
        return setup.bike_front_weight_pct / 100, "your value"
    if bike.front_weight_share is not None:
        return bike.front_weight_share, "measured axle weights (catalogue, derived)"
    return setup.bike_front_weight_pct / 100, "example: no published weight split"


def mass_points(bike: catalogue.Bike, setup: RiderSetup, *, loaded: bool = True) -> list[MassPoint]:
    """The motorcycle, the rider and, when ``loaded``, the pillion and the luggage, as point masses."""
    inertia = catalogue.load_json("sim-parameters.json")["pitch_inertia_kgm2"]
    share, _ = bike_front_share(bike, setup)
    points = [
        MassPoint("motorcycle", bike.mass_kg, share * bike.wheelbase_mm / 1000, setup.bike_cog_height_mm / 1000,
                  inertia["bike_own"]),
        MassPoint("rider", setup.rider_mass_kg, setup.rider_cog_ahead_mm / 1000, setup.rider_cog_height_mm / 1000,
                  inertia["rider_upper_body"]),
    ]
    if loaded and setup.pillion_mass_kg > 0:
        points.append(MassPoint("pillion", setup.pillion_mass_kg, setup.pillion_cog_ahead_mm / 1000,
                                setup.pillion_cog_height_mm / 1000, inertia["rider_upper_body"]))
    if loaded and setup.luggage_mass_kg > 0:
        points.append(MassPoint("luggage", setup.luggage_mass_kg, setup.luggage_cog_ahead_mm / 1000,
                                setup.luggage_cog_height_mm / 1000, 0.0))
    return points


def combined(points: list[MassPoint]) -> tuple[float, float, float, float]:
    """Total mass, CoG distance ahead of the rear contact patch, CoG height, pitch inertia about the CoG."""
    mass = sum(p.mass for p in points)
    b = sum(p.mass * p.x for p in points) / mass
    h = sum(p.mass * p.h for p in points) / mass
    inertia = sum(p.own_pitch_inertia + p.mass * ((p.x - b) ** 2 + (p.h - h) ** 2) for p in points)
    return mass, b, h, inertia


def static_wheel_loads(bike: catalogue.Bike, setup: RiderSetup, *, loaded: bool = True) -> tuple[float, float]:
    """Front and rear tyre loads at rest, in newtons."""
    mass, b, _, _ = combined(mass_points(bike, setup, loaded=loaded))
    front = mass * G * b / (bike.wheelbase_mm / 1000)
    return front, mass * G - front


def braking_parameters(
    bike: catalogue.Bike, setup: RiderSetup, mu: float, tyres: catalogue.TyreChoice | None = None
) -> tuple[BrakingParameters, list[ParameterNote]]:
    data = catalogue.load_json("sim-parameters.json")
    tyres = tyres or catalogue.original_tyres(bike)
    notes: list[ParameterNote] = []

    def note(name: str, value: str, basis: str) -> None:
        notes.append(ParameterNote(name, value, basis))

    def mine(name: str) -> str:
        return "example value" if setup.is_example(name) else "your value"

    wheelbase = bike.wheelbase_mm / 1000
    front_r, rear_r = tyres.front.radius_mm / 1000, tyres.rear.radius_mm / 1000
    note("Wheelbase", f"{bike.wheelbase_mm:.0f} mm", "manufacturer or test figure (catalogue)")
    note("Tyres", f"{tyres.front.name} · {tyres.rear.name}", "your choice in the Tyres tab")
    note("Wheel radii", f"{front_r * 1000:.1f} / {rear_r * 1000:.1f} mm",
         "the makers' design diameters" if tyres.front.design and tyres.rear.design
         else "from the tyre size codes where the maker publishes no design diameter (derived)")

    share, share_basis = bike_front_share(bike, setup)
    note("Motorcycle's weight on the front wheel", f"{share * 100:.1f} %", share_basis)
    note("Motorcycle mass", f"{bike.mass_kg:.0f} kg", bike.mass_note)
    note("Rider mass", f"{setup.rider_mass_kg:.0f} kg", mine("rider_mass_kg"))
    note("Motorcycle CoG height", f"{setup.bike_cog_height_mm:.0f} mm", mine("bike_cog_height_mm"))
    note("Rider CoG height / ahead of rear axle", f"{setup.rider_cog_height_mm:.0f} / {setup.rider_cog_ahead_mm:.0f} mm",
         "example values" if setup.is_example("rider_cog_height_mm") and setup.is_example("rider_cog_ahead_mm")
         else "your values")
    points = mass_points(bike, setup)
    for point in points[2:]:
        note(point.name.capitalize(), f"{point.mass:.0f} kg at {point.h * 1000:.0f} mm high, "
                                      f"{point.x * 1000:+.0f} mm ahead of the rear axle",
             "your values" if not setup.is_example(f"{point.name}_cog_height_mm") else "your mass, example position")

    mass, b, h, pitch = combined(points)
    note("Pitch inertia about the combined CoG", f"{pitch:.1f} kg m²",
         "stand-in: GSX-R1000 body inertias (Sharp et al. 2004) plus the parallel-axis terms")
    spin = data["wheel_spin_inertia_kgm2"]
    note("Wheel spin inertias", f"{spin['front']} / {spin['rear']} kg m²", "stand-in: GSX-R1000 (Sharp et al. 2004)")

    tyre = LongitudinalTyre.from_data(data["tyre_longitudinal"]).for_surface(mu)
    note("Tyre braking curve", f"peak μ {mu:.2f} at the nominal load",
         "Magic Formula fit to a 160/70 ZR17 tyre (Sharp et al. 2004), scaled to the surface; the same for every "
         "tyre, as no maker publishes grip curves")

    # The brakes are a property of the motorcycle: sized once, for the rider alone, so that a pillion or luggage
    # leaves the same torque for the same squeeze.
    capacity = data["brake_capacity"]
    k = capacity["lock_margin"] * capacity["reference_mu"]
    solo_mass, solo_b, _, _ = combined(points[:2])
    front_max = k * solo_mass * G * front_r
    rear_max = k * solo_mass * G * (1 - solo_b / wheelbase) * rear_r
    note("Brake torque at full lever / pedal", f"{front_max:.0f} / {rear_max:.0f} N m",
         "modelling choice: enough to lock either wheel on dry asphalt with the rider alone")

    a = data["abs"]
    settings = ABSSettings(a["release_factor"], a["reapply_factor"], a["release_rate_per_s"], a["apply_rate_per_s"])
    note("ABS", "slip-band controller around the tyre's peak slip", "generic model, not Royal Enfield's")

    params = BrakingParameters(
        wheelbase=wheelbase, front_radius=front_r, rear_radius=rear_r, mass=mass, cog_ahead_of_rear=b, cog_height=h,
        pitch_inertia=pitch, front_wheel_inertia=spin["front"], rear_wheel_inertia=spin["rear"], tyre=tyre,
        front_brake_max=front_max, rear_brake_max=rear_max, abs_settings=settings, g=G,
    )
    note("Rear lifts above", f"{params.lift_deceleration_g:.2f} g", "(L − b) ÷ h for these values")
    return params, notes


def suspension_parameters(bike: catalogue.Bike, setup: RiderSetup) -> tuple[SuspensionParameters, list[ParameterNote]]:
    data = catalogue.load_json("sim-parameters.json")
    chassis = bike.raw["chassis"]
    notes: list[ParameterNote] = []
    travel_f, travel_r = chassis["front_travel_mm"] / 1000, chassis["rear_travel_mm"] / 1000
    notes.append(ParameterNote("Suspension travel", f"{travel_f * 1000:.0f} / {travel_r * 1000:.0f} mm",
                               "manufacturer or test figure (catalogue)"))
    sag_basis = ("example: about 30 % of the travel (Touratech's set-up guide)"
                 if setup.is_example("front_sag_pct") and setup.is_example("rear_sag_pct") else "your values")
    notes.append(ParameterNote("Rider sag", f"{setup.front_sag_pct:.0f} % / {setup.rear_sag_pct:.0f} % of travel",
                               sag_basis + "; springs sized for the rider alone, so a pillion or luggage adds sag"))
    unsprung = data["unsprung_mass_kg"]
    notes.append(ParameterNote("Unsprung masses", f"{unsprung['front']} / {unsprung['rear']} kg",
                               "stand-in: GSX-R1000 (Sharp et al. 2004)"))
    tyre_k = data["tyre_radial_stiffness_N_per_m"]
    notes.append(ParameterNote("Tyre radial stiffness", f"{tyre_k['front'] / 1000:.0f} / {tyre_k['rear'] / 1000:.0f} kN/m",
                               "stand-in: sport tyres (Sharp et al. 2004)"))
    model = data["suspension_model"]
    notes.append(ParameterNote("Suspension damping", f"{model['damping_ratio']:.2f} of critical",
                               "modelling choice: no published damping data"))
    inertia = data["pitch_inertia_kgm2"]
    share, _ = bike_front_share(bike, setup)
    spring_front, spring_rear = static_wheel_loads(bike, setup, loaded=False)
    extras = tuple((p.mass, p.x, p.h, p.own_pitch_inertia) for p in mass_points(bike, setup)[2:])
    params = SuspensionParameters(
        rake_deg=bike.rake_deg, front_travel=travel_f, rear_travel=travel_r,
        front_sag=setup.front_sag_pct / 100 * travel_f, rear_sag=setup.rear_sag_pct / 100 * travel_r,
        front_unsprung=unsprung["front"], rear_unsprung=unsprung["rear"],
        tyre_k_front=tyre_k["front"], tyre_k_rear=tyre_k["rear"],
        damping_ratio=model["damping_ratio"], tyre_damping_ratio=model["tyre_damping_ratio"],
        stop_k=model["stop_stiffness_N_per_m"], stop_c=model["stop_damping_N_s_per_m"],
        bike_mass=bike.mass_kg, bike_cog_x=share * bike.wheelbase_mm / 1000, bike_cog_h=setup.bike_cog_height_mm / 1000,
        rider_mass=setup.rider_mass_kg, rider_cog_x=setup.rider_cog_ahead_mm / 1000,
        rider_cog_h=setup.rider_cog_height_mm / 1000,
        bike_own_pitch_inertia=inertia["bike_own"], rider_own_pitch_inertia=inertia["rider_upper_body"],
        extra_masses=extras, spring_load_front=spring_front, spring_load_rear=spring_rear,
    )
    return params, notes


@dataclass(frozen=True)
class PowertrainSpec:
    engine: Engine
    gearbox: Gearbox
    efficiency: float
    shift_time: float
    cda: float
    crr: float
    air_density: float

    def powertrain(self, shift_rpm: float, launch_rpm: float) -> Powertrain:
        return Powertrain(self.engine, self.gearbox, self.efficiency, self.shift_time, shift_rpm, launch_rpm,
                          rpm=self.engine.idle_rpm)


def acceleration_parameters(
    bike: catalogue.Bike, setup: RiderSetup, tyres: catalogue.TyreChoice | None = None
) -> tuple[PowertrainSpec, list[ParameterNote]]:
    data = catalogue.load_json("sim-parameters.json")
    drive = bike.raw["drivetrain"]
    pt, road = data["powertrain"], data["road_load"]
    tyres = tyres or catalogue.original_tyres(bike)
    engine = Engine(
        peak_torque_nm=drive["max_torque_nm"], peak_torque_rpm=drive["max_torque_rpm"],
        peak_power_kw=drive["max_power_kw"], peak_power_rpm=drive["max_power_rpm"], idle_rpm=drive["idle_rpm"],
        limit_rpm=drive["max_power_rpm"] + pt["rev_limit_above_peak_power_rpm"],
        idle_torque_share=pt["torque_at_idle_share"],
    )
    gearbox = Gearbox(drive["primary_ratio"], tuple(drive["gear_ratios"]), drive["secondary_ratio"])
    solo_mass, *_ = combined(mass_points(bike, setup, loaded=False))
    top = bike.raw["top_speed_kmh"]
    cda = drag_area_from_top_speed(engine, gearbox, top["value"], solo_mass, pt["efficiency"], road["rolling_resistance"],
                                   road["air_density_kg_m3"], tyres.rear.radius_mm / 1000)
    notes = [
        ParameterNote("Engine", f"{drive['max_torque_nm']:g} N m at {drive['max_torque_rpm']} rpm, "
                                f"{drive['max_power_kw']:g} kW at {drive['max_power_rpm']} rpm",
                      "manufacturer's figures; the curve's shape between and beyond them is an assumption"),
        ParameterNote("Gearing", f"primary {gearbox.primary}, gears {', '.join(f'{g:g}' for g in gearbox.gears)}, "
                                 f"secondary {gearbox.secondary}", "manufacturer's figures"),
        ParameterNote("Rev limit", f"{engine.limit_rpm:.0f} rpm", "stand-in: 1000 rpm above peak power"),
        ParameterNote("Drivetrain efficiency / shift time", f"{pt['efficiency']:.0%} / {pt['shift_time_s']:.2f} s", "stand-ins"),
        ParameterNote("Drag area CdA", f"{cda:.2f} m²",
                      f"derived: drag and rolling resistance balance the rear-wheel power at the reported top speed "
                      f"of about {top['value']} km/h ({top['basis']})"),
        ParameterNote("Rolling resistance", f"{road['rolling_resistance']:.3f} of the load", "stand-in"),
    ]
    spec = PowertrainSpec(engine, gearbox, pt["efficiency"], pt["shift_time_s"], cda, road["rolling_resistance"],
                          road["air_density_kg_m3"])
    return spec, notes
