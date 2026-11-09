"""Build simulation parameters from the catalogue bike, the rider's variables and the packaged model data,
keeping a note of where every number comes from so that the app can show it."""

from __future__ import annotations

from dataclasses import dataclass

from .. import catalogue
from ..rider import RiderSetup
from .braking import ABSSettings, BrakingParameters
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
