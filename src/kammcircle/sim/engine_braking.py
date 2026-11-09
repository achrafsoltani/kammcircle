"""Engine braking: a stop with the clutch home in a chosen gear and the throttle shut.

Until the rider shuts the throttle, at a set time or at the first touch of a brake, the throttle holds the speed and
the engine neither drives nor brakes. Then the engine's closed-throttle drag (friction and pumping) slows the rear wheel
through the gearing, and the engine's rotating parts add their inertia to the wheel's. If the chosen gear would
over-rev the engine at that speed,
the rider holds the clutch in until the engine can take it. The rider pulls the clutch in again when the engine falls
to the declutch speed, before it stalls. The suspended model carries everything else (section 11 of docs/physics.md).
"""

from __future__ import annotations

import math

from .acceleration import RPM, Powertrain
from .braking import BrakingParameters
from .suspension import SuspendedBrakingSim, SuspensionParameters

ORDINALS = ("1st", "2nd", "3rd", "4th", "5th", "6th", "7th")


class EngineBrakingSim(SuspendedBrakingSim):
    def __init__(self, params: BrakingParameters, susp: SuspensionParameters, powertrain: Powertrain, gear: int,
                 speed_kmh: float, *, declutch_rpm: float, throttle_off_at: float = 0.0, **kwargs) -> None:
        self.powertrain = powertrain
        powertrain.gear = gear
        powertrain.clutch_engaged = False
        powertrain.shift_timer = 0.0
        powertrain.rpm = powertrain.engine.idle_rpm
        self.declutch_rpm = declutch_rpm
        self.throttle_off_at = throttle_off_at
        self.engine_state = "cruising"  # cruising → waiting (clutch held in) → engaged → declutched
        self.engine_work = 0.0  # J taken out of the motion by the engine and drivetrain
        self.peak_engine_torque = 0.0  # N m at the rear wheel
        super().__init__(params, susp, speed_kmh, **kwargs)
        self.kinetic_energy = 0.5 * params.mass * self.v ** 2  # reset when the throttle shuts

    @property
    def gear_name(self) -> str:
        return ORDINALS[self.powertrain.gear - 1]

    def _drive_torque(self, dt: float) -> float:
        pt = self.powertrain
        ratio = pt.gearbox.overall(pt.gear)
        rpm = self.wr * ratio / RPM
        if self.engine_state == "cruising":
            if self.t < self.throttle_off_at - 1e-9 and self.brake_start is None:
                pt.rpm = min(rpm, pt.engine.limit_rpm)
                return 0.0
            self.engine_state = "waiting"
            self.kinetic_energy = 0.5 * self.p.mass * self.v ** 2
            if rpm >= pt.engine.limit_rpm:
                self.events.append((self.t, f"Throttle shut; {self.gear_name} gear would over-rev the engine at "
                                            f"{self.v * 3.6:.0f} km/h, so the rider holds the clutch in until it can"))
        if self.engine_state == "waiting" and rpm < pt.engine.limit_rpm:
            self.engine_state = "engaged"
            pt.clutch_engaged = True
            self.events.append((self.t, f"Throttle shut, clutch out in {self.gear_name} at {self.v * 3.6:.0f} km/h, "
                                        f"{rpm:.0f} rpm: engine braking"))
        if self.engine_state == "engaged" and rpm <= self.declutch_rpm:
            self.engine_state = "declutched"
            pt.clutch_engaged = False
            self.events.append((self.t, f"Clutch in at {rpm:.0f} rpm ({self.v * 3.6:.0f} km/h), before the engine "
                                        "stalls"))
        if self.engine_state != "engaged":
            pt.rpm = pt.engine.idle_rpm
            return 0.0
        pt.rpm = rpm
        torque = pt.at_wheel(-pt.engine.drag_torque(rpm), ratio)
        self.engine_work += -torque * self.wr * dt
        self.peak_engine_torque = max(self.peak_engine_torque, -torque)
        return torque

    def _rear_inertia(self) -> float:
        return self.p.rear_wheel_inertia + self.powertrain.reflected_inertia()

    @property
    def engine_share(self) -> float:
        """Share of the starting kinetic energy that the engine took out."""
        return self.engine_work / self.kinetic_energy if self.kinetic_energy > 0 else 0.0


def over_revs(powertrain: Powertrain, gear: int, speed_kmh: float, rear_radius: float) -> bool:
    return speed_kmh / 3.6 / rear_radius * powertrain.gearbox.overall(gear) / RPM >= powertrain.engine.limit_rpm


def coast_deceleration_g(params: BrakingParameters, powertrain: Powertrain, gear: int, speed_kmh: float,
                         g: float = 9.81) -> float:
    """Quasi-static engine-braking deceleration in a gear at a speed, ignoring drag and rolling resistance: the
    wheel torque over the radius, over the mass and the inertia the rear wheel and the engine add."""
    ratio = powertrain.gearbox.overall(gear)
    rpm = speed_kmh / 3.6 / params.rear_radius * ratio / RPM
    if rpm >= powertrain.engine.limit_rpm:
        return math.nan
    force = -powertrain.at_wheel(-powertrain.engine.drag_torque(rpm), ratio) / params.rear_radius
    inertia = params.front_wheel_inertia / params.front_radius ** 2 + (
        params.rear_wheel_inertia + powertrain.engine.inertia * ratio ** 2) / params.rear_radius ** 2
    return force / (params.mass + inertia) / g
