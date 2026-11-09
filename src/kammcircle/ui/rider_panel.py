"""Rider and bike: the user's own variables, the footpeg clearance angle, and the bike's sourced data."""

from __future__ import annotations

import html

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import catalogue
from .. import physics as P
from ..rider import RiderSetup
from .fields import ResultCard, note_label

FIELDS = (
    ("rider_mass_kg", "Rider mass, in gear", "kg", 30, 200, 1, 0),
    ("rider_cog_height_mm", "Rider CoG height", "mm", 500, 1600, 10, 0),
    ("rider_cog_ahead_mm", "Rider CoG ahead of the rear axle", "mm", 200, 1400, 10, 0),
    ("bike_cog_height_mm", "Bike CoG height", "mm", 300, 1000, 10, 0),
    ("bike_front_weight_pct", "Bike's weight on the front wheel", "%", 30, 70, 0.5, 1),
    ("front_sag_pct", "Front sag, rider aboard", "% of travel", 10, 50, 1, 0),
    ("rear_sag_pct", "Rear sag, rider aboard", "% of travel", 10, 50, 1, 0),
    ("tyre_crown_radius_mm", "Tyre crown radius", "mm", 0, 120, 1, 0),
    ("pillion_mass_kg", "Pillion mass, in gear", "kg", 0, 150, 1, 0),
    ("pillion_cog_height_mm", "Pillion CoG height", "mm", 500, 1700, 10, 0),
    ("pillion_cog_ahead_mm", "Pillion CoG ahead of the rear axle", "mm", -300, 1200, 10, 0),
    ("luggage_mass_kg", "Luggage mass", "kg", 0, 100, 1, 0),
    ("luggage_cog_height_mm", "Luggage CoG height", "mm", 200, 1500, 10, 0),
    ("luggage_cog_ahead_mm", "Luggage CoG ahead of the rear axle (− behind)", "mm", -600, 1200, 10, 0),
    ("peg_height_mm", "Footpeg tip height", "mm", 0, 600, 1, 0),
    ("peg_lateral_mm", "Footpeg tip lateral offset", "mm", 0, 600, 1, 0),
)


class RiderPanel(QWidget):
    setupChanged = Signal(object)

    def __init__(self, setup: RiderSetup, bike: catalogue.Bike, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setup = setup
        self.bike = bike
        self.spins: dict[str, QDoubleSpinBox] = {}
        self.labels: dict[str, QLabel] = {}

        variables = QGroupBox("Your rider and bike")
        form = QFormLayout(variables)
        for name, label, unit, low, high, step, decimals in FIELDS:
            spin = QDoubleSpinBox()
            spin.setDecimals(decimals)
            spin.setRange(low, high)
            spin.setSingleStep(step)
            spin.setSuffix(f" {unit}")
            if name.startswith("peg_"):
                spin.setSpecialValueText("not measured")
            elif name in ("pillion_mass_kg", "luggage_mass_kg"):
                spin.setSpecialValueText("none")
            spin.setValue(getattr(setup, name))
            spin.valueChanged.connect(self._edited)
            self.spins[name] = spin
            self.labels[name] = QLabel(label)
            form.addRow(self.labels[name], spin)

        reset = QPushButton("Reset to the example values")
        reset.clicked.connect(self.reset)
        self.c_clearance = ResultCard("Footpeg clearance lean")
        row = QHBoxLayout()
        row.addWidget(self.c_clearance, 1)
        row.addWidget(reset)

        left = QVBoxLayout()
        left.addWidget(variables)
        left.addLayout(row)
        left.addWidget(note_label(
            "Values marked “example” are placeholders, not data about any real rider or bike: Royal Enfield publishes "
            "no centre-of-gravity heights and no lean angles. Measure the footpeg tip's height and its lateral distance "
            "from the tyre centreline with the rider aboard and the bike upright; the clearance lean is atan(h ÷ w), "
            "a few degrees low because tyre width is ignored. The crown radius is about half the tyre's section width. "
            "The bike's weight split is used by the braking simulation: when it is left at the example, a measured "
            "figure from the catalogue is used if one exists. These values are saved for your user account only."
        ))
        left.addStretch(1)

        self.data = QTextBrowser()
        self.data.setOpenExternalLinks(True)
        right = QVBoxLayout()
        right.addWidget(QLabel("Catalogue data for the selected bike"))
        right.addWidget(self.data, 1)

        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addLayout(right, 1)
        self._refresh()

    def set_bike(self, bike: catalogue.Bike) -> None:
        self.bike = bike
        self._refresh()

    def reset(self) -> None:
        self.setup = RiderSetup()
        for name, spin in self.spins.items():
            with QSignalBlocker(spin):
                spin.setValue(getattr(self.setup, name))
        self._refresh()
        self.setupChanged.emit(self.setup)

    def _edited(self) -> None:
        self.setup = RiderSetup(**{name: spin.value() for name, spin in self.spins.items()})
        self._refresh()
        self.setupChanged.emit(self.setup)

    def _refresh(self) -> None:
        for name, label, *_ in FIELDS:
            example = (self.setup.is_example(name) and not name.startswith("peg_")
                       and name not in ("pillion_mass_kg", "luggage_mass_kg"))
            self.labels[name].setText(f"{label} (example)" if example else label)
        if self.setup.pegs_measured:
            angle = P.clearance_angle_deg(self.setup.peg_height_mm, self.setup.peg_lateral_mm)
            self.c_clearance.set(f"{angle:.1f}°")
        else:
            self.c_clearance.set("measure the footpeg")
        self.data.setHtml(bike_data_html(self.bike))


def _cite(ids: list[str]) -> str:
    known = catalogue.sources()
    links = []
    for source_id in ids:
        s = known.get(source_id)
        if s is None:
            links.append(html.escape(source_id))
        else:
            links.append(f'<a href="{html.escape(s.url)}" title="{html.escape(s.supports)}">{html.escape(source_id)}</a>')
    return ", ".join(links)


def bike_data_html(bike: catalogue.Bike) -> str:
    raw = bike.raw
    chassis, wheels = raw["chassis"], raw["wheels"]
    derived = raw.get("derived", {})
    rows = [
        ("Wheelbase", f"{chassis['wheelbase_mm']} mm", chassis["status"], chassis["source"]),
        ("Ground clearance", f"{chassis['ground_clearance_mm']} mm", chassis["status"], chassis["source"]),
        ("Rake / trail", f"{chassis['rake_deg']}° / {chassis['trail_mm']} mm", chassis["status"], chassis["source"]),
        ("Tyres", f"{wheels['front_tyre']} · {wheels['rear_tyre']}", wheels["status"], wheels["source"]),
        ("Mass used", f"{bike.mass_kg:.0f} kg ({bike.mass_note})",
         (raw.get("kerb_weight_kg") or raw.get("weight_kg"))["status"],
         (raw.get("kerb_weight_kg") or raw.get("weight_kg"))["source"]),
    ]
    for key, label in (("front_tyre_radius_mm", "Front tyre radius"), ("rear_tyre_radius_mm", "Rear tyre radius"),
                       ("fork_offset_mm", "Fork offset")):
        if key in derived:
            rows.append((label, f"{derived[key]['value']} mm = {derived[key]['formula']}", "derived", []))
    split = raw.get("front_weight_share") or derived.get("front_weight_share")
    if split is not None:
        value = "not published" if split.get("value") is None else f"{split['value'] * 100:.1f} % on the front ({split['formula']})"
        rows.append(("Weight split", value, split["status"], split.get("source", [])))
    lean = raw["lean_angle_deg"]
    rows.append(("Lean angle", "not published", lean["status"], []))

    body = "".join(
        f"<tr><td>{html.escape(label)}</td><td>{html.escape(value)}</td><td><i>{html.escape(status)}</i></td>"
        f"<td>{_cite(list(ids))}</td></tr>"
        for label, value, status, ids in rows
    )
    notes = " ".join(html.escape(n) for n in (chassis.get("note"), lean.get("note")) if n)
    return (
        f"<h3>{html.escape(bike.name)}</h3>"
        "<table cellspacing='0' cellpadding='4'><tr><th align='left'>Figure</th><th align='left'>Value</th>"
        f"<th align='left'>Status</th><th align='left'>Sources</th></tr>{body}</table>"
        f"<p>{notes}</p>"
        "<p><i>verified</i>: read from the cited source · <i>derived</i>: computed from verified figures · "
        "<i>unpublished</i>: the manufacturer gives no figure.</p>"
    )
