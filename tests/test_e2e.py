"""End to end: the real window, driven through Qt's event loop with mouse clicks, key presses and timers, as a user
would drive it, one feature at a time. Runs offscreen; the user's own settings are never touched."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSettings, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from kammcircle.sim import BrakingSim, SuspendedBrakingSim  # noqa: E402
from kammcircle.ui.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ini(tmp_path):
    return str(tmp_path / "kammcircle-e2e.ini")


def open_window(ini_path: str) -> MainWindow:
    window = MainWindow(QSettings(ini_path, QSettings.Format.IniFormat))
    window.resize(1100, 860)
    window.show()
    QApplication.processEvents()
    return window


def click(widget) -> None:
    """Click where a user would: the middle of a button, the box of a tick-box (a wide tick-box only reacts to
    clicks on its box and label)."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QCheckBox

    if isinstance(widget, QCheckBox):
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(9, widget.height() // 2))
    else:
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def wait_until(predicate, timeout_s: float) -> bool:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if predicate():
            return True
        QTest.qWait(20)
    return predicate()


def braking_tab(window: MainWindow):
    window.tabs.setCurrentWidget(window.braking)
    QApplication.processEvents()
    return window.braking


# ─── braking ─────────────────────────────────────────────────────────────────


def test_brake_button_runs_in_real_time_to_a_stop(app, ini):
    window = open_window(ini)
    b = braking_tab(window)
    b.speed.setValue(40)
    b.front.setValue(80)
    b.rear.setValue(30)
    started = time.monotonic()
    click(b.run_button)
    assert b.timer.isActive()
    assert wait_until(lambda: b.sim is not None and b.sim.stopped, 15.0)
    wall = time.monotonic() - started
    QTest.qWait(50)
    assert not b.timer.isActive()
    assert b.sim.summary().outcome == "stopped"
    assert wall == pytest.approx(b.sim.t, rel=0.35)  # real time, give or take the test machine
    assert b.c_distance.value.text().endswith(" m")
    assert all(len(chart.series) and len(chart.series[0].xs) > 10 for chart in b.charts)
    assert not b.view.grab().isNull()
    assert isinstance(b.sim, SuspendedBrakingSim)


def test_slow_motion_runs_at_a_quarter_of_real_time_and_reset_clears_it(app, ini):
    window = open_window(ini)
    b = braking_tab(window)
    click(b.slow_button)
    QTest.qWait(1200)
    assert b.sim.t == pytest.approx(0.3, abs=0.12)
    click(b.reset_button)
    assert b.sim is None and not b.timer.isActive()
    assert b.c_distance.value.text() == "—"


def test_instant_result_and_the_parameter_sources(app, ini):
    window = open_window(ini)
    b = braking_tab(window)
    click(b.instant_button)
    assert b.sim.stopped and b.c_mean.value.text().endswith(" g")
    click(b.toggle)
    assert b.parameters.isVisible()
    text = b.parameters.toPlainText()
    for expected in ("Sharp et al. 2004", "Touratech", "example", "modelling choice"):
        assert expected in text


def test_abs_off_locks_the_front_and_abs_on_does_not(app, ini):
    window = open_window(ini)
    b = braking_tab(window)
    b.surface.setCurrentIndex(b.surface.findData("wet-asphalt"))
    b.front.setValue(100)
    b.rear.setValue(0)
    click(b.abs_front)  # untick
    assert not b.abs_front.isChecked()
    click(b.instant_button)
    assert any("Front wheel locks" in e for _, e in b.sim.events)
    assert "loses its steering" in b.events.text()
    click(b.abs_front)  # tick again
    click(b.instant_button)
    assert not any("Front wheel locks" in e for _, e in b.sim.events if _ > 0.0 and b.sim.v > 2)
    assert b.sim.summary().front_locked_s < 0.1


def test_suspension_tick_box_switches_between_the_two_models(app, ini):
    window = open_window(ini)
    b = braking_tab(window)
    click(b.instant_button)
    assert isinstance(b.sim, SuspendedBrakingSim)
    assert max(s.susp_f for s in b.sim.trace) > 100
    click(b.suspension_box)
    click(b.instant_button)
    assert type(b.sim) is BrakingSim
    assert max(s.susp_f for s in b.sim.trace) == 0.0
    assert "Rider sag" not in b.parameters.toPlainText()


def test_live_keys_brake_even_when_a_spin_box_has_the_focus(app, ini):
    window = open_window(ini)
    b = braking_tab(window)
    b.front.setValue(70)
    click(b.manual_box)
    assert b.manual and not b.instant_button.isEnabled()
    b.front.spin.setFocus()  # the user has just typed a lever value
    QApplication.processEvents()
    QTest.keyPress(QApplication.focusWidget(), Qt.Key.Key_F)
    assert b.sim is not None, "pressing F must start a live run"
    QTest.qWait(600)
    assert b.sim.lever_f == pytest.approx(0.70, abs=0.02)
    QTest.keyRelease(QApplication.focusWidget(), Qt.Key.Key_F)
    QTest.qWait(500)
    assert b.sim.lever_f == pytest.approx(0.0, abs=0.01) or b.sim.stopped
    QTest.keyPress(QApplication.focusWidget(), Qt.Key.Key_R)
    QTest.qWait(400)
    assert b.sim.lever_r > 0.1 or b.sim.stopped
    QTest.keyRelease(QApplication.focusWidget(), Qt.Key.Key_R)
    click(b.reset_button)


def test_holding_full_front_on_high_grip_goes_over_the_bars(app, ini):
    window = open_window(ini)
    b = braking_tab(window)
    b.mu.setValue(1.3)
    assert b.surface.currentData() == "custom"
    b.speed.setValue(100)
    b.front.setValue(100)
    b.rear.setValue(0)
    click(b.instant_button)
    assert b.sim.summary().outcome == "pitched over"
    assert b.c_distance.value.text() == "went over the front"
    assert any("lifts" in e for _, e in b.sim.events)


# ─── the other tabs ──────────────────────────────────────────────────────────


def test_switching_bike_updates_every_tab_and_is_remembered(app, ini):
    window = open_window(ini)
    window.bike_box.setCurrentIndex(window.bike_box.findData("re-scram-411"))
    QApplication.processEvents()
    assert window.geometry.tyre.text() == "100/90-19"  # the size of the Scram's fitted (original) front tyre
    assert "Scram 411" in window.rider.data.toPlainText()
    assert "47.8" in window.rider.data.toPlainText()
    assert "measured axle weights" in window.braking.parameters.toPlainText()
    assert window.braking.view.wheelbase == 1455
    window.close()
    again = open_window(ini)
    assert again.bike_box.currentData() == "re-scram-411"


def test_cornering_tab(app, ini):
    window = open_window(ini)
    c = window.cornering
    window.tabs.setCurrentWidget(c)
    c.speed.setValue(60)
    c.radius.setValue(50)
    c.surface.setCurrentIndex(c.surface.findData("dry-asphalt"))
    assert c.c_lean.value.text() == "29.5°"
    assert c.c_wheel.value.text() != "off"
    click(c.tyre_width)
    assert c.c_wheel.value.text() == "off"
    assert "margin" in c.message.text()
    c.brake.setValue(0.9)
    assert "slide" in c.message.text()
    assert not c.grab().isNull()


def test_body_position_tab(app, ini):
    window = open_window(ini)
    body = window.body
    window.tabs.setCurrentWidget(body)
    window.cornering.speed.setValue(60)
    window.cornering.radius.setValue(50)
    assert body.c_bike.value.text() == "29.5°"
    body.offset.setValue(150)
    assert float(body.c_bike.value.text().rstrip("°")) < 29.5
    click(body.follow)  # untick: the combined lean is now set by hand
    assert body.combined.isEnabled()
    body.combined.setValue(40)
    body.offset.setValue(-150)
    assert float(body.c_bike.value.text().rstrip("°")) > 40


def test_steering_geometry_tab(app, ini):
    window = open_window(ini)
    g = window.geometry
    window.tabs.setCurrentWidget(g)
    buttons = {b.text(): b for b in g.findChildren(type(window.braking.run_button))}
    click(buttons["Rear −30 mm"])
    assert g.c_rake.value.text().startswith("27.1°")
    click(buttons["Both −30 mm"])
    assert g.c_clear.value.text() == "200 mm"
    g.tyre.selectAll()
    QTest.keyClicks(g.tyre, "nonsense")
    assert "unrecognised" in g.tyre_status.text()
    g.tyre.clear()
    QTest.keyClicks(g.tyre, "90/100-21")
    assert g.tyre_status.text().startswith("R = ")
    click(buttons["Stock"])
    assert g.c_trail.value.text().startswith(f"{g.view.trail:.0f} mm")


def test_rider_tab_edits_feed_the_models_and_survive_a_restart(app, ini):
    window = open_window(ini)
    r = window.rider
    window.tabs.setCurrentWidget(r)
    r.spins["rider_mass_kg"].setValue(92)
    r.spins["front_sag_pct"].setValue(25)
    r.spins["peg_height_mm"].setValue(300)
    r.spins["peg_lateral_mm"].setValue(320)
    assert "(example)" not in r.labels["rider_mass_kg"].text()
    assert r.c_clearance.value.text().endswith("°")
    notes = window.braking.parameters.toPlainText()
    assert "92 kg" in notes and "your value" in notes
    window.close()
    again = open_window(ini)
    assert again.rider.spins["rider_mass_kg"].value() == 92
    assert again.rider.spins["front_sag_pct"].value() == 25
    click(next(b for b in again.rider.findChildren(type(again.braking.run_button)) if b.text().startswith("Reset")))
    assert again.rider.spins["rider_mass_kg"].value() == 80
    assert "(example)" in again.rider.labels["rider_mass_kg"].text()


def test_help_about_and_quit(app, ini):
    window = open_window(ini)
    seen = []

    def close_dialog():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            seen.append(dialog.text())
            dialog.accept()

    QTimer.singleShot(200, close_dialog)
    about = next(a for a in window.menuBar().actions()[1].menu().actions() if "About" in a.text())
    about.trigger()
    from kammcircle import __version__

    assert seen and f"kammcircle {__version__}" in seen[0]
    quit_action = next(a for a in window.menuBar().actions()[0].menu().actions() if "Quit" in a.text())
    quit_action.trigger()
    QApplication.processEvents()
    assert not window.isVisible()


# ─── tyres, best fit, loads ──────────────────────────────────────────────────


def test_tyres_tab_fitting_feeds_the_simulation_and_is_remembered(app, ini):
    window = open_window(ini)
    t = window.tyres
    window.tabs.setCurrentWidget(t)
    assert t.table.rowCount() >= 15  # every listed tyre in the Himalayan's sizes
    assert "Motoshop" in " ".join(t.table.item(r, 7).text() for r in range(t.table.rowCount()))
    t.front_box.setCurrentIndex(t.front_box.findData("mitas-terra-force-r-90-90-21-54h"))
    t.rear_box.setCurrentIndex(t.rear_box.findData("mitas-terra-force-r-140-80r17-69v"))
    QApplication.processEvents()
    assert "Terra Force-R" in window.braking.parameters.toPlainText()
    click(window.braking.instant_button)
    assert window.braking.sim.p.front_radius == pytest.approx(0.3475)
    window.close()
    again = open_window(ini)
    assert again.tyres.choice.rear.id == "mitas-terra-force-r-140-80r17-69v"


def test_best_fit_ranks_by_riding_and_fits_the_chosen_pair(app, ini):
    window = open_window(ini)
    t = window.tyres
    window.tabs.setCurrentWidget(t)
    t.unpaved.setValue(40)
    assert "Enduro Trail+" in t.ranking.item(0, 0).text()
    click(t.fit_button)
    assert t.choice.front.product.id == t.choice.rear.product.id == "mitas-enduro-trail-plus"
    click(t.stock_only)
    assert t.ranking.rowCount() == 0 and "No complete pair" in t.excluded.toPlainText()
    assert not t.fit_button.isEnabled()


def test_a_slow_tyre_warns_in_the_braking_run(app, ini):
    window = open_window(ini)
    t = window.tyres
    t.front_box.setCurrentIndex(t.front_box.findData("timsun-ts-712f-90-90-21-54p"))
    assert "below the original" in t.front_info.text()
    b = braking_tab(window)
    b.speed.setValue(160)
    click(b.instant_button)
    assert "rated for 150 km/h" in b.events.text()


def test_pillion_and_luggage_change_the_loads_the_tyres_and_the_stop(app, ini):
    window = open_window(ini)
    b = braking_tab(window)
    b.front.setValue(50)
    b.rear.setValue(20)
    click(b.instant_button)
    solo = b.sim.summary().stopping_distance
    r = window.rider
    r.spins["pillion_mass_kg"].setValue(70)
    r.spins["luggage_mass_kg"].setValue(30)
    assert "Pillion" in b.parameters.toPlainText()
    assert "your load at rest" in window.tyres.rear_info.text()
    click(b.instant_button)
    assert b.sim.summary().stopping_distance > solo
    assert b.sim.static_rear_compression > b.sim.susp.rear_sag


# ─── acceleration ────────────────────────────────────────────────────────────


def test_acceleration_tab_runs_in_real_time_and_at_once(app, ini):
    window = open_window(ini)
    a = window.acceleration
    window.tabs.setCurrentWidget(a)
    QApplication.processEvents()
    a.target.setValue(50)
    started = time.monotonic()
    click(a.run_button)
    assert wait_until(lambda: a.sim is not None and a.sim.stopped, 15.0)
    assert time.monotonic() - started == pytest.approx(a.sim.t, rel=0.4)
    assert a.c_50.value.text().endswith(" s")
    a.target.setValue(100)
    click(a.instant_button)
    assert a.sim.outcome == "reached" and a.c_100.value.text().endswith(" s")
    assert "Gear changes" in a.events.text()
    click(a.toggle)
    assert "Drag area CdA" in a.parameters.toPlainText() and "derived" in a.parameters.toPlainText()
    assert all(len(chart.series) for chart in a.charts)


def test_acceleration_top_speed_and_throttle_control(app, ini):
    window = open_window(ini)
    a = window.acceleration
    a.start_speed.setValue(100)
    click(a.top_speed_box)
    assert not a.target.isEnabled()
    click(a.instant_button)
    assert a.sim.outcome == "top speed"
    assert "top speed" in a.c_end.value.text()
    click(a.top_speed_box)
    a.start_speed.setValue(0)
    click(a.control)  # let the tyre spin
    click(a.instant_button)
    assert "rear tyre spun" in a.events.text()


def test_acceleration_follows_the_bike(app, ini):
    window = open_window(ini)
    window.bike_box.setCurrentIndex(window.bike_box.findData("re-scram-411"))
    QApplication.processEvents()
    a = window.acceleration
    assert a.shift.value() == 6300  # 200 rpm under the Scram's peak power
    click(a.instant_button)
    assert a.sim.powertrain.gearbox.gears[0] == 2.916


def test_suspended_braking_runs_include_air_drag(app, ini):
    window = open_window(ini)
    b = braking_tab(window)
    b.speed.setValue(140)
    b.front.setValue(60)
    b.rear.setValue(20)
    click(b.instant_button)
    assert b.sim.cda > 0.3 and "Drag area CdA" in b.parameters.toPlainText()
    with_drag = b.sim.summary().stopping_distance
    b.sim.cda = 0.0  # the same run without drag, for comparison
    from kammcircle.sim import SuspendedBrakingSim, LeverRamp

    still = SuspendedBrakingSim(b.sim.p, b.sim.susp, 140)
    levers = LeverRamp(b.squeeze.value())
    while not still.stopped and still.t < 30:
        levers.update(0.6 if still.t >= 0.6 else 0.0, 0.2 if still.t >= 0.6 else 0.0, still.dt)
        still.step(levers.front, levers.rear)
    assert with_drag < still.summary().stopping_distance


# ─── countersteering ─────────────────────────────────────────────────────────


def countersteer_tab(window: MainWindow):
    window.tabs.setCurrentWidget(window.countersteer)
    QApplication.processEvents()
    return window.countersteer


def test_countersteering_tab_rides_a_corner_in_real_time_and_at_once(app, ini):
    window = open_window(ini)
    c = countersteer_tab(window)
    c.speed.setValue(60)
    c.radius.setValue(60)
    c.angle.setValue(45)
    started = time.monotonic()
    click(c.run_button)
    assert wait_until(lambda: c.sim is not None and c.sim.stopped, 20.0)
    assert time.monotonic() - started == pytest.approx(c.sim.t, rel=0.4)
    assert c.sim.outcome == "done" and c.sim.trace[-1].heading == pytest.approx(45, abs=0.2)
    assert c.c_push.value.text().endswith(" N m") and c.c_counter.value.text().endswith("°")
    assert c.c_wide.value.text().endswith(" cm") and c.c_lean_in.value.text().endswith(" m")
    text = c.events.toPlainText()
    assert "stands the motorcycle up" in text and "Weave at this speed" in text
    assert all(len(chart.series) for chart in c.charts) and len(c.chart_modes.series) == 3
    assert c.c_stable.value.text().endswith("km/h")
    click(c.toggle)
    notes = c.parameters.toPlainText()
    assert "Steered front frame" in notes and "Sharp et al. 2004" in notes and "1510 mm" in notes
    c.angle.setValue(90)
    click(c.instant_button)
    assert c.sim.stopped and c.sim.trace[-1].heading == pytest.approx(90, abs=0.2)
    click(c.reset_button)
    assert c.sim is None and c.c_push.value.text() == "—"


def test_countersteering_left_is_the_mirror_of_right(app, ini):
    window = open_window(ini)
    c = countersteer_tab(window)
    click(c.instant_button)
    right = c.sim
    c.direction.setCurrentIndex(c.direction.findData(-1))
    click(c.instant_button)
    left = c.sim
    assert left.peak_push == pytest.approx(right.peak_push, rel=1e-9)
    assert left.trace[-1].heading == pytest.approx(-right.trace[-1].heading, abs=1e-6)
    first = next(s for s in left.trace if abs(s.torque) > 0.5)
    assert first.torque > 0  # a left-hand corner starts with a push on the left grip, urging the bars right


def test_countersteering_reports_the_limits_of_its_model(app, ini):
    window = open_window(ini)
    c = countersteer_tab(window)
    c.speed.setValue(30)
    c.roll_in.setValue(0.3)
    click(c.instant_button)
    assert "no faster than" in c.events.toPlainText()
    c.speed.setValue(60)
    c.roll_in.setValue(1.0)
    c.radius.setValue(20)
    click(c.instant_button)
    text = c.events.toPlainText()
    assert "overstates the lean" in text and "tyres would slide" in text
    c.radius.setValue(80)
    c.surface.setCurrentIndex(c.surface.findData("wet-asphalt"))
    click(c.instant_button)
    wet = c.mu.value()
    assert wet < 1.0 and (c.sim.peak_lateral_g > wet) == ("tyres would slide" in c.events.toPlainText())


def test_countersteering_follows_the_bike_its_tyres_and_its_load(app, ini):
    window = open_window(ini)
    c = countersteer_tab(window)
    click(c.instant_button)
    solo_push, himalayan_band = c.sim.peak_push, c.c_stable.value.text()
    window.rider.spins["pillion_mass_kg"].setValue(70)
    click(c.instant_button)
    assert c.sim.peak_push != pytest.approx(solo_push, rel=1e-3)
    assert "Rear frame with its riders and load" in c.parameters.toPlainText()
    window.bike_box.setCurrentIndex(window.bike_box.findData("re-scram-411"))
    QApplication.processEvents()
    assert "1455 mm" in c.parameters.toPlainText()
    assert c.c_stable.value.text() != himalayan_band
    click(c.instant_button)
    assert c.sim.p.w == pytest.approx(1.455)


def test_braking_in_gear_brings_in_engine_braking(app, ini):
    window = open_window(ini)
    b = braking_tab(window)
    b.speed.setValue(60)
    b.front.setValue(40)
    b.rear.setValue(0)
    click(b.instant_button)
    clutch_in = b.sim.summary().stopping_distance
    b.engine_box.setCurrentIndex(b.engine_box.findData(2))
    assert "Engine drag, throttle shut" in b.parameters.toPlainText()
    click(b.instant_button)
    text = b.events.text()
    assert "clutch out in 2nd" in text and "The engine took" in text
    assert b.sim.summary().stopping_distance < clutch_in
    assert any(s.label == "engine" for s in b.chart_brakes.series)
    click(b.suspension_box)
    assert not b.engine_box.isEnabled()
    click(b.instant_button)
    assert "engine" not in b.events.text().lower()
    click(b.suspension_box)
    window.bike_box.setCurrentIndex(window.bike_box.findData("re-scram-411"))
    QApplication.processEvents()
    assert b.engine_box.count() == 1 + 5 and b.engine_box.currentData() == 0


# ─── tyre temperature ────────────────────────────────────────────────────────


def test_tyre_temperature_tab_rides_from_a_cold_start(app, ini):
    window = open_window(ini)
    t = window.thermal
    window.tabs.setCurrentWidget(t)
    QApplication.processEvents()
    t.air.setValue(5)
    t.road.setValue(3)
    assert t.start_temp.value() == 5 and not t.start_temp.isEnabled()  # parked outside: tyres at the air temperature
    t.length.setValue(5)
    started = time.monotonic()
    click(t.run_button)
    assert wait_until(lambda: t.run is not None and t.run.stopped, 15.0)
    assert time.monotonic() - started == pytest.approx(5.0, rel=0.4)  # a minute a second
    assert t.c_front.value.text() == "not in this ride" and "below 30 °C" in t.events.toPlainText()
    assert all(len(chart.series) for chart in t.charts)
    t.air.setValue(25)
    t.road.setValue(40)
    t.style.setCurrentIndex(t.style.findData("brisk"))
    t.length.setValue(30)
    click(t.instant_button)
    assert t.c_front.value.text() != "not in this ride" and t.run.reached[0] is not None
    click(t.toggle)
    notes = t.parameters.toPlainText()
    assert "Grip window" in notes and "Mousavi and Sandu" in notes


def test_warmers_and_the_grip_window_are_the_riders_to_set(app, ini):
    window = open_window(ini)
    t = window.thermal
    t.air.setValue(3)
    t.road.setValue(1)
    click(t.parked)
    t.start_temp.setValue(70)
    click(t.instant_button)
    assert t.run.start == 70 and "start warmer than this ride can keep them" in t.events.toPlainText()
    t.window_low.setValue(10)
    click(t.instant_button)
    assert t.run.window.window_low == 10 and t.run.reached == [0.0, 0.0]
    window.bike_box.setCurrentIndex(window.bike_box.findData("re-scram-411"))
    QApplication.processEvents()
    click(t.instant_button)
    from kammcircle import catalogue

    scram_front = catalogue.original_tyres(catalogue.bike("re-scram-411")).front
    assert t.run.front.radius == pytest.approx(scram_front.radius_mm / 1000)  # the Scram's own 19-inch front tyre
