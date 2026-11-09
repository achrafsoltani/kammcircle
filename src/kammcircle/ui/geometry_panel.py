"""Steering geometry and lowering: rake, trail and ground clearance after dropping either end."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from .. import catalogue
from .. import physics as P
from .fields import ResultCard, SliderField, note_label
from .views import GeometryView

PRESETS = (("Stock", 0, 0), ("Rear −30 mm", 30, 0), ("Front −30 mm", 0, 30), ("Both −30 mm", 30, 30))


class GeometryPanel(QWidget):
    def __init__(self, bike: catalogue.Bike, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bike = bike

        self.rear = SliderField("Rear-axle drop", 0, 50, 1, 0, "mm")
        self.front = SliderField("Front drop", 0, 50, 1, 0, "mm")
        presets = QHBoxLayout()
        for name, rear, front in PRESETS:
            button = QPushButton(name)
            button.clicked.connect(lambda _=False, r=rear, f=front: self._preset(r, f))
            presets.addWidget(button)
        presets.addStretch(1)

        self.tyre = QLineEdit(bike.front_tyre)
        self.tyre.setToolTip("Front tyre size code, for example 90/90-21. Changing it changes the wheel radius and the trail.")
        tyre_row = QHBoxLayout()
        tyre_label = QLabel("Front tyre")
        tyre_label.setMinimumWidth(120)
        tyre_row.addWidget(tyre_label)
        tyre_row.addWidget(self.tyre, 1)
        self.tyre_status = QLabel()
        tyre_row.addWidget(self.tyre_status)

        self.c_rake = ResultCard("Rake")
        self.c_trail = ResultCard("Trail")
        self.c_clear = ResultCard("Ground clearance (≈)")
        self.c_pitch = ResultCard("Chassis pitch")
        self.c_offset = ResultCard("Fork offset (back-solved)")
        self.c_radius = ResultCard("Front wheel radius")
        cards = QGridLayout()
        for i, card in enumerate((self.c_rake, self.c_trail, self.c_clear, self.c_pitch, self.c_offset, self.c_radius)):
            cards.addWidget(card, i // 3, i % 3)

        self.feel = QLabel()
        self.feel.setWordWrap(True)
        self.view = GeometryView()
        layout = QVBoxLayout(self)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.rear)
        layout.addWidget(self.front)
        layout.addLayout(presets)
        layout.addLayout(tyre_row)
        layout.addLayout(cards)
        layout.addWidget(self.feel)
        layout.addWidget(note_label(
            "Model: pitch change = atan((rear drop − front drop) ÷ wheelbase); trail = (R·sin θ − d) ÷ cos θ, with the "
            "fork offset d back-solved from the published rake and trail. Clearance loss ≈ the mean of the two drops. "
            "Not modelled: a lowering link's change of leverage ratio (a softer rear), sag, and the difference between "
            "rear-axle drop and seat drop."
        ))

        self.rear.valueChanged.connect(self.refresh)
        self.front.valueChanged.connect(self.refresh)
        self.tyre.textChanged.connect(self.refresh)
        self.refresh()

    def set_bike(self, bike: catalogue.Bike) -> None:
        self.bike = bike
        self.tyre.setText(bike.front_tyre)
        self.refresh()

    def set_tyres(self, tyres: catalogue.TyreChoice) -> None:
        self.tyre.setText(tyres.front.size)

    def _preset(self, rear: float, front: float) -> None:
        self.rear.setValue(rear)
        self.front.setValue(front)

    def refresh(self) -> None:
        b = self.bike
        try:
            radius = P.tyre_radius_from_code(self.tyre.text())
            self.tyre_status.setText(f"R = {radius:.1f} mm")
        except ValueError:
            radius = b.front_wheel_radius_mm
            self.tyre_status.setText("unrecognised size: using the stock tyre")
        offset = b.fork_offset_mm
        result = P.lowering_geometry(
            rake_deg=b.rake_deg, wheel_radius_mm=radius, fork_offset_mm=offset, wheelbase_mm=b.wheelbase_mm,
            ground_clearance_mm=b.ground_clearance_mm, rear_drop_mm=self.rear.value(), front_drop_mm=self.front.value(),
        )
        self.c_rake.set(f"{result.rake_deg:.1f}°  (stock {b.rake_deg:g}°)")
        self.c_trail.set(f"{result.trail_mm:.0f} mm  (stock {b.trail_mm:g})")
        self.c_clear.set(f"{result.ground_clearance_mm:.0f} mm")
        self.c_pitch.set(f"{result.pitch_deg:+.2f}°")
        self.c_offset.set(f"{offset:.1f} mm")
        self.c_radius.set(f"{radius:.1f} mm")

        change = result.rake_deg - b.rake_deg
        if abs(change) < 0.25:
            feel = "Geometry close to stock: handling unchanged; only ground clearance changes."
        elif change > 0:
            feel = "More rake and trail: slower, heavier turn-in, more stable at speed, tends to run wide in corners."
        else:
            feel = "Less rake and trail: quicker, lighter turn-in, less stable at speed, more prone to headshake on bumps."
        if self.rear.value() > 0:
            feel += " A rear lowering link also makes the rear suspension softer."
        self.feel.setText(feel)

        self.view.set_state(
            stock_rake_deg=b.rake_deg, rake_deg=result.rake_deg, pitch_deg=result.pitch_deg, trail_mm=result.trail_mm,
            ground_clearance_mm=result.ground_clearance_mm, stock_ground_clearance_mm=b.ground_clearance_mm,
            front_drop_mm=self.front.value(), wheelbase_mm=b.wheelbase_mm, front_radius_mm=radius,
            rear_radius_mm=b.rear_wheel_radius_mm,
        )
