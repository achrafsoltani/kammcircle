"""Small reusable input and output widgets."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from .style import label_font


class SliderField(QWidget):
    """A labelled slider kept in step with a spin box."""

    valueChanged = Signal(float)

    def __init__(
        self, label: str, minimum: float, maximum: float, step: float, value: float,
        unit: str = "", decimals: int = 0, parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._factor = 1.0 / step
        self.label = QLabel(label)
        self.label.setMinimumWidth(120)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(round(minimum * self._factor), round(maximum * self._factor))
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(step)
        if unit:
            self.spin.setSuffix(f" {unit}")
        self.spin.setMinimumWidth(110)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)

        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.setValue(value)

    def value(self) -> float:
        return self.spin.value()

    def setValue(self, value: float) -> None:  # noqa: N802 (Qt naming)
        self.spin.setValue(value)

    def _from_slider(self, raw: int) -> None:
        with QSignalBlocker(self.spin):
            self.spin.setValue(raw / self._factor)
        self.valueChanged.emit(self.spin.value())

    def _from_spin(self, value: float) -> None:
        with QSignalBlocker(self.slider):
            self.slider.setValue(round(value * self._factor))
        self.valueChanged.emit(value)


class ResultCard(QFrame):
    """A caption over a large value, as in the reference illustrations' result cards."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.caption = QLabel(caption)
        self.caption.setFont(label_font(self, 0.9))
        self.value = QLabel("—")
        self.value.setFont(label_font(self, 1.45, bold=True))
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(0)
        layout.addWidget(self.caption)
        layout.addWidget(self.value)

    def set(self, text: str, colour: QColor | None = None) -> None:
        self.value.setText(text)
        self.value.setStyleSheet(f"color: {colour.name()};" if colour is not None else "")


def note_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setFont(label_font(label, 0.9))
    label.setStyleSheet("color: palette(placeholder-text);")
    return label
