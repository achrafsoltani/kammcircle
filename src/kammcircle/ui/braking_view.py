"""Animated side view of a braking run: the road scrolls under the motorcycle, the wheels turn or lock, the rear
lifts in a stoppie, and locked tyres leave marks. Facing left, as every side view in kammcircle."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QTransform
from PySide6.QtWidgets import QWidget

from .. import catalogue
from ..physics import trail_mm
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
        self.fork_offset = bike.fork_offset_mm
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
        # The motorcycle at the simulated pose: both models report their axles and frame points in world metres,
        # so the fork visibly shortens and the rear wheel moves when the suspended model is running.
        theta = math.degrees(sim.theta) if sim else 0.0

        def screen(world: tuple[float, float]) -> QPointF:
            return QPointF(sx(world[0]), ground_y - world[1] * 1000 * s)

        fork_m = FORK_LENGTH_MM / 1000
        rake = math.radians(self.rake)
        if sim:
            front_axle = screen(sim.front_axle_world())
            rear_axle = screen(sim.rear_axle_world())
            head = screen(sim.body_point_world(-fork_m * math.sin(rake), fork_m * math.cos(rake)))
        else:
            front_axle = QPointF(front_x, ground_y - self.front_r * s)
            rear_axle = QPointF(front_x + self.wheelbase * s, ground_y - self.rear_r * s)
            head = QPointF(front_x + FORK_LENGTH_MM * math.sin(rake) * s,
                           front_axle.y() - FORK_LENGTH_MM * math.cos(rake) * s)
        sump = sump_depth_mm(self.front_r, self.rake, self.clearance)
        frame = QTransform()
        frame.translate(head.x(), head.y())
        frame.rotate(-theta)
        frame.scale(s, s)
        pivot = frame.map(swingarm_pivot(sump))

        p.setPen(pen(GREY_DARK, 5))
        p.drawLine(pivot, rear_axle)
        angle_f = -math.degrees(sim.angle_f) if sim else 0.0
        angle_r = -math.degrees(sim.angle_r) if sim else 0.0
        draw_wheel(p, front_axle, self.front_r * s, angle_f, scale=s, locked=bool(sim and sim.locked_f))
        draw_wheel(p, rear_axle, self.rear_r * s, angle_r, scale=s, locked=bool(sim and sim.locked_r))
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
        accelerating = hasattr(sim, "acceleration_summary")
        p.drawText(QPointF(14, 54), (f"acceleration {-decel:.2f} g" if accelerating
                                     else f"deceleration {decel:.2f} g") + f"   ·   t = {sim.t:.2f} s")
        powertrain = getattr(sim, "powertrain", None)
        if accelerating:
            clutch = "" if powertrain.clutch_engaged else "   ·   clutch slipping"
            p.drawText(QPointF(14, 72), f"gear {powertrain.gear}   ·   {powertrain.rpm:.0f} rpm   ·   "
                                        f"{sim.x - sim.start[1]:.1f} m from the start{clutch}")
        else:
            parts = []
            if powertrain is not None:  # a stop in gear: engine braking
                parts.append(f"gear {powertrain.gear}, {powertrain.rpm:.0f} rpm, "
                             + ("clutch out" if powertrain.clutch_engaged else "clutch in"))
            if sim.brake_start:
                parts.append(f"{sim.x - sim.brake_start[1]:.1f} m since the first touch of a brake")
            if parts:
                p.drawText(QPointF(14, 72), "   ·   ".join(parts))

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
        front_up = sim.front_axle_world()[1] - self.front_r / 1000
        if front_up > 0.002:
            p.setPen(PURPLE)
            p.drawText(front_axle + QPointF(-self.front_r * s - 120, 0), f"front up {front_up * 1000:.0f} mm")
        if sim.rear_lift > 0.002:
            p.setPen(PURPLE)
            p.drawText(rear_axle + QPointF(self.rear_r * s + 6, 0), f"rear up {sim.rear_lift * 1000:.0f} mm")
        susp = getattr(sim, "susp", None)
        if susp is not None:
            rake_now = self.rake - math.degrees(sim.theta)
            trail_now = trail_mm(rake_now, self.front_r, self.fork_offset)
            p.setFont(label_font(self, 0.95))
            p.setPen(secondary)
            p.drawText(QPointF(14, 90), f"fork {max(0.0, sim.front_compression) * 1000:.0f} of {susp.front_travel * 1000:.0f} mm"
                                        f"   ·   rear {max(0.0, sim.rear_compression) * 1000:.0f} of {susp.rear_travel * 1000:.0f} mm"
                                        f"   ·   pitch {math.degrees(sim.theta):+.1f}°")
            p.drawText(QPointF(14, 108), f"steering now: rake {rake_now:.1f}°, trail {trail_now:.0f} mm "
                                         f"(standing: {self.rake:g}°, {trail_mm(self.rake, self.front_r, self.fork_offset):.0f} mm)")

        if sim.stopped and accelerating:
            s = sim.acceleration_summary()
            text, colour = {"reached": (f"{s['speed_kmh']:.0f} km/h in {s['time']:.2f} s", PURPLE),
                            "top speed": (f"Top speed {s['speed_kmh']:.0f} km/h", PURPLE),
                            "looped over": ("Looped over backwards: the wheelie passed the point of no return", RED),
                            }.get(s["outcome"], ("Time limit reached", GREY))
            p.setFont(label_font(self, 1.25, bold=True))
            p.setPen(colour)
            p.drawText(QRectF(0, 118, w, 26), Qt.AlignmentFlag.AlignHCenter, text)
        elif sim.stopped:
            summary = sim.summary()
            if summary.outcome == "pitched over":
                text, colour = "Over the front wheel: the rear rose past the point of no return", RED
            elif summary.outcome == "stopped":
                text, colour = f"Stopped in {summary.stopping_distance:.1f} m", PURPLE
            else:
                text, colour = "Time limit reached", GREY
            p.setFont(label_font(self, 1.25, bold=True))
            p.setPen(colour)
            p.drawText(QRectF(0, 118, w, 26), Qt.AlignmentFlag.AlignHCenter, text)
