"""Build simulation parameters from the catalogue bike, the rider's variables and the packaged model data,
keeping a note of where every number comes from so that the app can show it."""

from __future__ import annotations

from dataclasses import dataclass

from .. import catalogue
from ..rider import RiderSetup
from .braking import ABSSettings, BrakingParameters
from .suspension import SuspensionParameters
from .tyre import LongitudinalTyre


@dataclass(frozen=True)
class ParameterNote:
    name: str
    value: str
    basis: str


def braking_parameters(
    bike: catalogue.Bike, setup: RiderSetup, mu: float
) -> tuple[BrakingParameters, list[ParameterNote]]:
    data = catalogue.load_json("sim-parameters.json")
    g = 9.81
    notes: list[ParameterNote] = []

    def note(name: str, value: str, basis: str) -> None:
        notes.append(ParameterNote(name, value, basis))

    wheelbase = bike.wheelbase_mm / 1000
    front_r = bike.front_wheel_radius_mm / 1000
    rear_r = bike.rear_wheel_radius_mm / 1000
    note("Wheelbase", f"{bike.wheelbase_mm:.0f} mm", "manufacturer or test figure (catalogue)")
    note("Wheel radii", f"{front_r * 1000:.0f} / {rear_r * 1000:.0f} mm", "from the tyre size codes (derived)")

    measured = bike.front_weight_share
    if not setup.is_example("bike_front_weight_pct"):
        share, basis = setup.bike_front_weight_pct / 100, "your value"
    elif measured is not None:
        share, basis = measured, "measured axle weights (catalogue, derived)"
    else:
        share, basis = setup.bike_front_weight_pct / 100, "example: no published weight split"
    note("Motorcycle's weight on the front wheel", f"{share * 100:.1f} %", basis)

    def mine(name: str) -> str:
        return "example value" if setup.is_example(name) else "your value"

    m_bike, m_rider = bike.mass_kg, setup.rider_mass_kg
    note("Motorcycle mass", f"{m_bike:.0f} kg", bike.mass_note)
    note("Rider mass", f"{m_rider:.0f} kg", mine("rider_mass_kg"))
    x_bike, h_bike = share * wheelbase, setup.bike_cog_height_mm / 1000
    x_rider, h_rider = setup.rider_cog_ahead_mm / 1000, setup.rider_cog_height_mm / 1000
    note("Motorcycle CoG height", f"{h_bike * 1000:.0f} mm", mine("bike_cog_height_mm"))
    note("Rider CoG height / ahead of rear axle", f"{h_rider * 1000:.0f} / {x_rider * 1000:.0f} mm",
         "example values" if setup.is_example("rider_cog_height_mm") and setup.is_example("rider_cog_ahead_mm")
         else "your values")

    mass = m_bike + m_rider
    b = (m_bike * x_bike + m_rider * x_rider) / mass
    h = (m_bike * h_bike + m_rider * h_rider) / mass

    inertia = data["pitch_inertia_kgm2"]
    pitch = (
        inertia["bike_own"] + m_bike * ((x_bike - b) ** 2 + (h_bike - h) ** 2)
        + inertia["rider_upper_body"] + m_rider * ((x_rider - b) ** 2 + (h_rider - h) ** 2)
    )
    note("Pitch inertia about the combined CoG", f"{pitch:.1f} kg m²",
         "stand-in: GSX-R1000 body inertias (Sharp et al. 2004) plus the parallel-axis terms")
    spin = data["wheel_spin_inertia_kgm2"]
    note("Wheel spin inertias", f"{spin['front']} / {spin['rear']} kg m²", "stand-in: GSX-R1000 (Sharp et al. 2004)")

    tyre = LongitudinalTyre.from_data(data["tyre_longitudinal"]).for_surface(mu)
    note("Tyre braking curve", f"peak μ {mu:.2f} at the nominal load",
         "Magic Formula fit to a 160/70 ZR17 tyre (Sharp et al. 2004), scaled to the surface")

    capacity = data["brake_capacity"]
    k = capacity["lock_margin"] * capacity["reference_mu"]
    front_max = k * mass * g * front_r
    rear_max = k * mass * g * (1 - b / wheelbase) * rear_r
    note("Brake torque at full lever / pedal", f"{front_max:.0f} / {rear_max:.0f} N m",
         "modelling choice: enough to lock either wheel on dry asphalt")

    a = data["abs"]
    settings = ABSSettings(a["release_factor"], a["reapply_factor"], a["release_rate_per_s"], a["apply_rate_per_s"])
    note("ABS", "slip-band controller around the tyre's peak slip", "generic model, not Royal Enfield's")

    params = BrakingParameters(
        wheelbase=wheelbase, front_radius=front_r, rear_radius=rear_r, mass=mass, cog_ahead_of_rear=b, cog_height=h,
        pitch_inertia=pitch, front_wheel_inertia=spin["front"], rear_wheel_inertia=spin["rear"], tyre=tyre,
        front_brake_max=front_max, rear_brake_max=rear_max, abs_settings=settings, g=g,
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
    notes.append(ParameterNote("Rider sag", f"{setup.front_sag_pct:.0f} % / {setup.rear_sag_pct:.0f} % of travel", sag_basis))
    unsprung = data["unsprung_mass_kg"]
    notes.append(ParameterNote("Unsprung masses", f"{unsprung['front']} / {unsprung['rear']} kg",
                               "stand-in: GSX-R1000 (Sharp et al. 2004)"))
    tyre_k = data["tyre_radial_stiffness_N_per_m"]
    notes.append(ParameterNote("Tyre radial stiffness", f"{tyre_k['front'] / 1000:.0f} / {tyre_k['rear'] / 1000:.0f} kN/m",
                               "stand-in: sport tyres (Sharp et al. 2004)"))
    model = data["suspension_model"]
    notes.append(ParameterNote("Suspension damping", f"{model['damping_ratio']:.2f} of critical",
                               "modelling choice: no published damping data"))
    share = (setup.bike_front_weight_pct / 100 if not setup.is_example("bike_front_weight_pct")
             else bike.front_weight_share if bike.front_weight_share is not None else setup.bike_front_weight_pct / 100)
    inertia = data["pitch_inertia_kgm2"]
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
    )
    return params, notes
