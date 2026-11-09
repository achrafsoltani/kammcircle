"""Shared palette and drawing helpers. Colour roles follow docs/illustrations.md."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

TEAL = QColor("#1D9E75")  # grip, good
CORAL = QColor("#D85A30")  # force, warning
PURPLE = QColor("#534AB7")  # line, centre of gravity, resultant
RED = QColor("#E24B4A")  # limit
AMBER = QColor("#BA7517")  # near the limit
GREY = QColor("#888780")  # structure
GREY_DARK = QColor("#5F5E5A")
GREY_LIGHT = QColor("#B4B2A9")


def usage_colour(usage: float) -> QColor:
    """Teal with margin, amber close to the limit, red beyond it (thresholds from illustration 05)."""
    if usage < 0.8:
        return TEAL
    if usage < 1.0:
        return AMBER
    return RED


def ink(widget: QWidget) -> tuple[QColor, QColor]:
    """Primary and secondary text colours that suit the widget's current palette (light or dark)."""
    pal = widget.palette()
    primary = pal.color(QPalette.ColorRole.WindowText)
    secondary = QColor(primary)
    secondary.setAlphaF(0.65)
    return primary, secondary


def pen(colour: QColor, width: float = 1.5, style: Qt.PenStyle = Qt.PenStyle.SolidLine) -> QPen:
    p = QPen(colour, width, style)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def arrow(painter: QPainter, start: QPointF, end: QPointF, colour: QColor, width: float = 2.0) -> None:
    """A straight arrow with an open head, as in the reference illustrations."""
    painter.setPen(pen(colour, width))
    painter.drawLine(start, end)
    angle = math.atan2(end.y() - start.y(), end.x() - start.x())
    size = 7 + width
    left = QPointF(end.x() - size * math.cos(angle - 0.45), end.y() - size * math.sin(angle - 0.45))
    right = QPointF(end.x() - size * math.cos(angle + 0.45), end.y() - size * math.sin(angle + 0.45))
    painter.drawPolyline(QPolygonF([left, end, right]))


def label_font(widget: QWidget, scale: float = 1.0, bold: bool = False) -> QFont:
    font = QFont(widget.font())
    font.setPointSizeF(max(7.0, font.pointSizeF() * scale))
    font.setBold(bold)
    return font


def polar(origin: QPointF, length: float, angle_from_vertical_deg: float) -> QPointF:
    """Point at ``length`` from ``origin``, leaning ``angle`` degrees to the right of vertical (screen y down)."""
    a = math.radians(angle_from_vertical_deg)
    return QPointF(origin.x() + length * math.sin(a), origin.y() - length * math.cos(a))
