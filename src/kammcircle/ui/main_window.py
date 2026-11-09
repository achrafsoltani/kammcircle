"""The main window: a bike selector over four tabs, with the rider's variables saved through QSettings."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from .. import __version__, catalogue
from ..rider import RiderSetup
from .body_panel import BodyPositionPanel
from .braking_panel import BrakingPanel
from .cornering_panel import CorneringPanel
from .geometry_panel import GeometryPanel
from .rider_panel import RiderPanel


def load_setup(settings: QSettings) -> RiderSetup:
    settings.beginGroup("rider")
    values = {key: settings.value(key) for key in settings.childKeys()}
    settings.endGroup()
    return RiderSetup.from_dict(values)


def save_setup(settings: QSettings, setup: RiderSetup) -> None:
    settings.beginGroup("rider")
    for key, value in setup.to_dict().items():
        settings.setValue(key, value)
    settings.endGroup()


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else QSettings()
        self.setWindowTitle("kammcircle — motorcycle simulator")
        self.resize(1100, 860)

        setup = load_setup(self.settings)
        bikes = catalogue.bikes()
        saved = self.settings.value("bike", bikes[0].id)
        bike = next((b for b in bikes if b.id == saved), bikes[0])

        self.bike_box = QComboBox()
        for b in bikes:
            self.bike_box.addItem(b.name, b.id)
        self.bike_box.setCurrentIndex(self.bike_box.findData(bike.id))
        top = QHBoxLayout()
        top.addWidget(QLabel("Bike"))
        top.addWidget(self.bike_box)
        top.addStretch(1)

        self.braking = BrakingPanel(setup, bike)
        self.cornering = CorneringPanel(setup, bike)
        self.body = BodyPositionPanel(setup, bike)
        self.geometry = GeometryPanel(bike)
        self.rider = RiderPanel(setup, bike)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.braking, "Braking (simulation)")
        self.tabs.addTab(self.cornering, "Cornering and grip")
        self.tabs.addTab(self.body, "Body position")
        self.tabs.addTab(self.geometry, "Steering geometry")
        self.tabs.addTab(self.rider, "Rider and bike")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.cornering.leanChanged.connect(self.body.set_cornering_lean)
        self.body.set_cornering_lean(self.cornering.lean_view.effective_lean)
        self.rider.setupChanged.connect(self._setup_changed)
        self.bike_box.currentIndexChanged.connect(self._bike_changed)
        self._build_menu()
        self.statusBar().showMessage("Braking is a time-stepped simulation; the other tabs are steady-state calculators.")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("&About kammcircle", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About kammcircle",
            f"<b>kammcircle {__version__}</b><p>A motorcycle simulator built on Kamm's circle: braking and cornering "
            "share one grip budget. Version 0.3 runs a time-stepped braking simulation (suspension, tyre slip, wheel "
            "lock, ABS, stoppies) to the steady-state calculators for cornering, rider position, steering geometry and lowering, "
            "on sourced data for the Royal Enfield Himalayan 450 and Scram 411.</p>",
        )

    def _setup_changed(self, setup: RiderSetup) -> None:
        save_setup(self.settings, setup)
        self.braking.set_setup(setup)
        self.cornering.set_setup(setup)
        self.body.set_setup(setup)

    def _bike_changed(self) -> None:
        bike = catalogue.bike(self.bike_box.currentData())
        self.settings.setValue("bike", bike.id)
        for panel in (self.braking, self.cornering, self.body, self.geometry, self.rider):
            panel.set_bike(bike)
