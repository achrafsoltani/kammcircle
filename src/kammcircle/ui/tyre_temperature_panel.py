"""Tyre temperature: a ride from a cold start, a minute a second or at once, with the tyres' temperatures and grip."""

from __future__ import annotations

import html
import math

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import catalogue
from ..rider import RiderSetup
from ..sim.parameters import slip_heat, thermal_parameters
from ..sim.tyre_thermal import GripWindow, WarmUpRun
from .charts import Series, StripChart
from .fields import ResultCard, SliderField, note_label
from .style import AMBER, CORAL, GREY, PURPLE, RED, TEAL, label_font

TIME_SCALE = 60.0  # a minute of riding per second on screen
STYLE_LABELS = {"gentle": "Gentle riding", "brisk": "Brisk riding", "hard": "Hard riding"}


class TyreTemperaturePanel(QWidget):
    def __init__(self, setup: RiderSetup, bike: catalogue.Bike, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setup, self.bike = setup, bike
        self.tyres = catalogue.original_tyres(bike)
        self.run: WarmUpRun | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.clock = QElapsedTimer()

        self.chart_surface = StripChart("Tread surface temperature (°C), which sets the grip", 0, 40, "", x_unit=" min")
        self.chart_inside = StripChart("Inside the tyre (°C): tread and carcass", 0, 40, "", x_unit=" min")
        self.chart_grip = StripChart("Grip, share of a warm tyre's", 0.5, 1.05, "", x_unit=" min")
        self.chart_curve = StripChart("Grip against tread-surface temperature", 0.4, 1.05, "", x_unit=" °C")
        self.charts = (self.chart_surface, self.chart_inside, self.chart_grip)
        grid = QGridLayout()
        for i, chart in enumerate((self.chart_surface, self.chart_inside, self.chart_grip, self.chart_curve)):
            grid.addWidget(chart, i // 2, i % 2)

        self.air = SliderField("Air temperature", -20, 45, 1, 5, "°C")
        self.road = SliderField("Road temperature", -20, 65, 1, 3, "°C")
        self.parked = QCheckBox("Tyres start at the air temperature (parked outside)")
        self.parked.setChecked(True)
        self.start_temp = SliderField("Tyres at the start", -20, 90, 1, 5, "°C")
        self.speed = SliderField("Speed", 10, 160, 1, 60, "km/h")
        self.style = QComboBox()
        self.length = SliderField("Ride length", 5, 90, 1, 30, "min")
        self.window_low = SliderField("Full grip from", 0, 120, 1, 30, "°C")
        self.window_high = SliderField("Full grip up to", 10, 150, 1, 60, "°C")
        self.cold_share = SliderField("Grip at 0 °C", 40, 100, 1, 80, "%")
        style_row = QHBoxLayout()
        label = QLabel("Riding")
        label.setMinimumWidth(120)
        style_row.addWidget(label)
        style_row.addWidget(self.style, 1)

        self.run_button = QPushButton("Ride (a minute a second)")
        self.instant_button = QPushButton("Instant result")
        self.reset_button = QPushButton("Reset")
        buttons = QHBoxLayout()
        for button in (self.run_button, self.instant_button, self.reset_button):
            buttons.addWidget(button)
        buttons.addStretch(1)

        controls = QGridLayout()
        left = (self.air, self.road, self.parked, self.start_temp, self.speed)
        right = (style_row, self.length, self.window_low, self.window_high, self.cold_share)
        for row, (a, b) in enumerate(zip(left, right)):
            controls.addWidget(a, row, 0)
            if isinstance(b, QHBoxLayout):
                controls.addLayout(b, row, 1)
            else:
                controls.addWidget(b, row, 1)
        controls.addLayout(buttons, len(left), 0, 1, 2)

        self.c_front = ResultCard("Front tyre in its window")
        self.c_rear = ResultCard("Rear tyre in its window")
        self.c_five = ResultCard("Grip after 5 min, front / rear")
        self.c_steady = ResultCard("Settles at, front / rear surface")
        cards = QGridLayout()
        for i, card in enumerate((self.c_front, self.c_rear, self.c_five, self.c_steady)):
            cards.addWidget(card, i // 2, i % 2)
        self.events = QTextBrowser()
        self.events.setMaximumHeight(110)
        self.events.setFont(label_font(self.events, 0.9))
        self.toggle = QToolButton()
        self.toggle.setText("Model parameters and where they come from")
        self.toggle.setCheckable(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.parameters = QTextBrowser()
        self.parameters.setVisible(False)
        self.parameters.setMaximumHeight(170)
        results = QVBoxLayout()
        results.addLayout(cards)
        results.addWidget(self.events)
        results.addWidget(self.toggle)
        results.addWidget(self.parameters)
        results.addStretch(1)

        bottom = QHBoxLayout()
        bottom.addLayout(controls, 3)
        bottom.addLayout(results, 2)
        layout = QVBoxLayout(self)
        layout.addLayout(grid, 3)
        layout.addLayout(bottom)
        layout.addWidget(note_label(
            "Model: each tyre is two heat stores, the tread and the carcass, warmed by rolling (the rubber's hysteresis "
            "turns the rolling-resistance work into heat) and by slip at the contact patch, and cooled by the riding wind "
            "and by the road it touches. The grip follows the tread surface's temperature through a working window that "
            "no maker publishes for road tyres: the window and the grip of a cold tyre are editable stand-ins. Constant "
            "speed; no rain, wear or pressure changes."
        ))

        self.parked.toggled.connect(self._parked_toggled)
        self.air.valueChanged.connect(self._air_moved)
        self.toggle.toggled.connect(self._toggle_parameters)
        self.run_button.clicked.connect(self.start)
        self.instant_button.clicked.connect(self.instant)
        self.reset_button.clicked.connect(self.reset)
        for field in (self.window_low, self.window_high, self.cold_share):
            field.valueChanged.connect(self._curve)
        self._parked_toggled(True)
        self._model_changed()
        self.reset()

    # ─── inputs ──────────────────────────────────────────────────────────────

    def set_setup(self, setup: RiderSetup) -> None:
        self.setup = setup
        self._model_changed()

    def set_bike(self, bike: catalogue.Bike) -> None:
        self.bike = bike
        self.tyres = catalogue.original_tyres(bike)
        self.reset()
        self._model_changed()

    def set_tyres(self, tyres: catalogue.TyreChoice) -> None:
        self.tyres = tyres
        self._model_changed()

    def _model_changed(self) -> None:
        self.thermal, notes = thermal_parameters(self.bike, self.setup, self.tyres)
        current = self.style.currentData() or "gentle"
        self.style.blockSignals(True)
        self.style.clear()
        for key, share in self.thermal.styles.items():
            self.style.addItem(f"{STYLE_LABELS.get(key, key.capitalize())} ({share:.0%} of the grip on average)", key)
        self.style.setCurrentIndex(max(0, self.style.findData(current)))
        self.style.blockSignals(False)
        rows = "".join(f"<tr><td>{html.escape(n.name)}</td><td><b>{html.escape(n.value)}</b></td>"
                       f"<td><i>{html.escape(n.basis)}</i></td></tr>" for n in notes)
        self.parameters.setHtml(f"<table cellspacing='0' cellpadding='3'>{rows}</table>")
        self._curve()

    def _parked_toggled(self, on: bool) -> None:
        self.start_temp.setEnabled(not on)
        if on:
            self.start_temp.setValue(self.air.value())

    def _air_moved(self) -> None:
        if self.parked.isChecked():
            self.start_temp.setValue(self.air.value())

    def _toggle_parameters(self, on: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.parameters.setVisible(on)

    def window(self) -> GripWindow:
        base = self.thermal.window
        low = self.window_low.value()
        high = max(self.window_high.value(), low)
        return GripWindow(cold_temp=min(base.cold_temp, low - 1.0), cold_share=self.cold_share.value() / 100,
                          window_low=low, window_high=high, hot_drop_per_k=base.hot_drop_per_k, floor=base.floor)

    # ─── running ─────────────────────────────────────────────────────────────

    def _new_run(self) -> WarmUpRun:
        ts = self.thermal
        v = self.speed.value() / 3.6
        share = ts.styles[self.style.currentData()]
        heat = tuple(slip_heat(ts.tyre, n, share, v) for n in ts.loads)
        return WarmUpRun(ts.front, ts.rear, ts.loads, heat, self.window(), self.air.value(), self.road.value(), v,
                         start=self.start_temp.value(), duration=self.length.value() * 60)

    def start(self) -> None:
        self.timer.stop()
        self.run = self._new_run()
        self.clock.start()
        self.timer.start()
        self._refresh()

    def instant(self) -> None:
        self.timer.stop()
        self.run = self._new_run()
        while not self.run.stopped:
            self.run.step()
        self._refresh()

    def reset(self) -> None:
        self.timer.stop()
        self.run = None
        self._refresh()

    def _tick(self) -> None:
        run = self.run
        if run is None:
            self.timer.stop()
            return
        elapsed = min(self.clock.restart() / 1000.0, 0.1) * TIME_SCALE
        for _ in range(max(1, round(elapsed / run.dt))):
            if run.stopped:
                break
            run.step()
        self._refresh()
        if run.stopped:
            self.timer.stop()

    # ─── outputs ─────────────────────────────────────────────────────────────

    def _curve(self) -> None:
        w = self.window()
        temps = list(range(-20, 111))
        surfaces = self.run.trace[-1].surface if self.run is not None and self.run.trace else ()
        vguides = [(t, colour, name) for t, colour, name in zip(surfaces, (TEAL, CORAL), ("front", "rear"))]
        self.chart_curve.set_data(110, [Series("grip", PURPLE, temps, [w.factor(t) for t in temps])],
                                  [(1.0, GREY, "")], x_min=-20, vguides=vguides)

    def _refresh(self) -> None:
        run = self.run
        self._curve()
        if run is None:
            for card in (self.c_front, self.c_rear, self.c_five, self.c_steady):
                card.set("—")
            self.events.setHtml("Set the weather, the start and the riding, then ride: the tyres warm from the cold "
                                "and the charts show how much grip they give along the way.")
            for chart in self.charts:
                chart.set_data(1.0, [])
            return
        trace = run.trace
        t = [x.t / 60 for x in trace]
        t_max = max(run.duration / 60, 1.0)
        w = run.window
        temps = [v for x in trace for v in x.surface + x.tread + x.carcass] + [run.air, run.road, w.window_low]
        lo, hi = math.floor(min(temps) / 5) * 5 - 5, math.ceil(max(temps) / 5) * 5 + 5
        guides = [(w.window_low, AMBER, "full grip from here"), (run.air, GREY, "air"), (run.road, GREY, "road")]
        if w.window_high < hi:
            guides.append((w.window_high, RED, "too hot above"))
        self.chart_surface.set_range(lo, hi)
        self.chart_surface.set_data(t_max, [Series("front", TEAL, t, [x.surface[0] for x in trace]),
                                            Series("rear", CORAL, t, [x.surface[1] for x in trace])], guides)
        self.chart_inside.set_range(lo, hi)
        self.chart_inside.set_data(t_max, [
            Series("front tread", TEAL, t, [x.tread[0] for x in trace]),
            Series("rear tread", CORAL, t, [x.tread[1] for x in trace]),
            Series("front carcass", TEAL, t, [x.carcass[0] for x in trace], dashed=True),
            Series("rear carcass", CORAL, t, [x.carcass[1] for x in trace], dashed=True),
        ])
        low_grip = min(min(x.grip) for x in trace)
        self.chart_grip.set_range(min(0.5, math.floor(low_grip * 20) / 20), 1.05)
        self.chart_grip.set_data(t_max, [Series("front", TEAL, t, [x.grip[0] for x in trace]),
                                         Series("rear", CORAL, t, [x.grip[1] for x in trace])])
        steady = run.steady()
        for card, i in ((self.c_front, 0), (self.c_rear, 1)):
            reached = run.reached[i]
            if reached is not None:
                card.set(f"after {reached / 60:.1f} min, {run.speed * reached / 1000:.1f} km" if reached > 0
                         else "from the start")
            elif run.stopped:
                card.set("not in this ride", RED if steady[i].surface < w.window_low else None)
            else:
                card.set("…")
        five = next((x for x in trace if x.t >= 300), None)
        self.c_five.set(f"{five.grip[0]:.0%} / {five.grip[1]:.0%}" if five else "…")
        self.c_steady.set(f"{steady[0].surface:.0f} / {steady[1].surface:.0f} °C")
        self.events.setHtml("<br>".join(self._messages(run, steady)))

    def _messages(self, run: WarmUpRun, steady) -> list[str]:
        w = run.window
        lines = []
        cold = [name for name, s in zip(("front", "rear"), steady) if s.surface < w.window_low]
        if cold:
            share = min(w.factor(s.surface) for s in steady)
            lines.append(f"Riding like this, the {' and '.join(cold)} tyre{'s' if len(cold) == 2 else ''} would settle "
                         f"below {w.window_low:g} °C and give about {share:.0%} of a warm tyre's grip however far you go; "
                         "ride harder, faster or in warmer weather, or allow for it.")
        hot = [name for name, s in zip(("front", "rear"), steady) if s.surface > w.window_high]
        if hot:
            lines.append(f"The {' and '.join(hot)} tyre would run above {w.window_high:g} °C: overheating.")
        rolling = [p.rolling_heat(run.speed, n) for p, n in ((run.front, run.loads[0]), (run.rear, run.loads[1]))]
        lines.append(f"Heat from rolling {rolling[0]:.0f} / {rolling[1]:.0f} W and from slip "
                     f"{run.slip_heat[0]:.0f} / {run.slip_heat[1]:.0f} W (front / rear); the tread underneath settles "
                     f"at {steady[0].tread:.0f} / {steady[1].tread:.0f} °C, warmer than its surface, which the wind "
                     "and the road cool.")
        if run.start > max(steady[0].tread, steady[1].tread) + 2:
            lines.append("The tyres start warmer than this ride can keep them: the heat drains away towards the "
                         "settled temperatures.")
        if run.road <= 0 or run.air <= 0:
            lines.append("At or below freezing, frost and ice may lie on the road; this model knows only dry tarmac.")
        return lines
