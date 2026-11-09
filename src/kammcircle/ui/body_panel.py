"""Body position: how far the bike leans when the rider moves inside or outside its plane."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QGridLayout, QVBoxLayout, QWidget

from .. import catalogue
from .. import physics as P
from ..rider import RiderSetup
from .fields import ResultCard, SliderField, note_label
from .views import BodyPositionView


class BodyPositionPanel(QWidget):
    def __init__(self, setup: RiderSetup, bike: catalogue.Bike, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setup = setup
        self.bike = bike
        self._cornering_lean = 30.0

        self.follow = QCheckBox("Take the combined lean from the Cornering and grip tab")
        self.follow.setChecked(True)
        self.combined = SliderField("Combined lean", 0, 60, 0.5, 30, "°", decimals=1)
        self.offset = SliderField("Rider offset", -300, 300, 5, 0, "mm")
        self.offset.setToolTip("Positive: the rider's centre of gravity moves to the inside of the turn (tarmac). "
                               "Negative: to the outside, standing on the outside peg (gravel).")

        self.c_bike = ResultCard("Bike lean")
        self.c_diff = ResultCard("Bike minus combined")
        self.c_cog = ResultCard("Combined CoG height")
        cards = QGridLayout()
        for i, card in enumerate((self.c_bike, self.c_diff, self.c_cog)):
            cards.addWidget(card, 0, i)

        self.view = BodyPositionView()
        self.examples = note_label("")
        layout = QVBoxLayout(self)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.follow)
        layout.addWidget(self.combined)
        layout.addWidget(self.offset)
        layout.addLayout(cards)
        layout.addWidget(self.examples)
        layout.addWidget(note_label(
            "The corner fixes the combined lean. Moving the rider's centre of gravity by s changes only the bike's "
            "lean: φ_bike = φ_combined − atan(m_r·s ÷ (m_b·h_b + m_r·h_r)). Hanging inside lets the bike lean less "
            "(more tyre and clearance margin); standing on the outside peg makes the bike lean more under an upright rider."
        ))

        self.follow.toggled.connect(self._follow_toggled)
        self.combined.valueChanged.connect(self.refresh)
        self.offset.valueChanged.connect(self.refresh)
        self._follow_toggled(True)

    def set_setup(self, setup: RiderSetup) -> None:
        self.setup = setup
        self.refresh()

    def set_bike(self, bike: catalogue.Bike) -> None:
        self.bike = bike
        self.refresh()

    def set_cornering_lean(self, lean_deg: float) -> None:
        self._cornering_lean = lean_deg
        if self.follow.isChecked():
            self.combined.setValue(round(lean_deg * 2) / 2)
            self.refresh()

    def _follow_toggled(self, on: bool) -> None:
        self.combined.setEnabled(not on)
        if on:
            self.combined.setValue(round(self._cornering_lean * 2) / 2)
        self.refresh()

    def refresh(self) -> None:
        s = self.setup
        combined = self._cornering_lean if self.follow.isChecked() else self.combined.value()
        bike_lean = P.bike_lean_for_rider_offset_deg(
            combined_lean_deg=combined, bike_mass_kg=self.bike.mass_kg, bike_cog_height_mm=s.bike_cog_height_mm,
            rider_mass_kg=s.rider_mass_kg, rider_cog_height_mm=s.rider_cog_height_mm,
            rider_offset_mm=self.offset.value(),
        )
        cog = P.combined_cog_height_mm(self.bike.mass_kg, s.bike_cog_height_mm, s.rider_mass_kg, s.rider_cog_height_mm)
        self.c_bike.set(f"{bike_lean:.1f}°")
        self.c_diff.set(f"{bike_lean - combined:+.1f}°")
        self.c_cog.set(f"{cog:.0f} mm")
        examples = [label for name, label in (
            ("rider_mass_kg", "rider mass"), ("rider_cog_height_mm", "rider CoG height"),
            ("bike_cog_height_mm", "bike CoG height"),
        ) if s.is_example(name)]
        self.examples.setText(
            f"Bike mass: {self.bike.mass_kg:.0f} kg, {self.bike.mass_note}. "
            + (f"Example values in use for {', '.join(examples)}: set your own in the Rider and bike tab."
               if examples else "Using your rider and bike values.")
        )
        self.view.set_state(
            combined_lean_deg=combined, bike_lean_deg=bike_lean, bike_cog_height_mm=s.bike_cog_height_mm,
            rider_cog_height_mm=s.rider_cog_height_mm, rider_offset_mm=self.offset.value(),
            combined_cog_height_mm=cog,
        )
