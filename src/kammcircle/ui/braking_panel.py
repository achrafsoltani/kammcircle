"""Braking: a time-stepped simulation run in real time (or slow motion), with live levers and charts."""

from __future__ import annotations

import html

from PySide6.QtCore import QElapsedTimer, QEvent, QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
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
from ..sim import BrakingSim, LeverRamp, SuspendedBrakingSim, braking_parameters, suspension_parameters
from .braking_view import BrakingView
from .charts import Series, StripChart
from .fields import ResultCard, SliderField, note_label
from .style import AMBER, CORAL, PURPLE, RED, TEAL

CUSTOM = "custom"
BRAKE_AT = 0.6  # s of steady riding before a scripted run touches the brakes
TIME_LIMIT = 60.0  # s
MAX_STEPS_PER_TICK = 400
CHART_INTERVAL_MS = 100  # charts redraw ten times a second; the animation every frame
CHART_POINTS = 400  # samples drawn per series at most


class BrakingPanel(QWidget):
    def __init__(self, setup: RiderSetup, bike: catalogue.Bike, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setup = setup
        self.bike = bike
        self.sim: BrakingSim | None = None
        self.tyres: catalogue.TyreChoice = catalogue.original_tyres(bike)
        self.levers = LeverRamp()
        self.time_scale = 1.0
        self.manual = False
        self.held = {"front": False, "rear": False}
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.clock = QElapsedTimer()
        self.chart_clock = QElapsedTimer()

        self.view = BrakingView()
        self.view.set_bike(bike)
        self.chart_speed = StripChart("Speed", 0, 100, "")
        self.chart_decel = StripChart("Deceleration (g), share of weight per wheel", 0, 1.4, "")
        self.chart_slip = StripChart("Wheel slip (%)", 0, 100, "")
        self.chart_brakes = StripChart("Lever demand and brake torque (%)", 0, 100, "")
        self.chart_susp = StripChart("Suspension compression (mm)", 0, 220, "")
        self.chart_pitch = StripChart("Pitch, nose down (°)", -2, 10, "")
        self.charts = (self.chart_speed, self.chart_decel, self.chart_susp,
                       self.chart_slip, self.chart_brakes, self.chart_pitch)
        charts = QGridLayout()
        for i, chart in enumerate(self.charts):
            charts.addWidget(chart, i // 3, i % 3)

        self.speed = SliderField("Speed", 20, 160, 1, 80, "km/h")
        self.surface = QComboBox()
        for s in catalogue.surfaces():
            self.surface.addItem(f"{s.label}  (μ {s.mu:.2f})", s.id)
        self.surface.addItem("Custom μ", CUSTOM)
        self.mu = SliderField("Peak grip μ", 0.10, 1.40, 0.01, 1.0, "", decimals=2)
        self.front = SliderField("Front lever", 0, 100, 1, 60, "%")
        self.rear = SliderField("Rear pedal", 0, 100, 1, 20, "%")
        self.squeeze = SliderField("Squeeze time", 0.05, 1.0, 0.05, 0.3, "s", decimals=2)
        self.abs_front = QCheckBox("ABS front")
        self.abs_rear = QCheckBox("ABS rear")
        self.abs_front.setChecked(True)
        self.abs_rear.setChecked(True)
        self.manual_box = QCheckBox("Brake live: hold F (front) and R (rear) at the lever positions above")
        self.suspension_box = QCheckBox("Suspension (fork dive, rear travel, compliant tyres)")
        self.suspension_box.setChecked(True)

        surface_row = QHBoxLayout()
        surface_label = QLabel("Surface")
        surface_label.setMinimumWidth(120)
        surface_row.addWidget(surface_label)
        surface_row.addWidget(self.surface, 1)
        abs_row = QHBoxLayout()
        abs_row.addWidget(self.abs_front)
        abs_row.addWidget(self.abs_rear)
        abs_row.addWidget(self.suspension_box)
        abs_row.addStretch(1)

        self.run_button = QPushButton("Brake")
        self.slow_button = QPushButton("Slow motion ×¼")
        self.instant_button = QPushButton("Instant result")
        self.reset_button = QPushButton("Reset")
        buttons = QHBoxLayout()
        for button in (self.run_button, self.slow_button, self.instant_button, self.reset_button):
            buttons.addWidget(button)
        buttons.addStretch(1)

        controls = QVBoxLayout()
        for widget in (self.speed,):
            controls.addWidget(widget)
        controls.addLayout(surface_row)
        for widget in (self.mu, self.front, self.rear, self.squeeze):
            controls.addWidget(widget)
        controls.addLayout(abs_row)
        controls.addWidget(self.manual_box)
        controls.addLayout(buttons)

        self.c_distance = ResultCard("Stopping distance")
        self.c_time = ResultCard("Stopping time")
        self.c_mean = ResultCard("Mean deceleration")
        self.c_peak = ResultCard("Peak deceleration")
        cards = QGridLayout()
        for i, card in enumerate((self.c_distance, self.c_time, self.c_mean, self.c_peak)):
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
        layout.addLayout(charts, 3)
        layout.addLayout(bottom)
        layout.addWidget(note_label(
            "Model: the sprung motorcycle and rider (surge, heave, pitch) on a fork that slides along the steering axis "
            "and a rear wheel that travels up and down, with compliant tyres and spinning wheels; untick Suspension "
            "for the rigid model. No aerodynamic drag and no engine braking (clutch in). Tyre force from the Magic "
            "Formula fitted to a 160/70 sport tyre by Sharp, Evangelou and Limebeer (2004), scaled to the surface; "
            "generic slip-band ABS. A locked front wheel would make a real motorcycle fall; this in-plane model keeps "
            "it upright and says so."
        ))

        self.surface.setCurrentIndex(self.surface.findData("dry-asphalt"))
        self.surface.currentIndexChanged.connect(self._surface_chosen)
        self.mu.valueChanged.connect(self._mu_moved)
        self.toggle.toggled.connect(self._toggle_parameters)
        self.run_button.clicked.connect(lambda: self.start(1.0))
        self.slow_button.clicked.connect(lambda: self.start(0.25))
        self.instant_button.clicked.connect(self.instant)
        self.reset_button.clicked.connect(self.reset)
        self.manual_box.toggled.connect(self._manual_toggled)
        self.suspension_box.toggled.connect(self._show_parameters)
        self._show_parameters()
        self.reset()

    # ─── inputs ──────────────────────────────────────────────────────────────

    def set_setup(self, setup: RiderSetup) -> None:
        self.setup = setup
        self._show_parameters()

    def set_bike(self, bike: catalogue.Bike) -> None:
        self.bike = bike
        self.tyres = catalogue.original_tyres(bike)
        self.view.set_bike(bike)
        self.reset()
        self._show_parameters()

    def set_tyres(self, tyres: catalogue.TyreChoice) -> None:
        self.tyres = tyres
        self._show_parameters()

    def _surface_chosen(self) -> None:
        surface_id = self.surface.currentData()
        if surface_id != CUSTOM:
            with QSignalBlocker(self.mu):
                self.mu.setValue(next(s.mu for s in catalogue.surfaces() if s.id == surface_id))
        self._show_parameters()

    def _mu_moved(self) -> None:
        current = self.surface.currentData()
        if current != CUSTOM:
            preset = next(s.mu for s in catalogue.surfaces() if s.id == current)
            if abs(preset - self.mu.value()) > 1e-9:
                with QSignalBlocker(self.surface):
                    self.surface.setCurrentIndex(self.surface.findData(CUSTOM))
        self._show_parameters()

    def _manual_toggled(self, on: bool) -> None:
        self.manual = on
        self.instant_button.setEnabled(not on)
        # Listen to the whole application, so that F and R brake even while a number box has the focus.
        app = QApplication.instance()
        if on:
            app.installEventFilter(self)
        else:
            app.removeEventFilter(self)
        self.reset()

    def _toggle_parameters(self, on: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.parameters.setVisible(on)

    def _show_parameters(self) -> None:
        params, notes = braking_parameters(self.bike, self.setup, self.mu.value(), self.tyres)
        if self.suspension_box.isChecked():
            notes = notes + suspension_parameters(self.bike, self.setup)[1]
        rows = "".join(
            f"<tr><td>{html.escape(n.name)}</td><td><b>{html.escape(n.value)}</b></td><td><i>{html.escape(n.basis)}</i></td></tr>"
            for n in notes
        )
        self.parameters.setHtml(f"<table cellspacing='0' cellpadding='3'>{rows}</table>")

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt override)
        kind = event.type()
        if (self.manual and self.isVisible() and kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
                and event.key() in (Qt.Key.Key_F, Qt.Key.Key_R)):
            if not event.isAutoRepeat():
                self._key(event.key(), kind == QEvent.Type.KeyPress)
            return True  # consumed, auto-repeats included
        return False

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.manual and event.key() in (Qt.Key.Key_F, Qt.Key.Key_R):
            if not event.isAutoRepeat():
                self._key(event.key(), True)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if self.manual and event.key() in (Qt.Key.Key_F, Qt.Key.Key_R):
            if not event.isAutoRepeat():
                self._key(event.key(), False)
            return
        super().keyReleaseEvent(event)

    def _key(self, key, pressed: bool) -> None:
        self.held["front" if key == Qt.Key.Key_F else "rear"] = pressed
        if pressed and (self.sim is None or self.sim.stopped):
            self.start(self.time_scale if self.sim else 1.0)

    # ─── running ─────────────────────────────────────────────────────────────

    def _new_sim(self) -> BrakingSim:
        params, _ = braking_parameters(self.bike, self.setup, self.mu.value(), self.tyres)
        self.levers = LeverRamp(self.squeeze.value())
        options = dict(abs_front=self.abs_front.isChecked(), abs_rear=self.abs_rear.isChecked())
        if self.suspension_box.isChecked():
            susp, _ = suspension_parameters(self.bike, self.setup)
            return SuspendedBrakingSim(params, susp, self.speed.value(), **options)
        return BrakingSim(params, self.speed.value(), **options)

    def start(self, time_scale: float = 1.0) -> None:
        held = dict(self.held)
        self.timer.stop()
        self.sim = self._new_sim()
        self.held = held
        self.time_scale = time_scale
        self.view.set_sim(self.sim)
        self.clock.start()
        self.chart_clock.start()
        self.timer.start()
        self.setFocus()
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
        self.held = {"front": False, "rear": False}
        self.view.set_sim(None)
        self.view.set_hint("Hold F for the front brake and R for the rear; the run starts with the first key."
                           if self.manual else "Set the speed, the surface and the levers, then press Brake.")
        self._refresh()

    def _targets(self) -> tuple[float, float]:
        if self.manual:
            return (self.front.value() / 100 if self.held["front"] else 0.0,
                    self.rear.value() / 100 if self.held["rear"] else 0.0)
        if self.sim and self.sim.t >= BRAKE_AT:
            return self.front.value() / 100, self.rear.value() / 100
        return 0.0, 0.0

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
            front, rear = self._targets()
            self.levers.update(front, rear, sim.dt)
            sim.step(self.levers.front, self.levers.rear)
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
            for card in (self.c_distance, self.c_time, self.c_mean, self.c_peak):
                card.set("—")
            self.events.setText("")
            for chart in self.charts:
                chart.set_data(1.0, [])
            return
        if charts:
            self._charts(sim)
        summary = sim.summary()
        if sim.stopped and summary.outcome == "stopped":
            self.c_distance.set(f"{summary.stopping_distance:.1f} m")
            self.c_time.set(f"{summary.stopping_time:.2f} s")
            self.c_mean.set(f"{summary.mean_decel_g:.2f} g")
        elif sim.stopped and summary.outcome == "pitched over":
            self.c_distance.set("went over the front", RED)
            self.c_time.set(f"{summary.stopping_time:.2f} s to the point of no return")
            self.c_mean.set("—")
        else:
            for card in (self.c_distance, self.c_time, self.c_mean):
                card.set("…")
        self.c_peak.set(f"{summary.peak_decel_g:.2f} g")
        lines = [f"<b>{t:.2f} s</b> — {html.escape(text)}" for t, text in sim.events[-8:]]
        extra = []
        start_kmh = sim.speed0 * 3.6
        for wheel, tyre in (("front", self.tyres.front), ("rear", self.tyres.rear)):
            if tyre.speed_kmh is not None and start_kmh > tyre.speed_kmh:
                extra.append(f"<span style='color:#E24B4A'>The {wheel} tyre is rated for {tyre.speed_kmh:.0f} km/h "
                             f"({tyre.ss}); this run starts at {start_kmh:.0f} km/h.</span>")
        if sim.stopped and (summary.abs_cycles_front or summary.abs_cycles_rear):
            extra.append(f"ABS released the brakes {summary.abs_cycles_front} times at the front and "
                         f"{summary.abs_cycles_rear} at the rear.")
        if sim.stopped and summary.max_rear_lift_mm > 0:
            extra.append(f"The rear wheel rose {summary.max_rear_lift_mm:.0f} mm at most.")
        self.events.setText("<br>".join(lines + extra))

    def _charts(self, sim: BrakingSim) -> None:
        trace = sim.trace[:: max(1, len(sim.trace) // CHART_POINTS)]
        if trace[-1] is not sim.trace[-1]:
            trace.append(sim.trace[-1])
        t = [s.t for s in trace]
        t_max = max(sim.t, 1.0)
        weight = sim.p.weight
        self.chart_speed.set_range(0, sim.speed0 * 3.6 * 1.05)
        self.chart_speed.set_data(t_max, [Series("speed, km/h", PURPLE, t, [s.v * 3.6 for s in trace])])
        top = max(1.4, sim.peak_decel / sim.p.g + 0.1)
        self.chart_decel.set_range(0, top)
        self.chart_decel.set_data(t_max, [
            Series("deceleration", PURPLE, t, [-s.a / sim.p.g for s in trace]),
            Series("front", TEAL, t, [s.nf / weight for s in trace]),
            Series("rear", CORAL, t, [s.nr / weight for s in trace]),
        ], [(sim.p.lift_deceleration_g, RED, "rear lifts at this deceleration")])
        peak = -sim.peak_slip(sim.p.static_front_load) * 100
        self.chart_slip.set_data(t_max, [
            Series("front", TEAL, t, [-s.kf * 100 for s in trace]),
            Series("rear", CORAL, t, [-s.kr * 100 for s in trace]),
        ], [(peak, AMBER, "peak grip")])
        susp = getattr(sim, "susp", None)
        if susp is None:
            guides = []
        elif abs(susp.front_travel - susp.rear_travel) < 1e-6:
            guides = [(susp.front_travel * 1000, PURPLE, "full travel")]
        else:
            guides = [(susp.front_travel * 1000, TEAL, "front: full travel"),
                      (susp.rear_travel * 1000, CORAL, "rear: full travel")]
        top = 220.0 if susp is None else max(susp.front_travel, susp.rear_travel) * 1000 * 1.1
        self.chart_susp.set_range(-5, top)
        self.chart_susp.set_data(t_max, [
            Series("front", TEAL, t, [s.susp_f for s in trace]),
            Series("rear", CORAL, t, [s.susp_r for s in trace]),
        ], guides)
        pitches = [s.pitch for s in trace]
        self.chart_pitch.set_range(min(-2.0, min(pitches) - 1), max(10.0, max(pitches) + 1))
        self.chart_pitch.set_data(t_max, [Series("pitch", PURPLE, t, pitches)])
        self.chart_brakes.set_data(t_max, [
            Series("front lever", TEAL, t, [s.lever_f * 100 for s in trace], dashed=True),
            Series("front brake", TEAL, t, [s.torque_f * 100 for s in trace]),
            Series("rear pedal", CORAL, t, [s.lever_r * 100 for s in trace], dashed=True),
            Series("rear brake", CORAL, t, [s.torque_r * 100 for s in trace]),
        ])
