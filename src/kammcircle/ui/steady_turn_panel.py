"""Steady turn on the tyre model: the lean, the tyres' slip and camber, the steer angle and the torque the rider holds
on the handlebars, from a full balance of the motorcycle with Magic Formula tyres (sim.steady_turn)."""

from __future__ import annotations

import html
import math

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QTextBrowser, QToolButton, QVBoxLayout, QWidget

from .. import catalogue
from ..rider import RiderSetup
from ..sim.parameters import steady_turn_parameters
from ..sim.steady_turn import (
    BeyondGrip,
    Trim,
    TrimModel,
    grip_limit_speed,
    kinematic_steer,
    peak_friction,
    solve,
    sweep_lateral,
    sweep_speed,
)
from .charts import Series, StripChart
from .fields import ResultCard, SliderField, note_label
from .steady_turn_view import TorqueBars, TrimView
from .style import AMBER, CORAL, GREY, PURPLE, RED, TEAL, label_font, usage_colour

CUSTOM = "custom"
G = 9.81
CHART_SPEEDS = [float(v) for v in range(15, 186, 10)]  # km/h
CHART_DELAY_MS = 180


def hold_words(torque: float) -> str:
    """How the rider holds a steady torque in a right-hand turn (inside grip = right): + turns the bars right."""
    return "pulling the inside grip" if torque > 0 else "pushing the inside grip"


class SteadyTurnPanel(QWidget):
    def __init__(self, setup: RiderSetup, bike: catalogue.Bike, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setup, self.bike = setup, bike
        self.tyres = catalogue.original_tyres(bike)
        self.grip = (1.0, 1.0)
        self.model: TrimModel | None = None
        self.trim: Trim | None = None
        self.error = ""
        self.limit_kmh: float | None = None
        self.stale = True  # the charts and grip limit wait until the tab is on screen
        self.chart_timer = QTimer(self)
        self.chart_timer.setSingleShot(True)
        self.chart_timer.setInterval(CHART_DELAY_MS)
        self.chart_timer.timeout.connect(self._slow_results)

        self.view = TrimView()
        self.bars = TorqueBars()
        views = QHBoxLayout()
        views.addWidget(self.view, 1)
        views.addWidget(self.bars, 1)

        self.chart_torque = StripChart("Torque you hold at this lean (N m), + pulls the inside grip", -20, 20, "",
                                       x_unit=" km/h")
        self.chart_steer = StripChart("Bars turned at this lean (°), + into the turn", -2, 2, "", x_unit=" km/h")
        self.chart_slip = StripChart("Slip angles at this speed (°)", -1, 3, "", x_unit=" g")
        charts = QHBoxLayout()
        for chart in (self.chart_torque, self.chart_steer, self.chart_slip):
            charts.addWidget(chart, 1)

        self.speed = SliderField("Speed", 10, 200, 1, 60, "km/h")
        self.radius = SliderField("Corner radius", 5, 500, 1, 50, "m")
        self.surface = QComboBox()
        for s in catalogue.surfaces():
            self.surface.addItem(f"{s.label}  (μ {s.mu:.2f})", s.id)
        self.surface.addItem("Custom μ", CUSTOM)
        self.mu = SliderField("Peak grip μ", 0.10, 1.30, 0.01, 1.0, "", decimals=2)
        surface_row = QHBoxLayout()
        label = QLabel("Surface")
        label.setMinimumWidth(120)
        surface_row.addWidget(label)
        surface_row.addWidget(self.surface, 1)
        self.offset = SliderField("Rider off centre", -200, 300, 5, 0, "mm")
        self.offset.setToolTip("Your centre of mass moved towards the inside of the turn (hanging off), or towards "
                               "the outside (negative: standing on the outside peg)")
        self.along = SliderField("Brake (−) / drive (+)", -0.6, 0.3, 0.01, 0.0, "g", decimals=2)
        self.along.setToolTip("Slowing or speeding up along the corner, held steady; braking is shared 70 % front")
        controls = QVBoxLayout()
        for widget in (self.speed, self.radius):
            controls.addWidget(widget)
        controls.addLayout(surface_row)
        for widget in (self.mu, self.offset, self.along):
            controls.addWidget(widget)
        controls.addStretch(1)

        self.c_lat = ResultCard("Lateral acceleration")
        self.c_lean = ResultCard("Lean (motorcycle)")
        self.c_steer = ResultCard("Bars turned")
        self.c_hold = ResultCard("Torque you hold")
        self.c_slip = ResultCard("Slip angle, front / rear")
        self.c_camber = ResultCard("From camber, front / rear")
        self.c_grip = ResultCard("Grip used, front / rear")
        self.c_limit = ResultCard("Fastest steady speed here")
        self.c_drive = ResultCard("Rear drive force")
        self.cards = (self.c_lat, self.c_lean, self.c_steer, self.c_hold, self.c_slip, self.c_camber, self.c_grip,
                      self.c_limit, self.c_drive)
        cards = QGridLayout()
        for i, card in enumerate(self.cards):
            cards.addWidget(card, i // 3, i % 3)
        self.messages = QTextBrowser()
        self.messages.setMaximumHeight(120)
        self.messages.setFont(label_font(self.messages, 0.9))
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
        results.addWidget(self.messages)
        results.addWidget(self.toggle)
        results.addWidget(self.parameters)

        bottom = QHBoxLayout()
        bottom.addLayout(controls, 2)
        bottom.addLayout(results, 3)
        layout = QVBoxLayout(self)
        layout.addLayout(views, 3)
        layout.addLayout(charts, 2)
        layout.addLayout(bottom)
        layout.addWidget(note_label(
            "Model: the whole motorcycle balanced in a steady turn (forces, moments and the wheels' gyroscopic "
            "moments), with round-section tyres whose contact patches move across the tread as they lean, and Magic "
            "Formula tyre forces and aligning moments in slip and camber (Sharp, Evangelou and Limebeer 2004). The "
            "tests rebuild that paper's GSX-R1000 and match its published steady 30° turn within about 0.3 N m of "
            "steering torque and 3 % of tyre force. "
            "The tyre data are the paper's sport radials, not your tyres; part masses and inertias are the "
            "stand-ins of the Countersteering tab. Braking is shared 70 % front, and the friction circle bounds the "
            "combined grip."
        ))

        self.surface.setCurrentIndex(self.surface.findData("dry-asphalt"))
        self.surface.currentIndexChanged.connect(self._surface_chosen)
        self.mu.valueChanged.connect(self._mu_moved)
        self.offset.valueChanged.connect(self._model_changed)
        for widget in (self.speed, self.radius, self.along):
            widget.valueChanged.connect(self.refresh)
        self.toggle.toggled.connect(self._toggle_parameters)
        self._model_changed()

    # ─── inputs ──────────────────────────────────────────────────────────────

    def set_setup(self, setup: RiderSetup) -> None:
        self.setup = setup
        self._model_changed()

    def set_bike(self, bike: catalogue.Bike) -> None:
        self.bike = bike
        self.tyres = catalogue.original_tyres(bike)
        self._model_changed()

    def set_tyres(self, tyres: catalogue.TyreChoice) -> None:
        self.tyres = tyres
        self._model_changed()

    def set_tyre_grip(self, front: float, rear: float) -> None:
        self.grip = (front, rear)
        self._model_changed()

    def _surface_chosen(self) -> None:
        surface_id = self.surface.currentData()
        if surface_id != CUSTOM:
            with QSignalBlocker(self.mu):
                self.mu.setValue(next(s.mu for s in catalogue.surfaces() if s.id == surface_id))
        self._model_changed()

    def _mu_moved(self) -> None:
        current = self.surface.currentData()
        if current != CUSTOM:
            preset = next(s.mu for s in catalogue.surfaces() if s.id == current)
            if abs(preset - self.mu.value()) > 1e-9:
                with QSignalBlocker(self.surface):
                    self.surface.setCurrentIndex(self.surface.findData(CUSTOM))
        self._model_changed()

    def _toggle_parameters(self, on: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.parameters.setVisible(on)

    def _model_changed(self) -> None:
        self.model, notes = steady_turn_parameters(self.bike, self.setup, self.tyres, mu=self.mu.value(),
                                                   grip=self.grip, rider_offset_mm=self.offset.value())
        rows = "".join(f"<tr><td>{html.escape(n.name)}</td><td><b>{html.escape(n.value)}</b></td>"
                       f"<td><i>{html.escape(n.basis)}</i></td></tr>" for n in notes)
        self.parameters.setHtml(f"<table cellspacing='0' cellpadding='3'>{rows}</table>")
        self.refresh()

    # ─── results ─────────────────────────────────────────────────────────────

    def acceleration(self) -> float:
        return self.along.value() * G

    def refresh(self) -> None:
        """Solve the turn now (a few milliseconds); the charts and the grip limit follow after a short pause."""
        m = self.model
        assert m is not None
        v, radius = self.speed.value() / 3.6, self.radius.value()
        try:
            self.trim = solve(m, v, radius=radius, acceleration=self.acceleration())
            self.error = ""
        except BeyondGrip as exc:
            self.trim = None
            self.error = f"No steady turn at {self.speed.value():.0f} km/h on a {radius:.0f} m radius: {exc}."
        self._show()
        self.stale = True
        if self.isVisible():  # the slower results take a few tenths of a second: never while another tab runs
            self.chart_timer.start()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.stale:
            self.chart_timer.start()

    def _show(self) -> None:
        t, m = self.trim, self.model
        lat = (self.speed.value() / 3.6) ** 2 / (self.radius.value() * G)
        self.c_lat.set(f"{lat:.2f} g")
        if t is None or m is None:
            for card in self.cards[1:]:
                if card is not self.c_limit:
                    card.set("—")
            self.c_grip.set("beyond", RED)
            self.view.set_trim(None, m, "No steady turn: the tyres would slide")
            self.bars.set_parts({}, 0.0)
            self.messages.setHtml(html.escape(self.error))
            return
        self.c_lean.set(f"{math.degrees(t.lean):.1f}°")
        self.c_steer.set(f"{math.degrees(abs(t.steer)):.2f}° {'in' if t.steer >= 0 else 'out'}")
        self.c_hold.set(f"{abs(t.steering_torque):.1f} N m {'pull' if t.steering_torque > 0 else 'push'}")
        self.c_slip.set(f"{math.degrees(t.front.slip_angle):+.2f}° / {math.degrees(t.rear.slip_angle):+.2f}°")
        self.c_camber.set(f"{t.front.camber_share:.0%} / {t.rear.camber_share:.0%}")
        worst = max(t.front.grip_used, t.rear.grip_used)
        self.c_grip.set(f"{t.front.grip_used:.0%} / {t.rear.grip_used:.0%}", usage_colour(worst))
        self.c_drive.set(f"{t.rear.longitudinal_force:+.0f} N")
        self.view.set_trim(t, m)
        self.bars.set_parts(t.torque_parts, t.steering_torque)
        self.messages.setHtml("<br>".join(self._messages(t, m)))

    def _messages(self, t: Trim, m: TrimModel) -> list[str]:
        lines = []
        ideal = math.degrees(math.atan(t.lateral_g))
        lean = math.degrees(t.lean)
        lines.append(f"The motorcycle leans {lean:.1f}°, against {ideal:.1f}° for a thin-tyred point mass: the round "
                     "tyres move the contact patches towards the inside, the spinning wheels need a little extra lean, "
                     "and a rider off centre changes it.")
        torque = t.steering_torque
        if abs(torque) < 0.5:
            lines.append(f"The bars need almost no torque here ({torque:+.1f} N m): the turn holds itself.")
        else:
            pull = "would straighten up" if torque > 0 else "would turn further in"
            lines.append(f"You hold <b>{abs(torque):.1f} N m</b> on the bars, {hold_words(torque)}: left alone, the "
                         f"bars {pull}. The bar chart shows where it comes from.")
        kinematic = math.degrees(kinematic_steer(m, t.lean, math.atan(m.wheelbase / t.radius)))
        side = "into" if t.steer >= 0 else "out of"
        sentence = (f"The bars are turned {math.degrees(abs(t.steer)):.2f}° {side} the turn; tyres that did not slip "
                    f"would need {kinematic:.2f}° into it.")
        if t.rear.slip_angle > t.front.slip_angle:
            sentence += (" The rear tyre slips more than the front, so the motorcycle turns tighter than its steering "
                         "alone would make it")
            sentence += (": at this speed it holds the turn with the bars turned slightly out of it." if t.steer < 0
                         else "; at higher speeds the bars end up turned slightly out of the turn.")
        lines.append(sentence)
        lines.append(f"Camber gives about {t.front.camber_share:.0%} of the front tyre's side force and "
                     f"{t.rear.camber_share:.0%} of the rear's; slip makes up the rest.")
        for name, state in (("front", t.front), ("rear", t.rear)):
            angle = math.degrees(state.slip_angle)
            if angle >= 0:
                lines.append(f"The {name} tyre points {angle:.2f}° inside the way it is travelling.")
            else:
                lines.append(f"The {name} tyre points {-angle:.2f}° outside the way it is travelling: its camber "
                             "alone gives more side force than the turn asks of it.")
        if self.along.value() < 0:
            lines.append(f"Braking at {abs(self.along.value()):.2f} g: the front tyre's braking force acts inside the "
                         f"steering axis and turns the bars into the turn by {t.torque_parts['tyre_longitudinal']:.1f} "
                         "N m, so the motorcycle wants to stand up unless you push the inside grip harder.")
        worst = max(t.front.grip_used, t.rear.grip_used)
        if worst >= 0.8:
            lines.append(f"<span style='color:{AMBER.name()}'>Close to the limit: {worst:.0%} of a tyre's friction "
                         "circle is in use.</span>")
        if min(self.grip) < 1.0:
            lines.append(f"Tyres not yet warm: {self.grip[0]:.0%} / {self.grip[1]:.0%} of a warm tyre's grip.")
        return lines

    def _slow_results(self) -> None:
        m = self.model
        if m is None:
            return
        self.stale = False
        v_now = self.speed.value()
        try:
            self.limit_kmh = grip_limit_speed(m, self.radius.value(), acceleration=self.acceleration()) * 3.6
            self.c_limit.set(f"{self.limit_kmh:.0f} km/h")
        except BeyondGrip:
            self.limit_kmh = None
            self.c_limit.set("—")
        t = self.trim
        guides = [(v_now, AMBER, "now")]
        if t is None:
            for chart in (self.chart_torque, self.chart_steer, self.chart_slip):
                chart.set_data(1.0, [])
            return
        sweep = sweep_speed(m, t.lean, [s / 3.6 for s in CHART_SPEEDS], acceleration=self.acceleration())
        points = [(s, x) for s, x in zip(CHART_SPEEDS, sweep) if x is not None]
        xs = [s for s, _ in points]
        torque = [x.steering_torque for _, x in points]
        top = max(5.0, max((abs(y) for y in torque), default=0) * 1.15)
        self.chart_torque.set_range(-top, top)
        self.chart_torque.set_data(CHART_SPEEDS[-1], [Series("torque", CORAL, xs, torque)], [(0.0, GREY, "")],
                                   x_min=CHART_SPEEDS[0], vguides=guides)
        steer = [math.degrees(x.steer) for _, x in points]
        kinematic = [math.degrees(kinematic_steer(m, x.lean, math.atan(m.wheelbase / x.radius))) for _, x in points]
        top = max(3.0, 1.5 * abs(math.degrees(t.steer)))  # low speeds steer far more; keep the sign change readable
        self.chart_steer.set_range(-top / 3, top)
        self.chart_steer.set_data(CHART_SPEEDS[-1], [Series("steer", TEAL, xs, steer),
                                                     Series("no tyre slip", GREY, xs, kinematic, dashed=True)],
                                  [(0.0, GREY, "")], x_min=CHART_SPEEDS[0], vguides=guides)
        mu = peak_friction(m)
        gs = [0.1 * i for i in range(1, int(mu / 0.1) + 1)]
        by_g = sweep_lateral(m, v_now / 3.6, gs, acceleration=self.acceleration())
        rows = [(g, x) for g, x in zip(gs, by_g) if x is not None]
        front = [math.degrees(x.front.slip_angle) for _, x in rows]
        rear = [math.degrees(x.rear.slip_angle) for _, x in rows]
        high = max([1.0] + rear + front) * 1.15
        low = min([-0.5] + front + rear) * 1.15
        self.chart_slip.set_range(low, high)
        self.chart_slip.set_data(max(gs[-1], 0.1) if gs else 1.0,
                                 [Series("front", TEAL, [g for g, _ in rows], front),
                                  Series("rear", PURPLE, [g for g, _ in rows], rear)],
                                 [(0.0, GREY, "")], x_min=0.0, vguides=[(t.lateral_g, AMBER, "now")])
