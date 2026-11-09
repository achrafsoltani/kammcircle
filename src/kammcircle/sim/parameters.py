"""Build simulation parameters from the catalogue bike, its tyres, the rider's variables (pillion and luggage
included) and the packaged model data, keeping a note of where every number comes from so that the app can show it."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .. import catalogue
from ..physics.tyres import parse_tyre_size
from ..rider import RiderSetup
from .acceleration import Engine, Gearbox, Powertrain, drag_area_from_top_speed
from .braking import ABSSettings, BrakingParameters
from .lateral import WhippleParameters
from .tyre_thermal import Air, GripWindow, TyreThermalParameters
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
    bike: catalogue.Bike, setup: RiderSetup, mu: float, tyres: catalogue.TyreChoice | None = None,
    grip: tuple[float, float] = (1.0, 1.0),
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
        front_grip=grip[0], rear_grip=grip[1],
    )
    if grip != (1.0, 1.0):
        note("Tyres not yet warm", f"front {grip[0]:.0%}, rear {grip[1]:.0%} of a warm tyre's grip",
             "the tyre temperatures set at the top of the window, through the Tyre temperature tab's grip window "
             "(a stand-in); the whole force curve is scaled")
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
    declutch_rpm: float = 0.0

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
        drag_share_idle=pt["closed_throttle_drag_share_of_peak_torque"]["at_idle"],
        drag_share_limit=pt["closed_throttle_drag_share_of_peak_torque"]["at_rev_limit"],
        inertia=pt["engine_inertia_kgm2"],
    )
    gearbox = Gearbox(drive["primary_ratio"], tuple(drive["gear_ratios"]), drive["secondary_ratio"])
    solo_mass, *_ = combined(mass_points(bike, setup, loaded=False))
    top = bike.raw["top_speed_kmh"]
    measured = drive.get("efficiency")
    efficiency = measured["value"] if measured else pt["efficiency"]
    cda = drag_area_from_top_speed(engine, gearbox, top["value"], solo_mass, efficiency, road["rolling_resistance"],
                                   road["air_density_kg_m3"], tyres.rear.radius_mm / 1000)
    notes = [
        ParameterNote("Engine", f"{drive['max_torque_nm']:g} N m at {drive['max_torque_rpm']} rpm, "
                                f"{drive['max_power_kw']:g} kW at {drive['max_power_rpm']} rpm",
                      "manufacturer's figures; the curve's shape between and beyond them is an assumption"),
        ParameterNote("Gearing", f"primary {gearbox.primary}, gears {', '.join(f'{g:g}' for g in gearbox.gears)}, "
                                 f"secondary {gearbox.secondary}", "manufacturer's figures"),
        ParameterNote("Rev limit", f"{engine.limit_rpm:.0f} rpm", "stand-in: 1000 rpm above peak power"),
        ParameterNote("Drivetrain efficiency", f"{efficiency:.1%}",
                      "derived: rear-wheel power on a dynamometer (Cycle World) over the maker's crankshaft figure"
                      if measured else "stand-in; no rear-wheel measurement recorded for this motorcycle"),
        ParameterNote("Shift time", f"{pt['shift_time_s']:.2f} s", "stand-in"),
        ParameterNote("Drag area CdA", f"{cda:.2f} m²",
                      f"derived: drag and rolling resistance balance the rear-wheel power at the reported top speed "
                      f"of about {top['value']} km/h ({top['basis']})"),
        ParameterNote("Rolling resistance", f"{road['rolling_resistance']:.3f} of the load", "stand-in"),
        ParameterNote("Engine drag, throttle shut", f"{engine.drag_torque(engine.idle_rpm):.1f} N m at idle to "
                                                    f"{engine.drag_torque(engine.limit_rpm):.1f} N m at the rev limit",
                      "stand-in: 10 % to 30 % of the peak torque; no motoring figures are published"),
        ParameterNote("Engine rotating inertia", f"{engine.inertia:g} kg m² at the crankshaft, "
                                                 f"{engine.inertia * gearbox.overall(1) ** 2:.1f} kg m² at the rear wheel "
                                                 f"in 1st", "stand-in; no figure is published"),
        ParameterNote("Clutch", drive.get("clutch", "not recorded"), "manufacturer's figures; a slipper's back-torque "
                                                                   "limit is not modelled"),
    ]
    spec = PowertrainSpec(engine, gearbox, efficiency, pt["shift_time_s"], cda, road["rolling_resistance"],
                          road["air_density_kg_m3"], declutch_rpm=pt["declutch_at_idle_multiple"] * engine.idle_rpm)
    return spec, notes


@dataclass(frozen=True)
class RiderSteering:
    torque_lag: float  # s
    settled_fraction: float  # share of the wanted lean that counts as leaned in


def lateral_parameters(
    bike: catalogue.Bike, setup: RiderSetup, tyres: catalogue.TyreChoice | None = None
) -> tuple[WhippleParameters, RiderSteering, list[ParameterNote]]:
    """The 25 design parameters of the benchmark lean-and-steer model for this motorcycle, its tyres and its load.
    The rear body is the motorcycle without its wheels and steered front frame, plus the rider, pillion and luggage,
    all rigid together; benchmark axes: x forward from the rear contact, z down."""
    data = catalogue.load_json("sim-parameters.json")
    lat, spin, steering = data["lateral_model"], data["wheel_spin_inertia_kgm2"], data["rider_steering"]
    tyres = tyres or catalogue.original_tyres(bike)
    w, c, lam = bike.wheelbase_mm / 1000, bike.trail_mm / 1000, math.radians(bike.rake_deg)
    sl, cl = math.sin(lam), math.cos(lam)
    r_f, r_r = tyres.front.radius_mm / 1000, tyres.rear.radius_mm / 1000
    m_f, m_r = lat["wheel_mass_kg"]["front"], lat["wheel_mass_kg"]["rear"]

    ff = lat["front_frame"]
    m_h = ff["mass_kg"]
    h_h = r_f + ff["cog_above_front_axle_m"]
    x_h = w + c - h_h * math.tan(lam)  # on the steering axis, which meets the road a trail ahead of the front contact
    fork = ff["inertia_fork_axes_kgm2"]
    across, along = fork["across_fork"], fork["along_fork"]
    i_hxx, i_hzz = across * cl * cl + along * sl * sl, across * sl * sl + along * cl * cl
    i_hxz = (along - across) * sl * cl

    points = mass_points(bike, setup)
    motorcycle = points[0]
    rest = motorcycle.mass - m_f - m_r - m_h
    if rest <= 0.25 * motorcycle.mass:
        raise ValueError(f"{bike.name}: the stand-in wheel and fork masses leave too little for the frame")
    rest_x = (motorcycle.mass * motorcycle.x - m_f * w - m_h * x_h) / rest
    rest_h = (motorcycle.mass * motorcycle.h - m_r * r_r - m_f * r_f - m_h * h_h) / rest
    frame, person = lat["main_frame_inertia_kgm2"], lat["rider_inertia_kgm2"]
    none = {"xx": 0.0, "yy": 0.0, "zz": 0.0, "xz": 0.0}
    bodies = [(rest, rest_x, rest_h, frame)]
    bodies += [(pt.mass, pt.x, pt.h, none if pt.name == "luggage" else person) for pt in points[1:]]
    m_b = sum(m for m, *_ in bodies)
    x_b = sum(m * x for m, x, _, _ in bodies) / m_b
    h_b = sum(m * h for m, _, h, _ in bodies) / m_b
    i_bxx = sum(own["xx"] + m * (h - h_b) ** 2 for m, x, h, own in bodies)
    i_byy = sum(own["yy"] + m * ((x - x_b) ** 2 + (h - h_b) ** 2) for m, x, h, own in bodies)
    i_bzz = sum(own["zz"] + m * (x - x_b) ** 2 for m, x, h, own in bodies)
    i_bxz = sum(own["xz"] + m * (x - x_b) * (h - h_b) for m, x, h, own in bodies)  # −m·Δx·Δz with z down

    params = WhippleParameters(
        w=w, c=c, lam=lam,
        r_r=r_r, m_r=m_r, i_rxx=lat["wheel_diametral_inertia_kgm2"]["rear"], i_ryy=spin["rear"],
        x_b=x_b, z_b=-h_b, m_b=m_b, i_bxx=i_bxx, i_bxz=i_bxz, i_byy=i_byy, i_bzz=i_bzz,
        x_h=x_h, z_h=-h_h, m_h=m_h, i_hxx=i_hxx, i_hxz=i_hxz, i_hyy=fork["lateral"], i_hzz=i_hzz,
        r_f=r_f, m_f=m_f, i_fxx=lat["wheel_diametral_inertia_kgm2"]["front"], i_fyy=spin["front"],
    )
    stand_in = "stand-in: GSX-R1000 and rider (Sharp et al. 2004)"
    notes = [
        ParameterNote("Steering geometry", f"rake {bike.rake_deg:g}°, trail {bike.trail_mm:g} mm, "
                                           f"wheelbase {bike.wheelbase_mm:.0f} mm", "manufacturer or test figures (catalogue)"),
        ParameterNote("Wheel radii", f"{r_f * 1000:.1f} / {r_r * 1000:.1f} mm", "the fitted tyres (Tyres tab)"),
        ParameterNote("Wheel masses", f"{m_f:g} / {m_r:g} kg", stand_in),
        ParameterNote("Wheel spin inertias", f"{spin['front']} / {spin['rear']} kg m²",
                      stand_in + "; they set the gyroscopic moments"),
        ParameterNote("Steered front frame", f"{m_h:g} kg, on the steering axis {ff['cog_above_front_axle_m'] * 1000:.0f} mm "
                                             "above the front axle", stand_in),
        ParameterNote("Rear frame with its riders and load", f"{m_b:.0f} kg, centre of mass {x_b * 1000:.0f} mm ahead of "
                                                             f"the rear contact and {h_b * 1000:.0f} mm high",
                      "derived: the motorcycle less its wheels and front frame, plus the rider, pillion and luggage "
                      "of the Rider and bike tab"),
        ParameterNote("Roll / yaw inertia of the rear frame", f"{i_bxx:.1f} / {i_bzz:.1f} kg m² about its centre of mass",
                      "derived: stand-in body inertias plus the parallel-axis terms"),
        ParameterNote("Rider's steering", f"torque from the lean error and lean rate, through a {steering['torque_lag_s']:g} s lag",
                      "controller form of Sharp et al. 2004; lag reported by Åström et al. 2005"),
    ]
    return params, RiderSteering(steering["torque_lag_s"], steering["lean_settled_fraction"]), notes


def slip_heat(tyre: LongitudinalTyre, load: float, share: float, speed: float) -> float:
    """Friction power released at the contact patch when a tyre carries ``share`` of its peak force on average:
    force × slip speed, with the slip from the tyre's force–slip curve."""
    if share <= 0.0 or load <= 0.0 or speed <= 0.0:
        return 0.0
    peak = tyre.peak_traction_slip(load)
    target = share * tyre.force(peak, load)
    lo, hi = 0.0, peak
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if tyre.force(mid, load) < target else (lo, mid)
    return target * 0.5 * (lo + hi) * speed


@dataclass(frozen=True)
class ThermalSetup:
    front: TyreThermalParameters
    rear: TyreThermalParameters
    loads: tuple[float, float]  # N, static, with the rider, pillion and luggage
    window: GripWindow
    styles: dict[str, float]
    tyre: LongitudinalTyre  # the dry-asphalt force–slip curve, for the slip heat


def thermal_parameters(
    bike: catalogue.Bike, setup: RiderSetup, tyres: catalogue.TyreChoice | None = None
) -> tuple[ThermalSetup, list[ParameterNote]]:
    """Both tyres' thermal parameters from their sizes, the tread-rubber and air properties and the stand-ins."""
    data = catalogue.load_json("sim-parameters.json")
    th = data["tyre_thermal"]
    tyres = tyres or catalogue.original_tyres(bike)
    rubber, layers, road, air = th["tread_rubber"], th["layers_m"], th["road_surface"], th["air"]
    stiffness = data["tyre_radial_stiffness_N_per_m"]
    rolling = data["road_load"]["rolling_resistance"]
    road_e = math.sqrt(road["conductivity_W_mK"] * road["density_kg_m3"] * road["specific_heat_J_kgK"])
    air_props = Air(air["conductivity_W_mK"], air["kinematic_viscosity_m2_s"], air["prandtl"], air["still_air_speed_m_s"])

    def build(listing: catalogue.TyreListing, position: str) -> TyreThermalParameters:
        size = parse_tyre_size(listing.size)
        return TyreThermalParameters(
            radius=listing.radius_mm / 1000, width=2 * listing.crown_radius_mm / 1000,
            rim_radius=size.rim_in * 25.4 / 2000, tread_depth=layers["tread_depth"],
            casing_thickness=layers["casing_under_tread"], sidewall_thickness=layers["sidewall"],
            density=rubber["density_kg_m3"], specific_heat=rubber["specific_heat_J_kgK"],
            conductivity=rubber["conductivity_W_mK"], road_effusivity=road_e, radial_stiffness=stiffness[position],
            rolling_resistance=rolling, hysteresis_to_tread=th["hysteresis_to_tread"]["value"],
            real_contact_share=road["real_contact_share"], air=air_props)

    front, rear = build(tyres.front, "front"), build(tyres.rear, "rear")
    loads = static_wheel_loads(bike, setup)
    gw = th["grip_window"]
    window = GripWindow(gw["cold_temp_C"], gw["cold_share"], gw["window_low_C"], gw["window_high_C"],
                        gw["hot_drop_per_K"], gw["floor"])
    styles = {k: v for k, v in th["riding_styles"].items() if isinstance(v, float)}
    tyre = LongitudinalTyre.from_data(data["tyre_longitudinal"]).for_surface(1.0)
    notes = [
        ParameterNote("Tyres", f"{tyres.front.name} · {tyres.rear.name}", "your choice in the Tyres tab; their sizes set "
                                                                         "the tread band and sidewall areas"),
        ParameterNote("Heat stores, front / rear", f"tread {front.tread_capacity / 1000:.1f} / {rear.tread_capacity / 1000:.1f} kJ/K, "
                                                   f"carcass {front.carcass_capacity / 1000:.1f} / {rear.carcass_capacity / 1000:.1f} kJ/K",
                      "derived: tread-rubber properties (Mousavi and Sandu 2020) and stand-in layer thicknesses"),
        ParameterNote("Rolling heat", f"{rolling:.3f} × load × speed, all of it into the tyre",
                      "the rolling-resistance stand-in of the Acceleration tab"),
        ParameterNote("Cooling by the air", "Churchill–Bernstein correlation, tyre as a cylinder in the riding wind",
                      "Incropera eq. 7.54; air properties from the Engineering ToolBox and the ISA"),
        ParameterNote("Cooling by the road", f"contact conduction through {road['real_contact_share']:.0%} of the footprint, "
                                             f"road effusivity {road_e:.0f} W s½/m² K",
                      "two semi-infinite bodies touching for the contact time; asphalt properties and the real-contact "
                      "share are stand-ins"),
        ParameterNote("Grip window", f"full grip {window.window_low:g}–{window.window_high:g} °C at the tread surface, "
                                     f"{window.cold_share:.0%} at {window.cold_temp:g} °C",
                      "stand-in for road and adventure tyres; no maker publishes these curves"),
    ]
    return ThermalSetup(front, rear, loads, window, styles, tyre), notes
