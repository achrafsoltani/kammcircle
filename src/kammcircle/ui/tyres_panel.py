"""Tyres: choose what is fitted (it feeds the simulation), browse what exists in the bike's sizes and what is on sale
in Morocco, and rank front-and-rear pairs for your riding."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import advice, catalogue
from ..rider import RiderSetup
from ..sim.parameters import G, static_wheel_loads
from .fields import SliderField, note_label

COLUMNS = ("Wheel", "Tyre", "Road / off-road", "Load", "Speed", "Type", "Design Ø", "In Morocco")


def _class_text(listing: catalogue.TyreListing) -> str:
    split = listing.product.road_offroad_pct
    return "not published" if split is None else f"{split[0]} / {split[1]}"


def _morocco_text(listing: catalogue.TyreListing) -> str:
    if not listing.offers:
        return "not seen"
    parts = []
    for o in listing.offers:
        stock = {True: "in stock", False: "out of stock", None: "listed"}[o.in_stock]
        price = f"{o.price_mad:.0f} DH" if o.price_mad is not None else "no price"
        parts.append(f"{o.retailer}: {price}, {stock} ({o.checked})")
    return "; ".join(parts)


class TyresPanel(QWidget):
    tyresChanged = Signal(object)

    def __init__(self, bike: catalogue.Bike, setup: RiderSetup, choice: catalogue.TyreChoice,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bike, self.setup, self.choice = bike, setup, choice

        fitted = QGroupBox("Fitted to your motorcycle (used by the simulation)")
        form = QFormLayout(fitted)
        self.front_box, self.rear_box = QComboBox(), QComboBox()
        self.front_info, self.rear_info = QLabel(), QLabel()
        for label in (self.front_info, self.rear_info):
            label.setTextFormat(Qt.TextFormat.RichText)
        form.addRow("Front", self.front_box)
        form.addRow("", self.front_info)
        form.addRow("Rear", self.rear_box)
        form.addRow("", self.rear_info)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)

        best = QGroupBox("Best fit for your riding")
        self.unpaved = SliderField("Unpaved riding", 0, 100, 5, 20, "%")
        self.stock_only = QCheckBox("Only tyres seen on sale in Morocco")
        self.keep_ratings = QCheckBox("Keep at least the original load and speed ratings")
        self.keep_ratings.setChecked(True)
        self.ranking = QTableWidget(0, 4)
        self.ranking.setHorizontalHeaderLabels(("Front", "Rear", "Score", "Why"))
        self.ranking.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ranking.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.ranking.verticalHeader().setVisible(False)
        rheader = self.ranking.horizontalHeader()
        rheader.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        rheader.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.ranking.setWordWrap(True)
        self.fit_button = QPushButton("Fit the selected pair")
        self.excluded = QTextBrowser()
        self.excluded.setMaximumHeight(64)
        options = QHBoxLayout()
        options.addWidget(self.stock_only)
        options.addWidget(self.keep_ratings)
        options.addStretch(1)
        options.addWidget(self.fit_button)
        best_layout = QVBoxLayout(best)
        best_layout.addWidget(self.unpaved)
        best_layout.addLayout(options)
        best_layout.addWidget(self.ranking, 1)
        best_layout.addWidget(self.excluded)
        best_layout.addWidget(note_label(
            "The ranking matches each tyre's published road/off-road split to your share of unpaved riding, keeps "
            "matched pairs together, and applies the load and speed ratings and, if asked, Moroccan availability. No "
            "maker publishes grip curves, so it does not rank tyres by braking or cornering grip; the simulation uses "
            "one tyre curve for all of them and takes only their size from the tyre you fit."
        ))

        layout = QVBoxLayout(self)
        fitted.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        catalogue_box = QGroupBox("Tyres in your motorcycle's sizes")
        cat_layout = QVBoxLayout(catalogue_box)
        cat_layout.addWidget(self.table)
        layout.addWidget(fitted)
        layout.addWidget(catalogue_box, 3)
        layout.addWidget(best, 4)

        self.front_box.currentIndexChanged.connect(self._choice_edited)
        self.rear_box.currentIndexChanged.connect(self._choice_edited)
        self.unpaved.valueChanged.connect(self._rank)
        self.stock_only.toggled.connect(self._rank)
        self.keep_ratings.toggled.connect(self._rank)
        self.fit_button.clicked.connect(self._fit_selected)
        self.set_bike(bike, choice)

    # ─── state ───────────────────────────────────────────────────────────────

    def set_bike(self, bike: catalogue.Bike, choice: catalogue.TyreChoice) -> None:
        self.bike, self.choice = bike, choice
        for box, size, position, current in ((self.front_box, bike.front_tyre, "front", choice.front),
                                             (self.rear_box, bike.rear_tyre, "rear", choice.rear)):
            box.blockSignals(True)
            box.clear()
            for listing in catalogue.listings_for(size, position):
                box.addItem(listing.name, listing.id)
            box.setCurrentIndex(max(0, box.findData(current.id)))
            box.blockSignals(False)
        self._fill_table()
        self._show_choice()
        self._rank()

    def set_setup(self, setup: RiderSetup) -> None:
        self.setup = setup
        self._show_choice()
        self._rank()

    def _choice_edited(self) -> None:
        self.choice = catalogue.TyreChoice(catalogue.tyre_listing(self.front_box.currentData()),
                                           catalogue.tyre_listing(self.rear_box.currentData()))
        self._show_choice()
        self.tyresChanged.emit(self.choice)

    def fit(self, front_id: str, rear_id: str) -> None:
        self.front_box.setCurrentIndex(self.front_box.findData(front_id))
        self.rear_box.setCurrentIndex(self.rear_box.findData(rear_id))

    def _fit_selected(self) -> None:
        row = max(0, self.ranking.currentRow())
        item = self.ranking.item(row, 0)
        if item is not None:
            front_id, rear_id = item.data(Qt.ItemDataRole.UserRole)
            self.fit(front_id, rear_id)

    # ─── outputs ─────────────────────────────────────────────────────────────

    def _fill_table(self) -> None:
        rows = ([("front", t) for t in catalogue.listings_for(self.bike.front_tyre, "front")]
                + [("rear", t) for t in catalogue.listings_for(self.bike.rear_tyre, "rear")])
        self.table.setRowCount(len(rows))
        for r, (wheel, t) in enumerate(rows):
            values = (wheel, f"{t.product.name} {t.size}", _class_text(t),
                      f"{t.li} = {t.load_kg:.0f} kg" if t.load_kg else "not stated",
                      f"{t.ss} = {t.speed_kmh:.0f} km/h" if t.speed_kmh else "not stated",
                      t.type or "—", f"{t.design[1]:.0f} mm" if t.design else "nominal", _morocco_text(t))
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(t.product.note)
                self.table.setItem(r, c, item)

    def _show_choice(self) -> None:
        front_n, rear_n = static_wheel_loads(self.bike, self.setup)
        oe = catalogue.original_tyres(self.bike)
        for label, listing, load_n, original in ((self.front_info, self.choice.front, front_n, oe.front),
                                                 (self.rear_info, self.choice.rear, rear_n, oe.rear)):
            basis = "maker's design diameter" if listing.design else "nominal size"
            lines = [f"radius {listing.radius_mm:.1f} mm ({basis}), crown radius {listing.crown_radius_mm:.0f} mm"]
            if listing.load_kg:
                ok = load_n / G <= listing.load_kg
                lines.append(f"carries {listing.load_kg:.0f} kg; your load at rest is {load_n / G:.0f} kg "
                             + ("✓" if ok else "<b style='color:#E24B4A'>over the rating</b>"))
            if listing.speed_kmh and original.speed_kmh:
                slower = listing.speed_kmh < original.speed_kmh
                lines.append(f"rated {listing.speed_kmh:.0f} km/h"
                             + (f" — <b style='color:#BA7517'>below the original {original.ss} "
                                f"({original.speed_kmh:.0f} km/h)</b>" if slower else ""))
            label.setText(html.escape(" · ").join(lines))

    def _rank(self) -> None:
        loads = static_wheel_loads(self.bike, self.setup)
        result = advice.rank_pairs(self.bike, self.unpaved.value(), in_stock_only=self.stock_only.isChecked(),
                                   keep_ratings=self.keep_ratings.isChecked(), static_loads_n=loads)
        pairs = result.pairs[:12]
        self.ranking.setRowCount(len(pairs))
        for r, pair in enumerate(pairs):
            values = (pair.front.name, pair.rear.name, f"{pair.score:.0f}", "; ".join(pair.reasons))
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, (pair.front.id, pair.rear.id))
                self.ranking.setItem(r, c, item)
        if pairs:
            self.ranking.selectRow(0)
        self.fit_button.setEnabled(bool(pairs))
        text = "" if pairs else "<b>No complete pair passes these filters.</b> "
        if result.excluded:
            text += "Left out: " + "; ".join(html.escape(e) for e in result.excluded)
        self.excluded.setHtml(text)
