"""A small time-series chart drawn with QPainter (Qt Charts is not part of PySide6-Essentials)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import QWidget

from .style import ink, label_font, pen


@dataclass
class Series:
    label: str
    colour: QColor
    xs: list[float] = field(default_factory=list)
    ys: list[float] = field(default_factory=list)
    dashed: bool = False


def nice_step(span: float, target: int = 4) -> float:
    raw = span / max(target, 1)
    if raw <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * magnitude:
            return m * magnitude
    return 10 * magnitude


class StripChart(QWidget):
    def __init__(self, title: str, y_min: float, y_max: float, unit: str = "", parent: QWidget | None = None,
                 x_unit: str = " s") -> None:
        super().__init__(parent)
        self.setMinimumSize(220, 130)
        self.title = title
        self.y_min, self.y_max = y_min, y_max
        self.unit = unit
        self.x_unit = x_unit
        self.x_min, self.x_max = 0.0, 1.0
        self.series: list[Series] = []
        self.guides: list[tuple[float, QColor, str]] = []
        self.vguides: list[tuple[float, QColor, str]] = []

    def set_range(self, y_min: float, y_max: float) -> None:
        self.y_min, self.y_max = y_min, y_max
        self.update()

    def set_data(self, x_max: float, series: list[Series], guides: list[tuple[float, QColor, str]] | None = None, *,
                 x_min: float = 0.0, vguides: list[tuple[float, QColor, str]] | None = None) -> None:
        self.x_min, self.x_max = x_min, max(x_max, x_min + 1e-6)
        self.series = series
        self.guides = guides or []
        self.vguides = vguides or []
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        primary, secondary = ink(self)
        w, h = self.width(), self.height()
        p.setFont(label_font(self, 0.85))
        metrics = p.fontMetrics()
        legend_width = sum(metrics.horizontalAdvance(s.label) + 22 for s in self.series)
        two_lines = metrics.horizontalAdvance(self.title) + legend_width + 24 > w
        left, right, top, bottom = 44.0, 10.0, 38.0 if two_lines else 22.0, 22.0
        plot = QRectF(left, top, max(10.0, w - left - right), max(10.0, h - top - bottom))
        span = self.y_max - self.y_min

        def to_screen(x: float, y: float) -> QPointF:
            return QPointF(plot.left() + plot.width() * (x - self.x_min) / (self.x_max - self.x_min),
                           plot.bottom() - plot.height() * (y - self.y_min) / span)

        p.setFont(label_font(self, 0.85))
        p.setPen(primary)
        p.drawText(QPointF(4, 14), self.title)
        p.setPen(pen(secondary, 0.6, Qt.PenStyle.DotLine))
        step = nice_step(span)
        y = math.ceil(self.y_min / step) * step
        while y <= self.y_max + 1e-9:
            pt = to_screen(0, y)
            p.drawLine(QPointF(plot.left(), pt.y()), QPointF(plot.right(), pt.y()))
            p.setPen(secondary)
            text = f"{y:g}{self.unit}"
            p.drawText(QRectF(0, pt.y() - 8, left - 4, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)
            p.setPen(pen(secondary, 0.6, Qt.PenStyle.DotLine))
            y += step
        xstep = nice_step(self.x_max - self.x_min, 5)
        x = math.ceil(self.x_min / xstep - 1e-9) * xstep
        while x <= self.x_max + 1e-9:
            pt = to_screen(x, self.y_min)
            p.setPen(secondary)
            p.drawText(QRectF(pt.x() - 30, plot.bottom() + 3, 60, 16), Qt.AlignmentFlag.AlignHCenter,
                       f"{round(x, 9):g}{self.x_unit}")
            x += xstep
        p.setPen(pen(secondary, 1))
        p.drawRect(plot)

        for value, colour, text in self.guides:
            if self.y_min <= value <= self.y_max:
                pt = to_screen(0, value)
                p.setPen(pen(colour, 1, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(plot.left(), pt.y()), QPointF(plot.right(), pt.y()))
                p.setPen(colour)
                p.drawText(QPointF(plot.left() + 4, pt.y() - 3), text)

        for value, colour, text in self.vguides:
            if self.x_min <= value <= self.x_max:
                pt = to_screen(value, self.y_max)
                p.setPen(pen(colour, 1, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(pt.x(), plot.top()), QPointF(pt.x(), plot.bottom()))
                p.setPen(colour)
                p.drawText(QPointF(pt.x() + 3, plot.bottom() - 4), text)

        p.save()
        p.setClipRect(plot.adjusted(-1, -1, 1, 1))
        for s in self.series:
            if len(s.xs) < 2:
                continue
            p.setPen(pen(s.colour, 1.8, Qt.PenStyle.DashLine if s.dashed else Qt.PenStyle.SolidLine))
            p.drawPolyline(QPolygonF([to_screen(x, max(min(y, self.y_max * 2), self.y_min * 2 - 1))
                                      for x, y in zip(s.xs, s.ys)]))
        p.restore()

        x0 = plot.right()
        y0 = 26.0 if two_lines else 10.0
        for s in reversed(self.series):
            width = p.fontMetrics().horizontalAdvance(s.label) + 22
            x0 -= width
            p.setPen(pen(s.colour, 2, Qt.PenStyle.DashLine if s.dashed else Qt.PenStyle.SolidLine))
            p.drawLine(QPointF(x0, y0), QPointF(x0 + 14, y0))
            p.setPen(secondary)
            p.drawText(QPointF(x0 + 17, y0 + 4), s.label)
        p.end()
