"""Cornering and grip: the lean a corner needs, the grip limit and the friction circle."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import catalogue
from .. import physics as P
from ..rider import RiderSetup
from .fields import ResultCard, SliderField, note_label
from .style import usage_colour
from .views import FrictionCircleView, LeanView

CUSTOM = "custom"


class CorneringPanel(QWidget):
    leanChanged = Signal(float)
    """Emits the ideal (combined) lean the corner needs, in degrees."""

    def __init__(self, setup: RiderSetup, bike: catalogue.Bike, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setup = setup
        self.bike = bike
        self.tyres = catalogue.original_tyres(bike)
        self.grip = (1.0, 1.0)  # share of a warm tyre's grip, front and rear (tyre temperature)

        self.speed = SliderField("Speed", 10, 200, 1, 60, "km/h")
        self.radius = SliderField("Corner radius", 5, 300, 1, 50, "m")
        self.surface = QComboBox()
        for s in catalogue.surfaces():
            self.surface.addItem(f"{s.label}  (μ {s.mu:.2f})", s.id)
        self.surface.addItem("Custom μ", CUSTOM)
        self.mu = SliderField("Grip μ", 0.10, 1.30, 0.01, 1.0, "", decimals=2)
        self.brake = SliderField("Braking", 0, 1.2, 0.01, 0, "g", decimals=2)
        self.tyre_width = QCheckBox("Correct the lean for tyre width (uses the rider and bike variables)")
        self.tyre_width.setChecked(True)

        surface_row = QHBoxLayout()
        surface_label = QLabel("Surface")
        surface_label.setMinimumWidth(120)
        surface_row.addWidget(surface_label)
        surface_row.addWidget(self.surface, 1)

        self.c_lat = ResultCard("Lateral acceleration")
        self.c_lean = ResultCard("Lean needed (ideal)")
        self.c_wheel = ResultCard("Lean needed (tyre width)")
        self.c_limit = ResultCard("Grip-limit lean")
        self.c_used = ResultCard("Grip used")
        self.c_vmax = ResultCard("Max speed, this corner")
        cards = QGridLayout()
        for i, card in enumerate((self.c_lat, self.c_lean, self.c_wheel, self.c_limit, self.c_used, self.c_vmax)):
            cards.addWidget(card, i // 3, i % 3)

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.lean_view = LeanView()
        self.circle_view = FrictionCircleView()
        views = QHBoxLayout()
        views.addWidget(self.lean_view, 3)
        views.addWidget(self.circle_view, 2)

        layout = QVBoxLayout(self)
        layout.addLayout(views, 1)
        for widget in (self.speed, self.radius):
            layout.addWidget(widget)
        layout.addLayout(surface_row)
        layout.addWidget(self.mu)
        layout.addWidget(self.brake)
        layout.addWidget(self.tyre_width)
        layout.addLayout(cards)
        layout.addWidget(self.message)
        layout.addWidget(note_label(
            "Model: steady speed, flat road. Lean = atan(v² ÷ g·r); grip used = √(lateral² + braking²) ÷ μ; "
            "grip-limit lean = atan(μ); max speed = √(√(μ² − b²)·g·r). The tyre-width correction is "
            "φ = φ0 + asin(t·sin φ0 ÷ (h − t)) with t the crown radius and h the combined centre-of-gravity height. "
            "μ presets come from data/surfaces.json; one μ per surface is a simplification."
        ))

        self.surface.currentIndexChanged.connect(self._surface_chosen)
        self.mu.valueChanged.connect(self._mu_moved)
        for widget in (self.speed, self.radius, self.brake):
            widget.valueChanged.connect(self.refresh)
        self.tyre_width.toggled.connect(self.refresh)
        self.refresh()

    def set_setup(self, setup: RiderSetup) -> None:
        self.setup = setup
        self.refresh()

    def set_bike(self, bike: catalogue.Bike) -> None:
        self.bike = bike
        self.tyres = catalogue.original_tyres(bike)
        self.refresh()

    def set_tyres(self, tyres: catalogue.TyreChoice) -> None:
        self.tyres = tyres
        self.refresh()

    def set_tyre_grip(self, front: float, rear: float) -> None:
        self.grip = (front, rear)
        self.refresh()

    def crown_radius_mm(self) -> float:
        """Your crown radius if you entered one, otherwise half the fitted rear tyre's section width."""
        if self.setup.is_example("tyre_crown_radius_mm"):
            return self.tyres.rear.crown_radius_mm
        return self.setup.tyre_crown_radius_mm

    def _surface_chosen(self) -> None:
        surface_id = self.surface.currentData()
        if surface_id != CUSTOM:
            mu = next(s.mu for s in catalogue.surfaces() if s.id == surface_id)
            with QSignalBlocker(self.mu):
                self.mu.setValue(mu)
        self.refresh()

    def _mu_moved(self) -> None:
        current = self.surface.currentData()
        if current != CUSTOM:
            preset = next(s.mu for s in catalogue.surfaces() if s.id == current)
            if abs(preset - self.mu.value()) > 1e-9:
                with QSignalBlocker(self.surface):
                    self.surface.setCurrentIndex(self.surface.findData(CUSTOM))
        self.refresh()

    def combined_cog_height_mm(self) -> float:
        return P.combined_cog_height_mm(
            self.bike.mass_kg, self.setup.bike_cog_height_mm, self.setup.rider_mass_kg, self.setup.rider_cog_height_mm
        )

    def refresh(self) -> None:
        kmh, r, brake = self.speed.value(), self.radius.value(), self.brake.value()
        mu = self.mu.value() * min(self.grip)  # tyres not yet warm grip less; the weaker one sets the limit
        lat = P.lateral_g(kmh, r)
        lean = P.lean_angle_deg(kmh, r)
        limit = P.max_lean_deg(mu)
        used = P.grip_usage(lat, brake, mu)
        vmax = P.max_corner_speed_kmh(r, mu, brake)
        colour = usage_colour(used)

        crown = self.crown_radius_mm() if self.tyre_width.isChecked() else 0.0
        cog = self.combined_cog_height_mm()
        try:
            wheel = P.lean_angle_with_tyre_deg(kmh, r, crown, cog)
        except ValueError:
            wheel = lean
            crown = 0.0

        self.c_lat.set(f"{lat:.2f} g")
        self.c_lean.set(f"{lean:.1f}°")
        self.c_wheel.set(f"{wheel:.1f}°" if crown > 0 else "off")
        self.c_limit.set(f"{limit:.1f}°")
        self.c_used.set(f"{used * 100:.0f} %", colour)
        self.c_vmax.set(f"{vmax:.0f} km/h")

        if used < 0.8:
            text = "Inside the grip circle with margin."
        elif used < 1.0:
            text = "Close to the limit: a bump, a painted line or a little more brake will push it over."
        else:
            text = f"Outside the grip circle: the tyres slide. The most this corner allows at this braking is {vmax:.0f} km/h."
        if min(self.grip) < 1.0:
            text += (f" Tyres not yet warm: the surface's μ {self.mu.value():.2f} is cut to {mu:.2f} "
                     f"({min(self.grip):.0%} of a warm tyre's grip).")
        self.message.setText(text)
        self.message.setStyleSheet(f"color: {colour.name()};")

        self.lean_view.set_state(
            effective_lean_deg=lean, wheel_lean_deg=wheel, limit_deg=limit, usage=used,
            crown_radius_mm=crown, cog_height_mm=cog,
        )
        self.circle_view.set_state(lat_g=lat, brake_g=brake, mu=mu)
        self.leanChanged.emit(lean)
