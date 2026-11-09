"""Render each tab of the main window to docs/screenshots/*.png (light palette), offscreen.

Usage: QT_QPA_PLATFORM=offscreen python tools/screenshots.py [output-dir]
The rider values are the built-in examples; nothing is read from or written to the user's settings.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kammcircle.ui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("cornering", "body-position", "steering-geometry", "rider-and-bike")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    with tempfile.TemporaryDirectory() as tmp:
        settings = QSettings(str(Path(tmp) / "screenshots.ini"), QSettings.Format.IniFormat)
        window = MainWindow(settings)
        window.resize(1100, 860)
        window.geometry.rear.setValue(30)
        window.body.offset.setValue(120)
        window.show()
        for index, name in enumerate(NAMES):
            window.tabs.setCurrentIndex(index)
            app.processEvents()
            path = out / f"{index + 1:02d}-{name}.png"
            window.grab().save(str(path))
            print(f"wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")


if __name__ == "__main__":
    main()
