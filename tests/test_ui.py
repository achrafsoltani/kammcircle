"""Offscreen smoke tests: the window builds, the panels agree with the physics, and settings round-trip."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtCore = pytest.importorskip("PySide6.QtCore")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from kammcircle import catalogue  # noqa: E402
from kammcircle import physics as P  # noqa: E402
from kammcircle.rider import RiderSetup  # noqa: E402
from kammcircle.ui.main_window import MainWindow, load_setup, save_setup  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def settings(tmp_path):
    return QtCore.QSettings(str(tmp_path / "kammcircle.ini"), QtCore.QSettings.Format.IniFormat)


def test_window_builds_and_shows_the_reference_corner(app, settings):
    window = MainWindow(settings)
    c = window.cornering
    c.tyre_width.setChecked(False)
    c.speed.setValue(60)
    c.radius.setValue(50)
    assert c.c_lean.value.text() == f"{P.lean_angle_deg(60, 50):.1f}°" == "29.5°"
    assert c.c_lat.value.text() == "0.57 g"
    assert c.c_wheel.value.text() == "off"


def test_surface_preset_sets_mu_and_custom_takes_over(app, settings):
    window = MainWindow(settings)  # keep a reference, or Qt deletes the panels
    c = window.cornering
    c.surface.setCurrentIndex(c.surface.findData("wet-asphalt"))
    assert c.mu.value() == pytest.approx(0.6)
    assert c.c_limit.value.text() == "31.0°"
    c.mu.setValue(0.42)
    assert c.surface.currentData() == "custom"


def test_braking_past_the_circle_reports_a_slide(app, settings):
    window = MainWindow(settings)  # keep a reference, or Qt deletes the panels
    c = window.cornering
    c.surface.setCurrentIndex(c.surface.findData("dry-asphalt"))
    c.speed.setValue(80)
    c.radius.setValue(50)
    c.brake.setValue(0.5)
    assert "slide" in c.message.text()


def test_geometry_presets_match_the_reference_table(app, settings):
    window = MainWindow(settings)
    window.bike_box.setCurrentIndex(window.bike_box.findData("re-himalayan-450-2026"))
    g = window.geometry
    g._preset(30, 0)
    assert g.c_rake.value.text().startswith("27.1°")
    assert g.c_trail.value.text().startswith("132 mm")
    assert g.c_clear.value.text() == "215 mm"
    g._preset(30, 30)
    assert g.c_rake.value.text().startswith("26.0°")
    assert g.c_clear.value.text() == "200 mm"


def test_body_position_follows_the_cornering_lean(app, settings):
    window = MainWindow(settings)
    window.cornering.speed.setValue(60)
    window.cornering.radius.setValue(50)
    window.body.offset.setValue(0)
    assert window.body.c_bike.value.text() == "29.5°"
    window.body.offset.setValue(150)
    assert float(window.body.c_bike.value.text().rstrip("°")) < 29.5


def test_rider_values_round_trip_through_settings(app, settings):
    window = MainWindow(settings)
    window.rider.spins["rider_mass_kg"].setValue(95)
    window.rider.spins["peg_height_mm"].setValue(290)
    window.rider.spins["peg_lateral_mm"].setValue(310)
    assert window.rider.c_clearance.value.text() == f"{P.clearance_angle_deg(290, 310):.1f}°"
    reloaded = load_setup(settings)
    assert reloaded.rider_mass_kg == 95
    assert reloaded.peg_height_mm == 290
    assert not reloaded.is_example("rider_mass_kg")


def test_save_and_load_setup(app, settings):
    save_setup(settings, RiderSetup(rider_mass_kg=72))
    assert load_setup(settings).rider_mass_kg == 72


def test_switching_bike_updates_every_panel(app, settings):
    window = MainWindow(settings)
    window.bike_box.setCurrentIndex(window.bike_box.findData("re-scram-411"))
    scram = catalogue.bike("re-scram-411")
    assert window.geometry.tyre.text() == scram.front_tyre
    assert window.geometry.c_rake.value.text().startswith("26.2°")
    assert "Scram 411" in window.rider.data.toPlainText()
    assert settings.value("bike") == "re-scram-411"


def test_views_paint_without_errors(app, settings):
    window = MainWindow(settings)
    window.resize(1100, 860)
    for index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(index)
        assert not window.tabs.currentWidget().grab().isNull()
