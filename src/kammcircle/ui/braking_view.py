"""Animated side view of a braking run: the road scrolls under the motorcycle, the wheels turn or lock, the rear
lifts in a stoppie, and locked tyres leave marks. Facing left, as every side view in kammcircle."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QTransform
from PySide6.QtWidgets import QWidget

from .. import catalogue
from ..sim import BrakingSim
from .bike_drawing import FORK_LENGTH_MM, draw_frame, draw_wheel, sump_depth_mm, swingarm_pivot
from .style import AMBER, GREY, GREY_DARK, PURPLE, RED, TEAL, ink, label_font, pen


class BrakingView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 230)
        self.sim: BrakingSim | None = None
        self.hint = ""
        self.set_bike(catalogue.bikes()[0])

    def set_bike(self, bike: catalogue.Bike) -> None:
        self.wheelbase = bike.wheelbase_mm
        self.front_r = bike.front_wheel_radius_mm
        self.rear_r = bike.rear_wheel_radius_mm
        self.rake = bike.rake_deg
        self.clearance = bike.ground_clearance_mm
        self.update()

    def set_sim(self, sim: BrakingSim | None) -> None:
        self.sim = sim
        self.update()

    def set_hint(self, text: str) -> None:
        self.hint = text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        primary, secondary = ink(self)
        w, h = self.width(), self.height()
        sim = self.sim
        ground_y = h - 40.0
        s = min(0.46 * w / (self.wheelbase + self.front_r + self.rear_r), (ground_y - 60) / 1450)  # px per mm
        front_x = w * 0.30
        x_bike = sim.x if sim else 0.0

        def sx(world_x: float) -> float:
            return front_x - (world_x - x_bike) * 1000 * s

        # Road, distance markers from the first touch of a brake, and tyre marks.
        p.setPen(pen(secondary, 1.2))
        p.drawLine(QPointF(0, ground_y), QPointF(w, ground_y))
        origin = sim.brake_start[1] if sim and sim.brake_start else 0.0
        metres_visible = w / (1000 * s)
        first = math.floor((x_bike - metres_visible - origin) / 5)
        p.setFont(label_font(self, 0.8))
        for k in range(first, first + int(metres_visible / 5) + 3):
            x = sx(origin + 5 * k)
            if -40 < x < w + 40:
                p.setPen(pen(secondary, 1))
                p.drawLine(QPointF(x, ground_y), QPointF(x, ground_y + 6))
                if sim and sim.brake_start and k >= 0:
                    p.drawText(QRectF(x - 30, ground_y + 8, 60, 14), Qt.AlignmentFlag.AlignHCenter, f"{5 * k} m")
        if sim:
            mark = QColor(primary)
            mark.setAlphaF(0.55)
            p.setPen(pen(mark, 3))
            for intervals, current in ((sim.skids_f, sim.x), (sim.skids_r, sim.rear_contact_x)):
                for start, end in intervals:
                    a, b = sx(start), sx(current if end is None else end)
                    p.drawLine(QPointF(a, ground_y - 1.5), QPointF(b, ground_y - 1.5))

        # The motorcycle, pitched about the front axle by the simulated angle.
        theta = math.degrees(sim.theta) if sim else 0.0
        body = QTransform()
        body.translate(front_x, ground_y - self.front_r * s)
        body.rotate(-theta)
        body.scale(s, s)
        head_mm = QPointF(FORK_LENGTH_MM * math.sin(math.radians(self.rake)),
                          -FORK_LENGTH_MM * math.cos(math.radians(self.rake)))
        sump = sump_depth_mm(self.front_r, self.rake, self.clearance)
        rear_axle_mm = QPointF(self.wheelbase, self.front_r - self.rear_r)
        front_axle, rear_axle = body.map(QPointF(0, 0)), body.map(rear_axle_mm)
        head = body.map(head_mm)
        pivot = body.map(head_mm + swingarm_pivot(sump))

        p.setPen(pen(GREY_DARK, 5))
        p.drawLine(pivot, rear_axle)
        angle_f = -math.degrees(sim.angle_f) if sim else 0.0
        angle_r = -math.degrees(sim.angle_r) if sim else 0.0
        draw_wheel(p, front_axle, self.front_r * s, angle_f, scale=s, locked=bool(sim and sim.locked_f))
        draw_wheel(p, rear_axle, self.rear_r * s, angle_r, scale=s, locked=bool(sim and sim.locked_r))
        frame = QTransform(body)
        frame.translate(head_mm.x(), head_mm.y())
        p.save()
        p.setTransform(frame, True)
        draw_frame(p, sump)
        p.restore()
        p.setPen(pen(GREY_DARK, 4))
        p.drawLine(front_axle, head)

        if sim:
            self._overlay(p, sim, primary, secondary, front_axle, rear_axle, s)
        elif self.hint:
            p.setPen(secondary)
            p.setFont(label_font(self, 1.0))
            p.drawText(QRectF(0, 8, w, 22), Qt.AlignmentFlag.AlignHCenter, self.hint)
        p.end()

    def _overlay(self, p: QPainter, sim: BrakingSim, primary, secondary, front_axle, rear_axle, s) -> None:
        w = self.width()
        p.setFont(label_font(self, 1.9, bold=True))
        p.setPen(primary)
        p.drawText(QPointF(14, 34), f"{sim.v * 3.6:.0f} km/h")
        p.setFont(label_font(self, 0.95))
        p.setPen(secondary)
        decel = -sim.a / sim.p.g
        p.drawText(QPointF(14, 54), f"deceleration {decel:.2f} g   ·   t = {sim.t:.2f} s")
        if sim.brake_start:
            p.drawText(QPointF(14, 72), f"{sim.x - sim.brake_start[1]:.1f} m since the first touch of a brake")

        for i, (name, channel) in enumerate((("ABS front", sim.abs_f), ("ABS rear", sim.abs_r))):
            box = QRectF(w - 190 + i * 92, 12, 84, 22)
            if not channel.enabled:
                p.setPen(pen(GREY, 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                label_colour = GREY
            elif channel.intervening:
                p.setPen(pen(AMBER, 1.5))
                p.setBrush(QBrush(AMBER))
                label_colour = QColor("white")
            else:
                p.setPen(pen(TEAL, 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                label_colour = TEAL
            p.drawRoundedRect(box, 5, 5)
            p.setPen(label_colour)
            p.setFont(label_font(self, 0.85, bold=True))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, name if channel.enabled else f"{name} off")

        p.setFont(label_font(self, 0.9, bold=True))
        if sim.locked_f and sim.v > 0.5:
            p.setPen(RED)
            p.drawText(front_axle + QPointF(-30, -self.front_r * s - 10), "LOCKED")
        if sim.locked_r and sim.v > 0.5:
            p.setPen(RED)
            p.drawText(rear_axle + QPointF(-30, -self.rear_r * s - 10), "LOCKED")
        if sim.theta > 0:
            p.setPen(PURPLE)
            p.drawText(rear_axle + QPointF(self.rear_r * s + 6, 0), f"rear up {sim.rear_lift * 1000:.0f} mm")

        if sim.stopped:
            summary = sim.summary()
            if summary.outcome == "pitched over":
                text, colour = "Over the front wheel: the rear rose past the point of no return", RED
            elif summary.outcome == "stopped":
                text, colour = f"Stopped in {summary.stopping_distance:.1f} m", PURPLE
            else:
                text, colour = "Time limit reached", GREY
            p.setFont(label_font(self, 1.25, bold=True))
            p.setPen(colour)
            p.drawText(QRectF(0, 84, w, 26), Qt.AlignmentFlag.AlignHCenter, text)
