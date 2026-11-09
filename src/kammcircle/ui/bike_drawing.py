"""The schematic adventure-bike side view shared by the geometry and braking views. A drawing, not data.

Frame coordinates are millimetres from the steering head, x towards the rear and y down (the bike faces left): the
seat sits about 170 mm below the head and the swingarm pivot about 520 mm above the road.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from .style import GREY, GREY_DARK, GREY_LIGHT, pen

FORK_LENGTH_MM = 720.0  # front axle to steering head along the axis; a drawing proportion


def head_height_mm(front_radius_mm: float, rake_deg: float) -> float:
    return front_radius_mm + FORK_LENGTH_MM * math.cos(math.radians(rake_deg))


def sump_depth_mm(front_radius_mm: float, rake_deg: float, ground_clearance_mm: float) -> float:
    """Depth of the sump guard below the steering head, so that it sits at the stated ground clearance."""
    return head_height_mm(front_radius_mm, rake_deg) - ground_clearance_mm


def swingarm_pivot(sump: float) -> QPointF:
    return QPointF(650, sump - 290)


def _cosmetic(colour: QColor, width: float) -> QPen:
    q = pen(colour, width)
    q.setCosmetic(True)  # pen widths in pixels, whatever the drawing's scale
    return q


def draw_frame(p: QPainter, sump: float) -> None:
    """Draw the frame, engine, tank, seat and handlebar; the painter's transform must be the head frame (mm)."""
    fill = QColor(GREY_LIGHT)
    fill.setAlphaF(0.35)
    p.setPen(_cosmetic(GREY, 1))
    p.setBrush(QBrush(fill))
    p.drawRoundedRect(QRectF(150, sump - 400, 410, 370), 40, 40)
    p.drawPolygon(QPolygonF([QPointF(30, -40), QPointF(120, -110), QPointF(430, -90),
                             QPointF(520, 60), QPointF(40, 120)]))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_cosmetic(GREY_DARK, 3))
    pivot = swingarm_pivot(sump)
    p.drawPolyline(QPolygonF([QPointF(0, 60), QPointF(110, 500), QPointF(180, sump), QPointF(560, sump),
                              pivot, QPointF(540, 170), QPointF(0, 40)]))
    p.drawPolyline(QPolygonF([QPointF(540, 170), QPointF(1000, 140)]))
    p.drawLine(pivot, QPointF(900, 160))
    p.setPen(_cosmetic(GREY_DARK, 7))
    p.drawLine(QPointF(470, 160), QPointF(1010, 120))
    p.setPen(_cosmetic(GREY_DARK, 2.5))
    p.drawPolyline(QPolygonF([QPointF(-10, -20), QPointF(-40, -160), QPointF(60, -175)]))


def draw_wheel(p: QPainter, centre: QPointF, radius: float, angle_deg: float | None, *, scale: float,
               locked: bool = False) -> None:
    """A tyre, rim and three spokes; ``angle_deg`` turns the spokes so that rolling (or locking) is visible.

    ``centre`` and ``radius`` are in the painter's current units; ``scale`` converts millimetres to those units.
    """
    p.setPen(pen(GREY_DARK, max(3.0, 70 * scale)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(centre, radius - 35 * scale, radius - 35 * scale)
    p.setPen(pen(GREY, 1))
    p.drawEllipse(centre, radius * 0.62, radius * 0.62)
    if angle_deg is None:
        return
    p.setPen(pen(QColor("#E24B4A") if locked else GREY, 1.6))
    for k in range(3):
        a = math.radians(angle_deg + 60 * k)
        dx, dy = radius * 0.62 * math.cos(a), radius * 0.62 * math.sin(a)
        p.drawLine(QPointF(centre.x() - dx, centre.y() - dy), QPointF(centre.x() + dx, centre.y() + dy))
