"""Views of the steady turn on the tyre model: the motorcycle from above, with each contact patch's direction of travel
and side force, and where the torque on the handlebars comes from."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPolygonF
from PySide6.QtWidgets import QWidget

from ..sim.steady_turn import Trim, TrimModel
from .style import CORAL, GREY, GREY_DARK, GREY_LIGHT, PURPLE, TEAL, arrow, ink, label_font, pen

TORQUE_LABELS = {
    "tyre_load": "Front tyre's load, beside the steering axis",
    "tyre_side": "Front tyre's side force, behind the axis (trail)",
    "tyre_moment": "Front tyre's twisting and aligning moment",
    "tyre_longitudinal": "Front tyre's drag or braking force",
    "gyroscopic": "Front wheel's gyroscopic moment",
    "weight": "Weight of the fork, wheel and bars",
    "inertia": "Their cornering inertia",
}


def exaggeration(*angles: float) -> int:
    """A round factor that makes the largest of these angles (rad) visible without passing about 30°."""
    largest = max((abs(a) for a in angles), default=0.0)
    for factor in (10, 5, 2):
        if largest * factor <= math.radians(30):
            return factor
    return 1


class TrimView(QWidget):
    """The motorcycle from above, heading up the screen, in a right-hand turn; angles exaggerated and labelled so."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 260)
        self.trim: Trim | None = None
        self.model: TrimModel | None = None
        self.message = ""

    def set_trim(self, trim: Trim | None, model: TrimModel | None, message: str = "") -> None:
        self.trim, self.model, self.message = trim, model, message
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        primary, secondary = ink(self)
        w, h = self.width(), self.height()
        p.setFont(label_font(self, 0.85))
        trim, m = self.trim, self.model
        if trim is None or m is None or trim.pose is None:
            p.setPen(secondary)
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self.message or "No steady turn")
            return
        ps = trim.pose
        k = exaggeration(trim.ground_steer, trim.front.slip_angle, trim.rear.slip_angle)
        wheelbase = m.wheelbase
        length = wheelbase + m.rear.radius + m.front.radius  # rear tyre's back to front tyre's front
        scale = min((h - 40) / length, 0.22 * w / max(m.rear.radius, 0.2))
        rear = QPointF(0.45 * w, h - 8 - m.rear.radius * scale)

        def screen(x: float, y: float) -> QPointF:  # SAE x forward, y right → screen
            return QPointF(rear.x() + y * scale, rear.y() - x * scale)

        def direction(angle: float, length: float, start: QPointF) -> QPointF:  # angle + to the right of forward
            return QPointF(start.x() + length * math.sin(angle), start.y() - length * math.cos(angle))

        front = screen(ps.front_contact[0], ps.front_contact[1])
        heading_f = k * trim.ground_steer

        # the frame and the centre of mass
        p.setPen(pen(GREY_LIGHT, 3))
        p.drawLine(rear, front)
        masses = [(m.rear_body.mass, ps.rear_cog), (m.front_body.mass, ps.front_cog), (m.rear.mass, ps.rear_hub),
                  (m.front.mass, ps.front_hub)]
        cog = [sum(mass * q[i] for mass, q in masses) / m.mass for i in range(2)]
        c = screen(cog[0], cog[1])
        p.setPen(pen(PURPLE, 1.5))
        p.setBrush(PURPLE)
        p.drawEllipse(c, 4, 4)
        p.setBrush(Qt.BrushStyle.NoBrush)

        def wheel(centre: QPointF, angle: float, radius: float, crown: float) -> None:
            half_l, half_w = radius * scale, max(crown * scale, 3.0)
            ca, sa = math.cos(angle), math.sin(angle)
            corners = [(-half_w, -half_l), (half_w, -half_l), (half_w, half_l), (-half_w, half_l)]
            poly = QPolygonF([QPointF(centre.x() + x * ca - y * sa, centre.y() + x * sa + y * ca) for x, y in corners])
            p.setPen(pen(GREY_DARK, 1.5))
            p.setBrush(GREY_LIGHT)
            p.drawPolygon(poly)
            p.setBrush(Qt.BrushStyle.NoBrush)

        wheel(rear, 0.0, m.rear.radius, m.rear.crown)
        wheel(front, heading_f, m.front.radius, m.front.crown)

        reach = 0.42 * wheelbase * scale
        for point, heading, state in ((rear, 0.0, trim.rear), (front, heading_f, trim.front)):
            travel = heading - k * state.slip_angle
            room = (point.y() - 26) / max(math.cos(travel), 0.2)  # keep clear of the title line
            arrow(p, point, direction(travel, min(reach, room), point), GREY, 1.6)
            # side force, split into the part camber provides and the part slip adds
            weight = m.mass * m.g
            unit = 0.9 * reach / max(0.3 * weight, 1.0)
            camber_part = state.side_force * state.camber_share
            slip_part = state.side_force - camber_part
            side = heading + math.pi / 2
            mid = direction(side, camber_part * unit, point)
            if abs(camber_part) * unit > 2:
                arrow(p, point, mid, TEAL, 2.2)
            if abs(slip_part) * unit > 2:
                arrow(p, mid, direction(side, slip_part * unit, mid), CORAL, 2.2)

        p.setPen(secondary)
        p.drawText(QPointF(8, 16), f"From above, right-hand turn of {trim.radius:.0f} m; angles drawn ×{k}")
        p.setPen(pen(GREY, 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(rear.x() + 40, rear.y()), QPointF(w - 10, rear.y()))
        p.setPen(secondary)
        p.drawText(QPointF(w - 120, rear.y() - 6), "to the turn centre")
        y = 36.0
        x0 = w - 190
        for colour, text in ((GREY, "path of each contact patch"), (TEAL, "side force from camber"),
                             (CORAL, "side force from slip")):
            p.setPen(pen(colour, 2.2))
            p.drawLine(QPointF(x0, y), QPointF(x0 + 18, y))
            p.setPen(secondary)
            p.drawText(QPointF(x0 + 24, y + 4), text)
            y += 15
        p.setPen(primary)
        for point, name, state in ((front, "front", trim.front), (rear, "rear", trim.rear)):
            text = f"{name}: slip {math.degrees(state.slip_angle):+.2f}°"
            p.drawText(QRectF(point.x() - 200, point.y() - 8, 186, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)
        p.end()


class TorqueBars(QWidget):
    """What each load does to the handlebars about the steering axis, and the torque the rider holds against it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 220)
        self.parts: dict[str, float] = {}
        self.torque = 0.0

    def set_parts(self, parts: dict[str, float], torque: float) -> None:
        self.parts, self.torque = dict(parts), torque
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        primary, secondary = ink(self)
        w, h = self.width(), self.height()
        p.setFont(label_font(self, 0.85))
        p.setPen(primary)
        p.drawText(QPointF(8, 16), "Torque on the bars, N m (+ turns them into the turn)")
        if not self.parts:
            return
        rows = [(TORQUE_LABELS[k], v, GREY_DARK) for k, v in self.parts.items()]
        rows.append(("The bars' own pull (sum)", sum(self.parts.values()), PURPLE))
        rows.append(("You hold", self.torque, CORAL))
        metrics = p.fontMetrics()
        label_w = max(metrics.horizontalAdvance(text) for text, _, _ in rows) + 12
        top, row_h = 28.0, max(15.0, (h - 36) / len(rows))
        room = 50.0  # for the value written beyond each bar's end
        span = max(20.0, 0.5 * (w - label_w - 2 * room))
        zero = label_w + room + span
        largest = max(1.0, max(abs(v) for _, v, _ in rows))
        p.setPen(pen(GREY, 1, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(zero, top - 4), QPointF(zero, top + row_h * len(rows)))
        for i, (text, value, colour) in enumerate(rows):
            y = top + i * row_h
            p.setPen(primary if colour is not GREY_DARK else secondary)
            p.drawText(QRectF(4, y, label_w - 8, row_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       text)
            length = span * value / largest
            bar = QRectF(min(zero, zero + length), y + 0.2 * row_h, abs(length), 0.6 * row_h)
            p.fillRect(bar, colour)
            p.setPen(primary)
            anchor = zero + length + (4 if value >= 0 else -4)
            align = Qt.AlignmentFlag.AlignLeft if value >= 0 else Qt.AlignmentFlag.AlignRight
            box = QRectF(anchor, y, 60, row_h) if value >= 0 else QRectF(anchor - 60, y, 60, row_h)
            p.drawText(box, align | Qt.AlignmentFlag.AlignVCenter, f"{value:+.1f}")
        p.end()
