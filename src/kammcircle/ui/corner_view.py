"""Top view of a corner ridden in time: the planned line, both wheels' tracks and the motorcycle, with two insets,
the motorcycle seen from behind and the handlebars seen from above with the steer angle magnified."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPolygonF
from PySide6.QtWidgets import QWidget

from ..sim.countersteer import CornerSim
from .charts import nice_step
from .style import CORAL, GREY, GREY_DARK, PURPLE, TEAL, arrow, ink, label_font, pen, polar

STEER_MAGNIFY = 10.0
INSET_W, INSET_H = 150.0, 118.0


def planned_line(sim: CornerSim) -> list[tuple[float, float]]:
    """The line the corner is drawn on: straight to where the rider starts the turn, the arc, then straight."""
    c = sim.corner
    x0, radius, d, angle = sim.v * c.approach, c.radius, c.direction, math.radians(c.angle_deg)
    points = [(0.0, 0.0), (x0, 0.0)]
    for i in range(1, 91):
        a = angle * i / 90
        points.append((x0 + radius * math.sin(a), d * radius * (1 - math.cos(a))))
    end = points[-1]
    run_out = max(25.0, 0.3 * radius)
    points.append((end[0] + run_out * math.cos(angle), end[1] + d * run_out * math.sin(angle)))
    return points


class CornerView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 220)
        self.sim: CornerSim | None = None
        self.planned: list[tuple[float, float]] = []
        self.hint = ""

    def set_sim(self, sim: CornerSim | None) -> None:
        self.sim = sim
        self.planned = planned_line(sim) if sim is not None else []
        self.update()

    def set_hint(self, text: str) -> None:
        self.hint = text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        primary, secondary = ink(self)
        sim = self.sim
        if sim is None:
            p.setPen(secondary)
            p.setFont(label_font(self, 1.0))
            p.drawText(self.rect().adjusted(20, 20, -20, -20), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       self.hint)
            p.end()
            return
        self._top_view(p, sim, primary, secondary)
        top = 30.0
        self._rear_inset(p, sim, primary, secondary, QRectF(8, top, INSET_W, INSET_H))
        self._bars_inset(p, sim, primary, secondary, QRectF(self.width() - INSET_W - 8, top, INSET_W, INSET_H))
        p.end()

    # ─── the corner from above ───────────────────────────────────────────────

    def _top_view(self, p: QPainter, sim: CornerSim, primary, secondary) -> None:
        trace = sim.trace
        xs = [x for x, _ in self.planned] + [s.x for s in trace] + [s.fx for s in trace]
        ys = [y for _, y in self.planned] + [s.y for s in trace] + [s.fy for s in trace]
        x_lo, x_hi, y_lo, y_hi = min(xs), max(xs), min(ys), max(ys)
        margin_top, margin_side, margin_bottom = 34.0, INSET_W + 22.0, 12.0  # the insets sit either side
        width, height = self.width() - 2 * margin_side, self.height() - margin_top - margin_bottom
        scale = min(width / max(y_hi - y_lo, 1.0), height / max(x_hi - x_lo, 1.0))
        left = margin_side + (width - (y_hi - y_lo) * scale) / 2
        bottom = self.height() - margin_bottom - (height - (x_hi - x_lo) * scale) / 2

        def screen(x: float, y: float) -> QPointF:  # x forward is up the screen, y to the right is right
            return QPointF(left + (y - y_lo) * scale, bottom - (x - x_lo) * scale)

        p.setPen(pen(GREY, 1.2, Qt.PenStyle.DashLine))
        p.drawPolyline(QPolygonF([screen(x, y) for x, y in self.planned]))
        if len(trace) > 1:
            p.setPen(pen(TEAL, 1.2))
            p.drawPolyline(QPolygonF([screen(s.fx, s.fy) for s in trace]))
            p.setPen(pen(PURPLE, 2.0))
            p.drawPolyline(QPolygonF([screen(s.x, s.y) for s in trace]))
        s = sim.state
        rear = screen(s[6], s[7])
        fx, fy = sim.front_contact()
        front = screen(fx, fy)
        if math.hypot(front.x() - rear.x(), front.y() - rear.y()) < 14:  # keep the motorcycle visible when zoomed out
            psi = s[5]
            front = QPointF(rear.x() + 14 * math.sin(psi), rear.y() - 14 * math.cos(psi))
        p.setPen(pen(primary, 4.0))
        p.drawLine(rear, front)
        p.setBrush(QBrush(primary))
        p.drawEllipse(front, 2.5, 2.5)
        p.setBrush(Qt.BrushStyle.NoBrush)

        p.setFont(label_font(self, 0.85))
        items = ((GREY, Qt.PenStyle.DashLine, "planned line"), (PURPLE, Qt.PenStyle.SolidLine, "rear wheel"),
                 (TEAL, Qt.PenStyle.SolidLine, "front wheel"))
        x0 = 12.0
        for colour, style, text in items:
            p.setPen(pen(colour, 2, style))
            p.drawLine(QPointF(x0, 16), QPointF(x0 + 18, 16))
            p.setPen(secondary)
            p.drawText(QPointF(x0 + 23, 20), text)
            x0 += 32 + p.fontMetrics().horizontalAdvance(text)
        bar = nice_step((self.width() / 6) / scale, 1)
        bar_px = bar * scale
        p.setPen(pen(secondary, 1.5))
        right, y = self.width() - 14.0, self.height() - 26.0
        p.drawLine(QPointF(right - bar_px, y), QPointF(right, y))
        p.drawLine(QPointF(right - bar_px, y - 4), QPointF(right - bar_px, y + 4))
        p.drawLine(QPointF(right, y - 4), QPointF(right, y + 4))
        p.drawText(QRectF(right - bar_px - 80, y + 4, bar_px + 80, 16), Qt.AlignmentFlag.AlignRight, f"{bar:g} m")

    # ─── insets ──────────────────────────────────────────────────────────────

    def _inset_frame(self, p: QPainter, rect: QRectF, title: str, secondary) -> None:
        background = self.palette().color(self.backgroundRole())
        p.setBrush(QBrush(background))
        p.setPen(pen(secondary, 0.8))
        p.drawRoundedRect(rect, 6, 6)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setFont(label_font(self, 0.8))
        p.setPen(secondary)
        p.drawText(QRectF(rect.left() + 6, rect.top() + 3, rect.width() - 12, 14), Qt.AlignmentFlag.AlignLeft, title)

    def _rear_inset(self, p: QPainter, sim: CornerSim, primary, secondary, rect: QRectF) -> None:
        self._inset_frame(p, rect, "From behind", secondary)
        lean = math.degrees(sim.state[0])
        ground_y = rect.bottom() - 22
        contact = QPointF(rect.center().x(), ground_y)
        p.setPen(pen(GREY_DARK, 1.2))
        p.drawLine(QPointF(rect.left() + 12, ground_y), QPointF(rect.right() - 12, ground_y))
        p.setPen(pen(GREY, 1, Qt.PenStyle.DotLine))
        p.drawLine(contact, QPointF(contact.x(), rect.top() + 22))
        top = polar(contact, 72, lean)
        p.setPen(pen(GREY_DARK, 7))
        p.drawLine(contact, polar(contact, 30, lean))
        p.setPen(pen(primary, 3))
        p.drawLine(polar(contact, 30, lean), top)
        p.setBrush(QBrush(PURPLE))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(polar(contact, 60, lean), 5, 5)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(secondary)
        p.setFont(label_font(self, 0.8))
        side = "right" if lean > 0.05 else "left" if lean < -0.05 else ""
        p.drawText(QRectF(rect.left(), ground_y + 3, rect.width(), 16), Qt.AlignmentFlag.AlignHCenter,
                   f"lean {abs(lean):.1f}° {side}".rstrip())

    def _bars_inset(self, p: QPainter, sim: CornerSim, primary, secondary, rect: QRectF) -> None:
        self._inset_frame(p, rect, f"Bars from above, steer ×{STEER_MAGNIFY:g}", secondary)
        steer, torque = math.degrees(sim.state[1]), sim.state[4]
        centre = QPointF(rect.center().x(), rect.center().y() + 4)
        half = 46.0
        a = math.radians(steer * STEER_MAGNIFY)  # steering right turns the bars clockwise seen from above
        dx, dy = half * math.cos(a), half * math.sin(a)
        left, right = QPointF(centre.x() - dx, centre.y() - dy), QPointF(centre.x() + dx, centre.y() + dy)
        p.setPen(pen(GREY, 1, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(centre.x() - half, centre.y()), QPointF(centre.x() + half, centre.y()))
        p.setPen(pen(primary, 3))
        p.drawLine(left, right)
        p.setBrush(QBrush(GREY_DARK))
        p.drawEllipse(centre, 4, 4)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if abs(torque) > 0.2:
            grip = right if torque < 0 else left  # a torque urging the bars left is a push on the right grip
            length = min(34.0, 6 + 2.0 * abs(torque))
            arrow(p, QPointF(grip.x(), grip.y() + length / 2), QPointF(grip.x(), grip.y() - length / 2), CORAL, 2.0)
        p.setFont(label_font(self, 0.8))
        p.setPen(secondary)
        side = "right" if steer > 0.005 else "left" if steer < -0.005 else ""
        text = f"steer {abs(steer):.2f}° {side}".rstrip()
        if abs(torque) > 0.2:
            text += f", push {'right' if torque < 0 else 'left'} grip {abs(torque):.1f} N m"
        p.drawText(QRectF(rect.left() + 4, rect.bottom() - 30, rect.width() - 8, 28),
                   Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, text)
