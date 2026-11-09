"""Application entry point: ``kammcircle`` or ``python -m kammcircle``."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setOrganizationName("kammcircle")
    app.setApplicationName("kammcircle")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
