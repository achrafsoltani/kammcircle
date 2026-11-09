"""QPainter views: rear view of the lean, the friction circle, the side view of the steering geometry and the
rear view of the rider's position. Conventions from docs/illustrations.md: rear views lean right for a
right-hand bend; the side view faces left."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QTransform
from PySide6.QtWidgets import QWidget

from .bike_drawing import FORK_LENGTH_MM, draw_frame, draw_wheel, sump_depth_mm, swingarm_pivot
from .style import (
    CORAL,
    GREY,
    GREY_DARK,
    PURPLE,
    RED,
    TEAL,
    arrow,
    ink,
    label_font,
    pen,
    polar,
    usage_colour,
)

MAX_DRAWN_LEAN = 75.0


def _angle_arc(painter: QPainter, centre: QPointF, radius: float, lean_deg: float) -> None:
    """Arc from vertical to a line leaning ``lean_deg`` to the right (Qt angles: anticlockwise from 3 o'clock)."""
    rect = QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius)
    painter.drawArc(rect, 90 * 16, int(-lean_deg * 16))


def _legend(painter: QPainter, widget: QWidget, items: list[tuple], x: float = 12, y: float = 18) -> None:
    _, secondary = ink(widget)
    painter.setFont(label_font(widget, 0.9))
    for i, (colour, width, style, text) in enumerate(items):
        yy = y + i * 18
        painter.setPen(pen(colour, width, style))
        painter.drawLine(QPointF(x, yy), QPointF(x + 22, yy))
        painter.setPen(secondary)
        painter.drawText(QPointF(x + 30, yy + 4), text)


class LeanView(QWidget):
    """Rear view of the bike at the lean the corner needs, with the grip limit and the forces at the tyre."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(280, 260)
        self.effective_lean = 0.0
        self.wheel_lean = 0.0
        self.limit = 45.0
        self.usage = 0.0
        self.crown_mm = 0.0
        self.cog_mm = 680.0

    def set_state(
        self, *, effective_lean_deg: float, wheel_lean_deg: float, limit_deg: float, usage: float,
        crown_radius_mm: float, cog_height_mm: float,
    ) -> None:
        self.effective_lean = effective_lean_deg
        self.wheel_lean = wheel_lean_deg
        self.limit = limit_deg
        self.usage = usage
        self.crown_mm = crown_radius_mm
        self.cog_mm = cog_height_mm
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        primary, secondary = ink(self)
        w, h = self.width(), self.height()
        ground_y = h - 30.0
        contact = QPointF(w * 0.36, ground_y)
        usable = ground_y - 70.0
        scale = usable / 1250.0  # px per mm

        p.setPen(pen(secondary, 1))
        p.drawLine(QPointF(10, ground_y), QPointF(w - 10, ground_y))
        p.setPen(pen(secondary, 0.8, Qt.PenStyle.DotLine))
        p.drawLine(contact, QPointF(contact.x(), ground_y - usable))

        p.setPen(pen(RED, 1.5, Qt.PenStyle.DashLine))
        p.drawLine(contact, polar(contact, usable, min(self.limit, MAX_DRAWN_LEAN)))

        wheel = min(self.wheel_lean, MAX_DRAWN_LEAN)
        t = self.crown_mm * scale
        crown = QPointF(contact.x(), ground_y - t)
        p.setPen(pen(GREY, 10))
        p.drawLine(polar(crown, -t, wheel), polar(crown, 1150 * scale - t, wheel))
        if t > 0.5:
            p.setPen(pen(GREY_DARK, 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(crown, t, t)

        cog = polar(crown, (self.cog_mm - self.crown_mm) * scale, wheel)
        p.setPen(pen(PURPLE, 1, Qt.PenStyle.DashLine))
        p.drawLine(contact, cog)

        n_len = usable * 0.36
        f_len = min(n_len * math.tan(math.radians(min(self.effective_lean, MAX_DRAWN_LEAN))), w * 0.55)
        arrow(p, contact, QPointF(contact.x(), ground_y - n_len), TEAL)
        arrow(p, contact, QPointF(contact.x() + f_len, ground_y), CORAL)
        arrow(p, contact, QPointF(contact.x() + f_len, ground_y - n_len), PURPLE, 2.5)
        arrow(p, cog, QPointF(cog.x(), cog.y() + n_len * 0.45), secondary, 1.5)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(PURPLE))
        p.drawEllipse(cog, 5, 5)

        p.setFont(label_font(self, 0.95))
        p.setPen(TEAL)
        p.drawText(QPointF(contact.x() - 18, ground_y - n_len + 4), "N")
        p.setPen(CORAL)
        p.drawText(QPointF(contact.x() + f_len - 4, ground_y + 18), "F")
        p.setPen(secondary)
        p.drawText(QPointF(cog.x() + 8, cog.y() + n_len * 0.45), "mg")

        p.setPen(pen(primary, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        _angle_arc(p, crown, 46, wheel)
        p.setFont(label_font(self, 1.0, bold=True))
        p.drawText(polar(crown, 58, wheel / 2) + QPointF(-4, 0), f"{self.wheel_lean:.1f}°")
        if self.usage >= 1.0:
            p.setPen(RED)
            p.drawText(polar(contact, usable * 0.98, min(self.limit, MAX_DRAWN_LEAN)) + QPointF(6, 0), "slides")

        _legend(p, self, [
            (GREY, 6, Qt.PenStyle.SolidLine, "wheel plane"),
            (RED, 1.5, Qt.PenStyle.DashLine, "grip limit"),
            (PURPLE, 2.5, Qt.PenStyle.SolidLine, "road force N + F"),
        ])
        p.end()


class FrictionCircleView(QWidget):
    """Kamm's circle: cornering and braking share one grip budget of radius μ."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(240, 240)
        self.lat = 0.0
        self.brake = 0.0
        self.mu = 1.0

    def set_state(self, *, lat_g: float, brake_g: float, mu: float) -> None:
        self.lat, self.brake, self.mu = lat_g, brake_g, mu
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        primary, secondary = ink(self)
        w, h = self.width(), self.height()
        centre = QPointF(w / 2, h / 2 + 8)
        k = (min(w, h - 16) / 2 - 14) / 1.35  # px per g

        p.setPen(pen(secondary, 0.8))
        p.drawLine(QPointF(centre.x() - 1.35 * k, centre.y()), QPointF(centre.x() + 1.35 * k, centre.y()))
        p.drawLine(QPointF(centre.x(), centre.y() - 1.35 * k), QPointF(centre.x(), centre.y() + 1.35 * k))
        p.setPen(pen(secondary, 0.8, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(centre, k, k)
        p.setPen(pen(TEAL, 2))
        p.drawEllipse(centre, self.mu * k, self.mu * k)

        usage = math.hypot(self.lat, self.brake) / self.mu
        colour = usage_colour(usage)
        tip = QPointF(centre.x() + min(self.lat, 1.35) * k, centre.y() + min(self.brake, 1.35) * k)
        p.setPen(pen(primary, 1.5))
        p.drawLine(centre, tip)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(colour))
        p.drawEllipse(tip, 6, 6)

        p.setFont(label_font(self, 0.9))
        p.setPen(secondary)
        p.drawText(polar(centre, k + 12, 45) + QPointF(-6, 0), "1 g")
        p.setPen(TEAL)
        p.drawText(polar(centre, self.mu * k - 4, -45) + QPointF(-44, -4), f"μ {self.mu:.2f}")
        p.setPen(secondary)
        p.drawText(QRectF(0, 2, w - 6, 16), Qt.AlignmentFlag.AlignRight, "→ cornering g · ↓ braking g")
        p.end()


class GeometryView(QWidget):
    """Side view (facing left) of the front end: rake, trail and ground clearance after lowering."""

    EXAGGERATION = 5.0
    FORK_LENGTH_MM = FORK_LENGTH_MM

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 250)
        self.stock_rake = 26.0
        self.rake = 26.0
        self.pitch = 0.0
        self.trail = 124.0
        self.clearance = 230.0
        self.stock_clearance = 230.0
        self.front_drop = 0.0
        self.wheelbase = 1510.0
        self.front_radius = 347.7
        self.rear_radius = 327.9

    def set_state(
        self, *, stock_rake_deg: float, rake_deg: float, pitch_deg: float, trail_mm: float,
        ground_clearance_mm: float, stock_ground_clearance_mm: float, front_drop_mm: float,
        wheelbase_mm: float, front_radius_mm: float, rear_radius_mm: float,
    ) -> None:
        self.stock_rake, self.rake, self.pitch, self.trail = stock_rake_deg, rake_deg, pitch_deg, trail_mm
        self.clearance, self.stock_clearance = ground_clearance_mm, stock_ground_clearance_mm
        self.front_drop, self.wheelbase = front_drop_mm, wheelbase_mm
        self.front_radius, self.rear_radius = front_radius_mm, rear_radius_mm
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        primary, secondary = ink(self)
        w, h = self.width(), self.height()
        ground_y = h - 46.0
        s = min((w - 70) / (self.wheelbase + self.front_radius + self.rear_radius), (ground_y - 30) / 1150)
        fx = 35 + self.front_radius * s
        rx = fx + self.wheelbase * s
        front_axle = QPointF(fx, ground_y - self.front_radius * s)
        rear_axle = QPointF(rx, ground_y - self.rear_radius * s)

        k = self.EXAGGERATION
        drawn_pitch = k * self.pitch
        drawn_rake = self.stock_rake + drawn_pitch
        fork_px = (self.FORK_LENGTH_MM - k * self.front_drop) * s
        head = polar(front_axle, fork_px, drawn_rake)

        # The frame is drawn in millimetres relative to the steering head, placed so that the sump guard sits at
        # the stock ground clearance, then pitched with the chassis.
        sump = sump_depth_mm(self.front_radius, self.stock_rake, self.stock_clearance)
        frame = QTransform()
        frame.translate(head.x(), head.y())
        frame.rotate(drawn_pitch)
        frame.scale(s, s)

        def at(x: float, y: float) -> QPointF:
            return frame.map(QPointF(x, y))

        p.setPen(pen(secondary, 1))
        p.drawLine(QPointF(8, ground_y), QPointF(w - 8, ground_y))

        for centre, radius in ((front_axle, self.front_radius), (rear_axle, self.rear_radius)):
            draw_wheel(p, centre, radius * s, None, scale=s)

        pivot = frame.map(swingarm_pivot(sump))
        p.setPen(pen(GREY_DARK, 5))
        p.drawLine(pivot, rear_axle)
        p.save()
        p.setTransform(frame, True)
        draw_frame(p, sump)
        p.restore()

        if abs(drawn_rake - self.stock_rake) > 0.05:
            stock_top = polar(front_axle, self.FORK_LENGTH_MM * s + 40, self.stock_rake)
            stock_hit = QPointF(
                front_axle.x() - (ground_y - front_axle.y()) * math.tan(math.radians(self.stock_rake)), ground_y
            )
            p.setPen(pen(GREY, 1, Qt.PenStyle.DashLine))
            p.drawLine(stock_top, stock_hit)
            p.setFont(label_font(self, 0.85))
            p.setPen(secondary)
            p.drawText(stock_top + QPointF(-70, -4), "stock axis")

        p.setPen(pen(PURPLE, 3))
        p.drawLine(front_axle, head)
        tan_r = math.tan(math.radians(drawn_rake))
        ground_hit = QPointF(front_axle.x() - (ground_y - front_axle.y()) * tan_r, ground_y)
        top = polar(head, 40, drawn_rake)
        p.setPen(pen(PURPLE, 1.2, Qt.PenStyle.DashLine))
        p.drawLine(top, ground_hit)
        p.setPen(pen(secondary, 0.8, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(ground_hit.x(), ground_y), QPointF(ground_hit.x(), ground_y - 90))

        contact = QPointF(front_axle.x(), ground_y)
        p.setPen(pen(TEAL, 4))
        p.drawLine(ground_hit, contact)

        guard = at(370, sump)
        p.setPen(pen(CORAL, 1.5, Qt.PenStyle.DashLine))
        p.drawLine(guard, QPointF(guard.x(), ground_y))

        p.setFont(label_font(self, 0.95, bold=True))
        p.setPen(PURPLE)
        p.drawText(top + QPointF(8, 4), f"rake {self.rake:.1f}°")
        p.setPen(TEAL)
        p.drawText(QPointF(min(ground_hit.x(), contact.x()) - 6, ground_y + 18), f"trail {self.trail:.0f} mm")
        p.setPen(CORAL)
        p.drawText(QPointF(guard.x() + 6, (guard.y() + ground_y) / 2 + 4), f"≈ {self.clearance:.0f} mm")

        p.setFont(label_font(self, 0.85))
        p.setPen(secondary)
        p.drawText(QRectF(8, h - 22, w - 16, 18), Qt.AlignmentFlag.AlignLeft,
                   "Side view, facing left. Angle changes are drawn ×5; the numbers are real.")
        p.end()


class BodyPositionView(QWidget):
    """Rear view: the bike's lean under a rider who moves off the bike's plane, for a fixed combined lean."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(280, 260)
        self.combined = 30.0
        self.bike_lean = 30.0
        self.bike_cog = 550.0
        self.rider_cog = 1000.0
        self.offset = 0.0
        self.combined_cog = 680.0

    def set_state(
        self, *, combined_lean_deg: float, bike_lean_deg: float, bike_cog_height_mm: float,
        rider_cog_height_mm: float, rider_offset_mm: float, combined_cog_height_mm: float,
    ) -> None:
        self.combined, self.bike_lean = combined_lean_deg, bike_lean_deg
        self.bike_cog, self.rider_cog = bike_cog_height_mm, rider_cog_height_mm
        self.offset, self.combined_cog = rider_offset_mm, combined_cog_height_mm
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        primary, secondary = ink(self)
        w, h = self.width(), self.height()
        ground_y = h - 30.0
        contact = QPointF(w * 0.4, ground_y)
        scale = (ground_y - 80) / max(1300.0, self.rider_cog + 300)

        p.setPen(pen(secondary, 1))
        p.drawLine(QPointF(10, ground_y), QPointF(w - 10, ground_y))
        p.setPen(pen(secondary, 0.8, Qt.PenStyle.DotLine))
        p.drawLine(contact, QPointF(contact.x(), 40))

        bike = min(self.bike_lean, MAX_DRAWN_LEAN)
        combined = min(self.combined, MAX_DRAWN_LEAN)
        p.setPen(pen(GREY, 10))
        p.drawLine(contact, polar(contact, 1100 * scale, bike))
        p.setPen(pen(PURPLE, 1.5, Qt.PenStyle.DashLine))
        p.drawLine(contact, polar(contact, (self.rider_cog + 250) * scale, combined))

        a = math.radians(bike)

        def bike_frame(x_mm: float, y_mm: float) -> QPointF:
            """x towards the inside of the turn, y up the bike's plane, from the contact point."""
            wx = x_mm * math.cos(a) + y_mm * math.sin(a)
            wy = -x_mm * math.sin(a) + y_mm * math.cos(a)
            return QPointF(contact.x() + wx * scale, contact.y() - wy * scale)

        bike_cog = bike_frame(0, self.bike_cog)
        seat = bike_frame(0, self.bike_cog + 200)
        rider = bike_frame(self.offset, self.rider_cog)
        combined_cog = polar(contact, self.combined_cog * scale, combined)

        p.setPen(pen(CORAL, 3))
        p.drawLine(seat, rider)
        p.setPen(Qt.PenStyle.NoPen)
        for point, colour, radius in ((bike_cog, GREY_DARK, 5), (rider, CORAL, 7), (combined_cog, PURPLE, 6)):
            p.setBrush(QBrush(colour))
            p.drawEllipse(point, radius, radius)

        p.setPen(pen(primary, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        _angle_arc(p, contact, 42, bike)
        p.setFont(label_font(self, 1.0, bold=True))
        p.drawText(polar(contact, 54, bike / 2) + QPointF(-2, 0), f"{self.bike_lean:.1f}°")

        _legend(p, self, [
            (GREY, 6, Qt.PenStyle.SolidLine, "bike"),
            (CORAL, 3, Qt.PenStyle.SolidLine, "rider's centre of gravity"),
            (PURPLE, 1.5, Qt.PenStyle.DashLine, f"combined lean {self.combined:.1f}°"),
        ])
        p.end()
