"""The main window: a bike selector over the tabs, with the rider's variables and each bike's tyres saved through
QSettings."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, catalogue
from ..rider import RiderSetup
from .acceleration_panel import AccelerationPanel
from .body_panel import BodyPositionPanel
from .braking_panel import BrakingPanel
from .cornering_panel import CorneringPanel
from .countersteer_panel import CountersteerPanel
from .geometry_panel import GeometryPanel
from .rider_panel import RiderPanel
from .steady_turn_panel import SteadyTurnPanel
from .tyre_temperature_panel import TyreTemperaturePanel
from .tyres_panel import TyresPanel


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


def load_tyres(settings: QSettings, bike: catalogue.Bike) -> catalogue.TyreChoice:
    """The tyres last fitted to this bike, or its original fitment when none were saved or they no longer fit."""
    original = catalogue.original_tyres(bike)
    chosen = []
    for position, default, size in (("front", original.front, bike.front_tyre), ("rear", original.rear, bike.rear_tyre)):
        saved = settings.value(f"tyres/{bike.id}/{position}")
        fits = {t.id for t in catalogue.listings_for(size, position)}
        chosen.append(catalogue.tyre_listing(saved) if saved in fits else default)
    return catalogue.TyreChoice(*chosen)


def save_tyres(settings: QSettings, bike: catalogue.Bike, choice: catalogue.TyreChoice) -> None:
    settings.setValue(f"tyres/{bike.id}/front", choice.front.id)
    settings.setValue(f"tyres/{bike.id}/rear", choice.rear.id)


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
        tyres = load_tyres(self.settings, bike)

        self.bike_box = QComboBox()
        for b in bikes:
            self.bike_box.addItem(b.name, b.id)
        self.bike_box.setCurrentIndex(self.bike_box.findData(bike.id))
        self.cold_box = QCheckBox("Tyres not yet warm, surface at")
        self.cold_box.setToolTip("Every run uses this share of a warm tyre's grip; the Tyre temperature tab can set it")
        self.front_temp = QSpinBox()
        self.rear_temp = QSpinBox()
        for spin, end in ((self.front_temp, "front"), (self.rear_temp, "rear")):
            spin.setRange(-30, 150)
            spin.setValue(10)
            spin.setSuffix(f" °C {end}")
            spin.setEnabled(False)
        self.grip_label = QLabel("warm tyres: full grip")
        top = QHBoxLayout()
        top.addWidget(QLabel("Bike"))
        top.addWidget(self.bike_box)
        top.addSpacing(24)
        top.addWidget(self.cold_box)
        top.addWidget(self.front_temp)
        top.addWidget(self.rear_temp)
        top.addWidget(self.grip_label)
        top.addStretch(1)

        self.braking = BrakingPanel(setup, bike)
        self.acceleration = AccelerationPanel(setup, bike)
        self.countersteer = CountersteerPanel(setup, bike)
        self.thermal = TyreTemperaturePanel(setup, bike)
        self.cornering = CorneringPanel(setup, bike)
        self.steady = SteadyTurnPanel(setup, bike)
        self.body = BodyPositionPanel(setup, bike)
        self.geometry = GeometryPanel(bike)
        self.tyres = TyresPanel(bike, setup, tyres)
        self.rider = RiderPanel(setup, bike)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.braking, "Braking (simulation)")
        self.tabs.addTab(self.acceleration, "Acceleration (simulation)")
        self.tabs.addTab(self.countersteer, "Countersteering (simulation)")
        self.tabs.addTab(self.thermal, "Tyre temperature (simulation)")
        self.tabs.addTab(self.cornering, "Cornering and grip")
        self.tabs.addTab(self.steady, "Steady turn (tyre model)")
        self.tabs.addTab(self.body, "Body position")
        self.tabs.addTab(self.geometry, "Steering geometry")
        self.tabs.addTab(self.tyres, "Tyres")
        self.tabs.addTab(self.rider, "Rider and bike")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.cornering.leanChanged.connect(self.body.set_cornering_lean)
        self.body.set_cornering_lean(self.cornering.lean_view.effective_lean)
        self.rider.setupChanged.connect(self._setup_changed)
        self.tyres.tyresChanged.connect(self._tyres_changed)
        self.bike_box.currentIndexChanged.connect(self._bike_changed)
        self.cold_box.toggled.connect(self._grip_changed)
        self.front_temp.valueChanged.connect(self._grip_changed)
        self.rear_temp.valueChanged.connect(self._grip_changed)
        self.thermal.windowChanged.connect(self._grip_changed)
        self.thermal.temperaturesChosen.connect(self.use_tyre_temperatures)
        self._apply_tyres(tyres)
        self._build_menu()
        self.statusBar().showMessage("Braking, acceleration, countersteering and tyre temperature are time-stepped "
                                     "simulations; the other tabs are steady-state calculators.")

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
            "share one grip budget. It runs time-stepped braking and acceleration simulations (suspension, tyre slip, "
            "wheel lock and wheelspin, ABS, stoppies and wheelies, engine and gearbox, engine braking, air drag) and a corner ridden by "
            "countersteering on the benchmark lean-and-steer model, with the speeds at which the motorcycle steadies "
            "itself, and tyres warming from a cold start in any weather. A steady turn is solved on Magic Formula tyres "
            "that slip and camber, down to the torque the rider holds on the bars, beside steady-state calculators for "
            "cornering, rider position, steering geometry and lowering. "
            "Tyres come from a catalogue that records what is on sale in Morocco, with a best-fit ranking, and the "
            "load includes a pillion and luggage. Data is sourced for the Royal Enfield Himalayan 450 and Scram 411.</p>",
        )

    def use_tyre_temperatures(self, front: float, rear: float) -> None:
        """Run every tab on tyres whose surfaces are at these temperatures."""
        for spin, value in ((self.front_temp, front), (self.rear_temp, rear)):
            spin.blockSignals(True)
            spin.setValue(round(value))
            spin.blockSignals(False)
        if self.cold_box.isChecked():
            self._grip_changed()
        else:
            self.cold_box.setChecked(True)
        self.statusBar().showMessage(f"Every run now uses tyres at {round(front)} °C front and {round(rear)} °C rear.")

    def tyre_grip(self) -> tuple[float, float]:
        if not self.cold_box.isChecked():
            return 1.0, 1.0
        window = self.thermal.window()
        return window.factor(self.front_temp.value()), window.factor(self.rear_temp.value())

    def _grip_changed(self) -> None:
        on = self.cold_box.isChecked()
        self.front_temp.setEnabled(on)
        self.rear_temp.setEnabled(on)
        front, rear = self.tyre_grip()
        self.grip_label.setText(f"grip {front:.0%} / {rear:.0%} of warm" if on else "warm tyres: full grip")
        for panel in (self.braking, self.acceleration, self.countersteer, self.cornering, self.steady):
            panel.set_tyre_grip(front, rear)

    def _apply_tyres(self, choice: catalogue.TyreChoice) -> None:
        for panel in (self.braking, self.acceleration, self.countersteer, self.thermal, self.cornering, self.steady,
                      self.geometry):
            panel.set_tyres(choice)

    def _tyres_changed(self, choice: catalogue.TyreChoice) -> None:
        save_tyres(self.settings, catalogue.bike(self.bike_box.currentData()), choice)
        self._apply_tyres(choice)

    def _setup_changed(self, setup: RiderSetup) -> None:
        save_setup(self.settings, setup)
        for panel in (self.braking, self.acceleration, self.countersteer, self.thermal, self.cornering, self.steady,
                      self.body, self.tyres):
            panel.set_setup(setup)

    def _bike_changed(self) -> None:
        bike = catalogue.bike(self.bike_box.currentData())
        self.settings.setValue("bike", bike.id)
        for panel in (self.braking, self.acceleration, self.countersteer, self.thermal, self.cornering, self.steady,
                      self.body, self.geometry, self.rider):
            panel.set_bike(bike)
        tyres = load_tyres(self.settings, bike)
        self.tyres.set_bike(bike, tyres)
        self._apply_tyres(tyres)
