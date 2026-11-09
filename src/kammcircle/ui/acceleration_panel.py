"""Acceleration: a launch or roll-on run in real time, slow motion or at once, with live charts."""

from __future__ import annotations

import html

from PySide6.QtCore import QElapsedTimer, QSignalBlocker, Qt, QTimer
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
from ..sim import AccelerationSim, acceleration_parameters, braking_parameters, suspension_parameters
from .braking_view import BrakingView
from .charts import Series, StripChart
from .fields import ResultCard, SliderField, note_label
from .style import AMBER, CORAL, PURPLE, TEAL

CUSTOM = "custom"
TIME_LIMIT = 120.0
MAX_STEPS_PER_TICK = 400
CHART_INTERVAL_MS = 100
CHART_POINTS = 400


class AccelerationPanel(QWidget):
    def __init__(self, setup: RiderSetup, bike: catalogue.Bike, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setup, self.bike = setup, bike
        self.tyres = catalogue.original_tyres(bike)
        self.sim: AccelerationSim | None = None
        self.time_scale = 1.0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.clock = QElapsedTimer()
        self.chart_clock = QElapsedTimer()

        self.view = BrakingView()
        self.view.set_bike(bike)
        self.chart_speed = StripChart("Speed", 0, 100, "")
        self.chart_accel = StripChart("Acceleration (g), share of weight per wheel", 0, 1.2, "")
        self.chart_engine = StripChart("Engine (1000 rpm) and gear", 0, 10, "")
        self.chart_slip = StripChart("Rear wheel slip (%)", 0, 40, "")
        self.chart_susp = StripChart("Suspension compression (mm)", 0, 220, "")
        self.chart_pitch = StripChart("Pitch, nose down (°)", -6, 2, "")
        self.charts = (self.chart_speed, self.chart_accel, self.chart_engine,
                       self.chart_slip, self.chart_susp, self.chart_pitch)
        grid = QGridLayout()
        for i, chart in enumerate(self.charts):
            grid.addWidget(chart, i // 3, i % 3)

        self.start_speed = SliderField("Start speed", 0, 120, 1, 0, "km/h")
        self.target = SliderField("Target speed", 30, 180, 1, 100, "km/h")
        self.top_speed_box = QCheckBox("Run to top speed instead")
        self.throttle = SliderField("Throttle", 10, 100, 1, 100, "%")
        self.control = QCheckBox("Throttle control: keep the rear tyre at its grip limit and the front wheel down")
        self.control.setChecked(True)
        self.launch = SliderField("Launch speed", 1500, 8000, 50, 4000, "rpm")
        self.shift = SliderField("Shift at", 3000, 9500, 50, 7800, "rpm")
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

        self.run_button = QPushButton("Go")
        self.slow_button = QPushButton("Slow motion ×¼")
        self.instant_button = QPushButton("Instant result")
        self.reset_button = QPushButton("Reset")
        buttons = QHBoxLayout()
        for button in (self.run_button, self.slow_button, self.instant_button, self.reset_button):
            buttons.addWidget(button)
        buttons.addStretch(1)

        controls = QVBoxLayout()
        for widget in (self.start_speed, self.target):
            controls.addWidget(widget)
        controls.addWidget(self.top_speed_box)
        for widget in (self.throttle, self.launch, self.shift):
            controls.addWidget(widget)
        controls.addWidget(self.control)
        controls.addLayout(surface_row)
        controls.addWidget(self.mu)
        controls.addLayout(buttons)

        self.c_50 = ResultCard("0–50 km/h")
        self.c_100 = ResultCard("0–100 km/h")
        self.c_peak = ResultCard("Peak acceleration")
        self.c_end = ResultCard("Result")
        cards = QGridLayout()
        for i, card in enumerate((self.c_50, self.c_100, self.c_peak, self.c_end)):
            cards.addWidget(card, i // 2, i % 2)
        self.events = QLabel()
        self.events.setWordWrap(True)
        self.events.setTextFormat(Qt.TextFormat.RichText)
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
            "Model: the suspended model of the Braking tab with the engine driving the rear wheel through the "
            "published gearing; the torque curve passes through the published peak torque and power, and its shape "
            "elsewhere is an assumption. The clutch slips at the launch speed until the motorcycle catches up; drive is "
            "cut while shifting and at the rev limit. Aerodynamic drag uses a drag area derived from the reported top "
            "speed. Not modelled: chain pull on the swingarm (anti-squat), engine braking, clutch heat."
        ))

        self.surface.setCurrentIndex(self.surface.findData("dry-asphalt"))
        self.surface.currentIndexChanged.connect(self._surface_chosen)
        self.mu.valueChanged.connect(self._mu_moved)
        self.toggle.toggled.connect(self._toggle_parameters)
        self.top_speed_box.toggled.connect(lambda on: self.target.setEnabled(not on))
        self.run_button.clicked.connect(lambda: self.start(1.0))
        self.slow_button.clicked.connect(lambda: self.start(0.25))
        self.instant_button.clicked.connect(self.instant)
        self.reset_button.clicked.connect(self.reset)
        self._defaults_for_bike()
        self.reset()

    # ─── inputs ──────────────────────────────────────────────────────────────

    def _defaults_for_bike(self) -> None:
        drive = self.bike.raw.get("drivetrain")
        if drive:
            self.shift.setValue(drive["max_power_rpm"] - 200)
            self.launch.setValue(round(drive["max_torque_rpm"] * 0.8 / 50) * 50)
        self._show_parameters()

    def set_setup(self, setup: RiderSetup) -> None:
        self.setup = setup
        self._show_parameters()

    def set_bike(self, bike: catalogue.Bike) -> None:
        self.bike = bike
        self.tyres = catalogue.original_tyres(bike)
        self.view.set_bike(bike)
        self.reset()
        self._defaults_for_bike()

    def set_tyres(self, tyres: catalogue.TyreChoice) -> None:
        self.tyres = tyres
        self._show_parameters()

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

    def _show_parameters(self) -> None:
        spec, notes = acceleration_parameters(self.bike, self.setup, self.tyres)
        notes = notes + braking_parameters(self.bike, self.setup, self.mu.value(), self.tyres)[1]
        rows = "".join(f"<tr><td>{html.escape(n.name)}</td><td><b>{html.escape(n.value)}</b></td>"
                       f"<td><i>{html.escape(n.basis)}</i></td></tr>" for n in notes)
        self.parameters.setHtml(f"<table cellspacing='0' cellpadding='3'>{rows}</table>")

    # ─── running ─────────────────────────────────────────────────────────────

    def _new_sim(self) -> AccelerationSim:
        spec, _ = acceleration_parameters(self.bike, self.setup, self.tyres)
        params, _ = braking_parameters(self.bike, self.setup, self.mu.value(), self.tyres)
        susp, _ = suspension_parameters(self.bike, self.setup)
        powertrain = spec.powertrain(shift_rpm=self.shift.value(), launch_rpm=self.launch.value())
        target = None if self.top_speed_box.isChecked() else self.target.value()
        return AccelerationSim(params, susp, powertrain, speed_kmh=self.start_speed.value(), target_kmh=target,
                               throttle=self.throttle.value() / 100, throttle_control=self.control.isChecked(),
                               cda=spec.cda, crr=spec.crr, air_density=spec.air_density)

    def start(self, time_scale: float = 1.0) -> None:
        self.timer.stop()
        self.sim = self._new_sim()
        self.time_scale = time_scale
        self.view.set_sim(self.sim)
        self.clock.start()
        self.chart_clock.start()
        self.timer.start()
        self._refresh()

    def instant(self) -> None:
        self.timer.stop()
        self.sim = self._new_sim()
        self.view.set_sim(self.sim)
        self._advance(TIME_LIMIT, unlimited=True)
        self._refresh()

    def reset(self) -> None:
        self.timer.stop()
        self.sim = None
        self.view.set_sim(None)
        self.view.set_hint("Set the start and target speeds, the throttle and the gear changes, then press Go.")
        self._refresh()

    def _advance(self, seconds: float, unlimited: bool = False) -> None:
        sim = self.sim
        if sim is None:
            return
        steps = max(0, round(seconds / sim.dt))
        if not unlimited:
            steps = min(steps, MAX_STEPS_PER_TICK)
        for _ in range(steps):
            if sim.stopped:
                break
            sim.step(0.0, 0.0)
            if sim.t >= TIME_LIMIT:
                sim.stop_at_time_limit()

    def _tick(self) -> None:
        elapsed = min(self.clock.restart() / 1000.0, 0.1)
        self._advance(elapsed * self.time_scale)
        finished = self.sim is None or self.sim.stopped
        charts = finished or self.chart_clock.elapsed() >= CHART_INTERVAL_MS
        if charts:
            self.chart_clock.restart()
        self._refresh(charts=charts)
        if finished:
            self.timer.stop()

    # ─── outputs ─────────────────────────────────────────────────────────────

    def _refresh(self, charts: bool = True) -> None:
        sim = self.sim
        self.view.update()
        if sim is None:
            for card in (self.c_50, self.c_100, self.c_peak, self.c_end):
                card.set("—")
            self.events.setText("")
            for chart in self.charts:
                chart.set_data(1.0, [])
            return
        if charts:
            self._charts(sim)
        s = sim.acceleration_summary()
        self.c_50.set(f"{s['t_50']:.2f} s" if s["t_50"] is not None else "—")
        self.c_100.set(f"{s['t_100']:.2f} s" if s["t_100"] is not None else "—")
        self.c_peak.set(f"{s['peak_accel_g']:.2f} g")
        outcome = {"reached": f"{s['speed_kmh']:.0f} km/h in {s['time']:.1f} s, {s['distance']:.0f} m",
                   "top speed": f"top speed {s['speed_kmh']:.0f} km/h",
                   "looped over": "looped over backwards", "time limit": "time limit"}.get(s["outcome"], "…")
        self.c_end.set(outcome)
        lines = [f"<b>{t:.2f} s</b> — {html.escape(text)}" for t, text in sim.events[-8:]]
        shifts = sim.powertrain.shifts
        if shifts:
            lines.append("Gear changes: " + ", ".join(f"{g} at {t:.2f} s" for t, g in shifts))
        if s["wheelspin_s"] > 0.05:
            lines.append(f"The rear tyre spun for {s['wheelspin_s']:.2f} s.")
        self.events.setText("<br>".join(lines))

    def _charts(self, sim: AccelerationSim) -> None:
        trace = sim.trace[:: max(1, len(sim.trace) // CHART_POINTS)]
        if trace[-1] is not sim.trace[-1]:
            trace.append(sim.trace[-1])
        t = [x.t for x in trace]
        t_max = max(sim.t, 1.0)
        weight = sim.p.weight
        top = max(x.v for x in trace) * 3.6
        self.chart_speed.set_range(0, max(top * 1.1, 10))
        self.chart_speed.set_data(t_max, [Series("speed, km/h", PURPLE, t, [x.v * 3.6 for x in trace])])
        self.chart_accel.set_data(t_max, [
            Series("acceleration", PURPLE, t, [x.a / sim.p.g for x in trace]),
            Series("front", TEAL, t, [x.nf / weight for x in trace]),
            Series("rear", CORAL, t, [x.nr / weight for x in trace]),
        ])
        limit = sim.powertrain.engine.limit_rpm / 1000
        self.chart_engine.set_range(0, max(10.0, limit + 0.5))
        self.chart_engine.set_data(t_max, [
            Series("rpm ÷ 1000", PURPLE, t, [x.rpm / 1000 for x in trace]),
            Series("gear", AMBER, t, [x.gear for x in trace]),
        ], [(limit, CORAL, "rev limit")])
        self.chart_slip.set_data(t_max, [Series("rear", CORAL, t, [max(0.0, x.kr) * 100 for x in trace])])
        susp = sim.susp
        self.chart_susp.set_range(-5, max(susp.front_travel, susp.rear_travel) * 1000 * 1.1)
        self.chart_susp.set_data(t_max, [Series("front", TEAL, t, [x.susp_f for x in trace]),
                                         Series("rear", CORAL, t, [x.susp_r for x in trace])])
        pitches = [x.pitch for x in trace]
        self.chart_pitch.set_range(min(-6.0, min(pitches) - 1), max(2.0, max(pitches) + 1))
        self.chart_pitch.set_data(t_max, [Series("pitch", PURPLE, t, pitches)])
