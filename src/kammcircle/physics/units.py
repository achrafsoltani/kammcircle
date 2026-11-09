"""Units and constants shared by the physics modules.

Conventions used throughout ``kammcircle.physics``:

* mm for chassis and tyre geometry; m, m/s and kg for dynamics; km/h only at the UI edge.
* The public API takes and returns **degrees**; radians are used only inside functions.
"""

from __future__ import annotations

import math

G = 9.81
"""Gravitational acceleration in m/s², rounded as in the reference values the tests anchor on."""


def deg2rad(degrees: float) -> float:
    return math.radians(degrees)


def rad2deg(radians: float) -> float:
    return math.degrees(radians)


def kmh_to_ms(speed_kmh: float) -> float:
    return speed_kmh / 3.6


def ms_to_kmh(speed_ms: float) -> float:
    return speed_ms * 3.6
