"""Countersteering: a corner ridden in time with handlebar torque alone, on the benchmark lean-and-steer model, and
the speeds at which the motorcycle steadies itself."""

from __future__ import annotations

import html
import math

from PySide6.QtCore import QElapsedTimer, QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
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
from ..sim.countersteer import SETTLE, Corner, CornerSim
from ..sim.lateral import coefficients, modes, self_stable_range
from ..sim.parameters import lateral_parameters
from .charts import Series, StripChart
from .corner_view import CornerView
from .fields import ResultCard, SliderField, note_label
from .style import AMBER, CORAL, GREY, PURPLE, TEAL, label_font

CUSTOM = "custom"
LINEAR_LEAN_LIMIT = 25.0  # degrees beyond which the linear model's lean drifts noticeably from the exact one
CHART_INTERVAL_MS = 100
CHART_POINTS = 500
STABILITY_SPEEDS = range(4, 162, 2)  # km/h


class CountersteerPanel(QWidget):
    def __init__(self, setup: RiderSetup, bike: catalogue.Bike, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setup, self.bike = setup, bike
        self.tyres = catalogue.original_tyres(bike)
        self.sim: CornerSim | None = None
        self.error = ""
        self.time_scale = 1.0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.clock = QElapsedTimer()
        self.chart_clock = QElapsedTimer()

        self.view = CornerView()
        self.chart_lean = StripChart("Lean (°)", -30, 30, "")
        self.chart_steer = StripChart("Steer angle (°)", -1, 1, "")
        self.chart_torque = StripChart("Handlebar torque (N m), + turns the bars right", -20, 20, "")
        self.chart_wide = StripChart("Off the approach line at turn-in, + towards the corner (cm)", -20, 40, "")
        self.chart_lat = StripChart("Lateral acceleration (g)", -1, 1, "")
        self.chart_modes = StripChart("Left alone: growth rate of each motion (1/s)", -8, 3, "", x_unit=" km/h")
        self.charts = (self.chart_lean, self.chart_steer, self.chart_torque, self.chart_wide, self.chart_lat)
        grid = QGridLayout()
        for i, chart in enumerate(self.charts + (self.chart_modes,)):
            grid.addWidget(chart, i // 3, i % 3)

        self.speed = SliderField("Speed", 30, 160, 1, 60, "km/h")
        self.radius = SliderField("Corner radius", 10, 1000, 1, 80, "m")
        self.angle = SliderField("Corner angle", 10, 180, 1, 90, "°")
        self.roll_in = SliderField("Roll-in time", 0.3, 3.0, 0.05, 1.0, "s", decimals=2)
        self.direction = QComboBox()
        self.direction.addItem("Right-hand corner", 1)
        self.direction.addItem("Left-hand corner", -1)
        direction_row = QHBoxLayout()
        label = QLabel("Direction")
        label.setMinimumWidth(120)
        direction_row.addWidget(label)
        direction_row.addWidget(self.direction, 1)
        self.surface = QComboBox()
        for s in catalogue.surfaces():
            self.surface.addItem(f"{s.label}  (μ {s.mu:.2f})", s.id)
        self.surface.addItem("Custom μ", CUSTOM)
        self.mu = SliderField("Peak grip μ", 0.10, 1.40, 0.01, 1.0, "", decimals=2)
        surface_row = QHBoxLayout()
        label = QLabel("Surface")
        label.setMinimumWidth(120)
        surface_row.addWidget(label)
        surface_row.addWidget(self.surface, 1)

        self.run_button = QPushButton("Ride the corner")
        self.slow_button = QPushButton("Slow motion ×¼")
        self.instant_button = QPushButton("Instant result")
        self.reset_button = QPushButton("Reset")
        buttons = QHBoxLayout()
        for button in (self.run_button, self.slow_button, self.instant_button, self.reset_button):
            buttons.addWidget(button)
        buttons.addStretch(1)

        controls = QVBoxLayout()
        for widget in (self.speed, self.radius, self.angle):
            controls.addWidget(widget)
        controls.addLayout(direction_row)
        controls.addWidget(self.roll_in)
        controls.addLayout(surface_row)
        controls.addWidget(self.mu)
        controls.addLayout(buttons)

        self.c_push = ResultCard("Push, inside grip")
        self.c_counter = ResultCard("Bars turned away")
        self.c_lean_in = ResultCard("Leaned in (90 %)")
        self.c_wide = ResultCard("Ran wide, rear / front")
        self.c_turn = ResultCard("Lean in the turn")
        self.c_stable = ResultCard("Steadies itself at")
        cards = QGridLayout()
        for i, card in enumerate((self.c_push, self.c_counter, self.c_lean_in, self.c_wide, self.c_turn, self.c_stable)):
            cards.addWidget(card, i // 3, i % 3)
        self.events = QTextBrowser()
        self.events.setMaximumHeight(96)
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
        layout.addWidget(self.view, 3)
        layout.addLayout(grid, 3)
        layout.addLayout(bottom)
        layout.addWidget(note_label(
            "Model: the linearised Whipple model of Meijaard et al. (2007), whose published benchmark the tests "
            "reproduce, with this motorcycle's geometry and load and stand-in part inertias. The rider steers by "
            "handlebar torque alone, from the lean error and the lean rate. Constant speed; rigid, knife-edge wheels that "
            "do not slip; the rider is rigid with the frame. The lean and steer angles are exact only when small, and "
            "real tyres, whose aligning moment the model lacks, change the torque held in the steady turn."
        ))

        self.surface.setCurrentIndex(self.surface.findData("dry-asphalt"))
        self.surface.currentIndexChanged.connect(self._surface_chosen)
        self.mu.valueChanged.connect(self._mu_moved)
        self.speed.valueChanged.connect(self._stability)
        self.toggle.toggled.connect(self._toggle_parameters)
        self.run_button.clicked.connect(lambda: self.start(1.0))
        self.slow_button.clicked.connect(lambda: self.start(0.25))
        self.instant_button.clicked.connect(self.instant)
        self.reset_button.clicked.connect(self.reset)
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
        self.params, self.steering, notes = lateral_parameters(self.bike, self.setup, self.tyres)
        self.coefficients = coefficients(self.params)
        self.stable_range = self_stable_range(self.coefficients)
        rows = "".join(f"<tr><td>{html.escape(n.name)}</td><td><b>{html.escape(n.value)}</b></td>"
                       f"<td><i>{html.escape(n.basis)}</i></td></tr>" for n in notes)
        self.parameters.setHtml(f"<table cellspacing='0' cellpadding='3'>{rows}</table>")
        self._stability()

    def _surface_chosen(self) -> None:
        surface_id = self.surface.currentData()
        if surface_id != CUSTOM:
            with QSignalBlocker(self.mu):
                self.mu.setValue(next(s.mu for s in catalogue.surfaces() if s.id == surface_id))

    def _mu_moved(self) -> None:
        current = self.surface.currentData()
        if current != CUSTOM:
            preset = next(s.mu for s in catalogue.surfaces() if s.id == current)
            if abs(preset - self.mu.value()) > 1e-9:
                with QSignalBlocker(self.surface):
                    self.surface.setCurrentIndex(self.surface.findData(CUSTOM))

    def _toggle_parameters(self, on: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.parameters.setVisible(on)

    # ─── running ─────────────────────────────────────────────────────────────

    def corner(self) -> Corner:
        return Corner(self.speed.value(), self.radius.value(), self.angle.value(), self.direction.currentData(),
                      roll_in_time=self.roll_in.value())

    def _new_sim(self) -> CornerSim | None:
        try:
            sim = CornerSim(self.params, self.corner(), torque_lag=self.steering.torque_lag,
                            settled=self.steering.settled_fraction, mu=self.mu.value())
        except ValueError as exc:
            self.error = str(exc).capitalize() + "; the model has no body lean to help."
            return None
        self.error = ""
        return sim

    def start(self, time_scale: float = 1.0) -> None:
        self.timer.stop()
        self.sim = self._new_sim()
        self.time_scale = time_scale
        self.view.set_sim(self.sim)
        if self.sim is not None:
            self.clock.start()
            self.chart_clock.start()
            self.timer.start()
        self._refresh()

    def instant(self) -> None:
        self.timer.stop()
        self.sim = self._new_sim()
        if self.sim is not None:
            while not self.sim.stopped:
                self.sim.step()
        self.view.set_sim(self.sim)
        self._refresh()

    def reset(self) -> None:
        self.timer.stop()
        self.sim = None
        self.error = ""
        self.view.set_sim(None)
        self.view.set_hint("Set the speed, the corner and how quickly to lean in, then ride it: the rider steers by "
                           "handlebar torque alone, and the first push turns the bars away from the corner.")
        self._refresh()

    def _tick(self) -> None:
        sim = self.sim
        if sim is None:
            self.timer.stop()
            return
        elapsed = min(self.clock.restart() / 1000.0, 0.1) * self.time_scale
        for _ in range(min(400, max(0, round(elapsed / sim.dt)))):
            if sim.stopped:
                break
            sim.step()
        finished = sim.stopped
        charts = finished or self.chart_clock.elapsed() >= CHART_INTERVAL_MS
        if charts:
            self.chart_clock.restart()
        self._refresh(charts=charts)
        if finished:
            self.timer.stop()

    # ─── outputs ─────────────────────────────────────────────────────────────

    def _stability(self) -> None:
        k = self.coefficients
        weave, capsize, castering = [], [], []
        for kmh in STABILITY_SPEEDS:
            m = modes(k, kmh / 3.6)
            if m.weave is not None:
                weave.append((kmh, m.weave.real))
                capsize.append((kmh, m.capsize))
                castering.append((kmh, m.castering))
        series = [Series(name, colour, [x for x, _ in pts], [y for _, y in pts])
                  for name, colour, pts in (("weave", PURPLE, weave), ("capsize", CORAL, capsize),
                                            ("castering", TEAL, castering))]
        vguides = [(self.speed.value(), AMBER, "now")]
        band = self.stable_range
        if band is not None:
            vguides += [(band[0] * 3.6, GREY, ""), (min(band[1] * 3.6, STABILITY_SPEEDS[-1]), GREY, "")]
        self.chart_modes.set_data(STABILITY_SPEEDS[-1], series, [(0.0, GREY, "")], x_min=0.0, vguides=vguides)
        if band is None:
            self.c_stable.set("never")
        else:
            upper = "and above" if math.isinf(band[1]) else f"and {band[1] * 3.6:.0f} km/h"
            self.c_stable.set(f"{band[0] * 3.6:.0f} {upper}")

    def _refresh(self, charts: bool = True) -> None:
        sim = self.sim
        self.view.update()
        if sim is None:
            for card in (self.c_push, self.c_counter, self.c_lean_in, self.c_wide, self.c_turn):
                card.set("—")
            self.events.setHtml(html.escape(self.error))
            for chart in self.charts:
                chart.set_data(1.0, [])
            return
        if charts:
            self._charts(sim)
        self.c_push.set(f"{sim.peak_push:.1f} N m" if sim.turn_start is not None else "—")
        self.c_counter.set(f"{math.degrees(sim.peak_countersteer):.2f}°" if sim.turn_start is not None else "—")
        self.c_lean_in.set(f"{sim.time_to_lean:.2f} s · {sim.distance_to_lean:.0f} m"
                           if sim.time_to_lean is not None else "…")
        self.c_wide.set(f"{sim.wide_rear * 100:.1f} / {sim.wide_front * 100:.1f} cm" if sim.turn_start is not None else "—")
        self.c_turn.set(f"{math.degrees(abs(sim.turn.lean)):.1f}°")
        self.events.setHtml("<br>".join(self._messages(sim)))

    def _messages(self, sim: CornerSim) -> list[str]:
        lines = [f"<b>{t:.2f} s</b> — {html.escape(text)}" for t, text in sim.events[-6:]]
        turn = sim.turn
        hold = "pushing" if sim.corner.direction * turn.torque < 0 else "pulling"
        lines.append(f"In the steady turn the rider holds {abs(turn.torque):.1f} N m, {hold} the inside grip, with "
                     f"the bars {math.degrees(abs(turn.steer)):.2f}° into the corner (knife-edge tyres: real ones change "
                     "this torque).")
        designed = SETTLE / sim.gains.omega
        if abs(designed - sim.corner.roll_in_time) > 0.02:
            lines.append(f"At this speed the rider can lean in no faster than about {designed:.2f} s; that is what "
                         "the run uses.")
        lean = math.degrees(abs(sim.turn.lean))
        if lean > LINEAR_LEAN_LIMIT:
            exact = math.degrees(math.atan(sim.v ** 2 / (sim.g * sim.corner.radius)))
            lines.append(f"At {lean:.0f}° the linear model overstates the lean (tan φ = v²/gR gives {exact:.0f}° "
                         "with thin tyres); the Cornering tab has the exact steady-state figures.")
        m = modes(self.coefficients, sim.v)
        if m.capsize is not None:
            if m.capsize > 0:
                lines.append(f"Left alone at this speed, a lean doubles every {math.log(2) / m.capsize:.0f} s (capsize); "
                             "the rider's corrections hide it.")
            else:
                lines.append(f"Left alone at this speed, a small lean dies away (capsize time constant "
                             f"{-1 / m.capsize:.1f} s).")
        if m.weave is not None and m.weave_frequency_hz is not None:
            lines.append(f"Weave at this speed: {m.weave_frequency_hz:.2f} Hz, damping ratio {m.weave_damping:.2f}, "
                         "for a rigid frame; a flexible one damps weave less at high speed (Sharp et al. 2004).")
        return lines

    def _charts(self, sim: CornerSim) -> None:
        trace = sim.trace[:: max(1, len(sim.trace) // CHART_POINTS)]
        if trace[-1] is not sim.trace[-1]:
            trace.append(sim.trace[-1])
        t = [s.t for s in trace]
        t_max = max(sim.t, 1.0)
        lean = math.degrees(abs(sim.turn.lean))
        top = max(10.0, lean * 1.25)
        self.chart_lean.set_range(-top, top)
        self.chart_lean.set_data(t_max, [Series("lean", PURPLE, t, [s.lean for s in trace]),
                                         Series("wanted", GREY, t, [s.lean_target for s in trace], dashed=True)])
        steer_top = max(0.5, max(abs(s.steer) for s in trace) * 1.2)
        self.chart_steer.set_range(-steer_top, steer_top)
        self.chart_steer.set_data(t_max, [Series("steer", TEAL, t, [s.steer for s in trace])])
        torque_top = max(5.0, max(abs(s.torque) for s in trace) * 1.2)
        self.chart_torque.set_range(-torque_top, torque_top)
        self.chart_torque.set_data(t_max, [Series("torque", CORAL, t, [s.torque for s in trace])])
        start = sim.turn_start if sim.turn_start is not None else sim.corner.approach
        window = [s for s in sim.trace if start - 0.2 <= s.t <= start + 1.6]
        wide = max(sim.wide_front, sim.wide_rear, 0.05) * 100
        self.chart_wide.set_range(-2.5 * wide, 2.5 * wide)
        d = sim.corner.direction
        self.chart_wide.set_data(start + 1.6, [
            Series("rear", PURPLE, [s.t for s in window], [d * s.y * 100 for s in window]),
            Series("front", TEAL, [s.t for s in window], [d * s.fy * 100 for s in window]),
        ], [(0.0, GREY, "")], x_min=max(0.0, start - 0.2))
        g_top = max(0.3, sim.peak_lateral_g * 1.3, min(sim.mu * 1.1, 1.5))
        self.chart_lat.set_range(-g_top, g_top)
        self.chart_lat.set_data(t_max, [Series("lateral", PURPLE, t, [s.lateral_g for s in trace])],
                                [(d * sim.mu, CORAL, "grip limit")])
