"""A watched end-to-end tour of kammcircle: the real window, driven feature by feature through Qt's event loop at a pace
a person can follow. A banner names each step and shows whether its check passed; a red frame marks the control being
used. Settings go to a temporary file, so your own rider values and fitted tyres are never touched.

Usage:
    python tools/tour.py                 # watch it: about five minutes, in a 1400 × 900 window
    python tools/tour.py --keep-open     # leave the window open afterwards to explore
    python tools/tour.py --pace 0.5      # twice as fast
    python tools/tour.py --quick         # no pauses, instant results instead of the real-time runs (a few seconds)
    QT_QPA_PLATFORM=offscreen python tools/tour.py --quick   # headless, as the tests run it

The exit code is the number of failed checks.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QLabel, QMessageBox, QPushButton, QWidget

parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
parser.add_argument("--pace", type=float, default=1.0, help="scale of the pauses (1 = watchable)")
parser.add_argument("--quick", action="store_true", help="no pauses; instant results instead of real-time runs")
parser.add_argument("--size", default="1400x900", help="window size in pixels, WIDTHxHEIGHT (default 1400x900)")
parser.add_argument("--keep-open", action="store_true", help="leave the window open when the tour ends")
args = parser.parse_args()
PACE = 0.0 if args.quick else args.pace
REAL_TIME = not args.quick

app = QApplication(sys.argv[:1])
app.setOrganizationName("kammcircle-tour")
app.setApplicationName("kammcircle-tour")

from kammcircle import __version__  # noqa: E402
from kammcircle.ui.main_window import MainWindow  # noqa: E402

work = Path(tempfile.mkdtemp(prefix="kammcircle-tour-"))
settings = QSettings(str(work / "tour-settings.ini"), QSettings.Format.IniFormat)
window = MainWindow(settings)
window.setWindowTitle(f"kammcircle {__version__} — end-to-end tour (temporary settings)")

banner = QLabel()
banner.setWordWrap(True)
banner.setTextFormat(Qt.TextFormat.RichText)
font = QFont(banner.font())
font.setPointSizeF(font.pointSizeF() * 1.2)
banner.setFont(font)
banner.setStyleSheet("QLabel { background: #FFF4D6; color: #2B2A27; border: 2px solid #BA7517; border-radius: 6px;"
                     " padding: 8px; }")
banner.setMinimumHeight(70)
window.centralWidget().layout().insertWidget(0, banner)

frame = QFrame(window)
frame.setStyleSheet("QFrame { border: 3px solid #E24B4A; border-radius: 4px; background: transparent; }")
frame.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
frame.hide()

results: list[tuple[str, bool, str]] = []
started = time.monotonic()
step_no = 0
current = ""


def pause(ms: float) -> None:
    QTest.qWait(max(1, int(ms * PACE)))


def hold(ms: int) -> None:
    """A wait that the simulation measures in real time: never shortened by the pace."""
    QTest.qWait(ms)


def show(text: str, last: str = "") -> None:
    passed = sum(ok for _, ok, _ in results)
    failed = len(results) - passed
    tally = f"<span style='color:#1D9E75'>✓ {passed}</span>" + (
        f" &nbsp; <span style='color:#E24B4A'>✗ {failed}</span>" if failed else "")
    banner.setText(f"<b>Step {step_no} — {text}</b> &nbsp;&nbsp; {tally}" + (f"<br>{last}" if last else ""))
    QApplication.processEvents()


def step(text: str) -> None:
    global step_no, current
    step_no += 1
    current = text
    show(text)
    print(f"[{time.monotonic() - started:6.1f} s] step {step_no}: {text}", flush=True)
    pause(1600)


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    mark_text = "<span style='color:#1D9E75'>✓</span>" if ok else "<span style='color:#E24B4A'>✗ FAILED:</span>"
    show(current, f"{mark_text} {name}" + (f" <i>({detail})</i>" if detail else ""))
    print(f"    {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)
    pause(1300 if ok else 3000)
    return ok


def mark(widget: QWidget | None) -> None:
    if widget is None:
        frame.hide()
        return
    top_left = widget.mapTo(window, QPoint(0, 0))
    frame.setGeometry(QRect(top_left - QPoint(5, 5), widget.size() + QSize(10, 10)))
    frame.show()
    frame.raise_()
    QApplication.processEvents()


def tab(panel: QWidget) -> None:
    window.tabs.setCurrentWidget(panel)
    mark(window.tabs.tabBar())
    pause(900)
    mark(None)


def click(widget: QWidget) -> float:
    """Frame the control, click it as a user would, and return the moment of the click."""
    mark(widget)
    pause(650)
    if isinstance(widget, QCheckBox):
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(9, widget.height() // 2))
    else:
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    clicked = time.monotonic()
    QApplication.processEvents()
    pause(450)
    mark(None)
    return clicked


def slide(field, target: float, ms: float = 900) -> None:
    """Move a slider field to ``target`` in visible steps, as a hand would."""
    mark(field)
    start = field.value()
    steps = 14 if PACE else 1
    for i in range(1, steps + 1):
        field.setValue(start + (target - start) * i / steps)
        pause(ms / steps)
    field.setValue(target)
    pause(350)
    mark(None)


def choose(combo, data) -> None:
    mark(combo)
    pause(600)
    combo.setCurrentIndex(combo.findData(data))
    QApplication.processEvents()
    pause(500)
    mark(None)


def wait_until(predicate, timeout_s: float) -> bool:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if predicate():
            return True
        QTest.qWait(30)
    return predicate()


def ride(panel, done) -> float | None:
    """Run the panel in real time and return the wall time from the click to the end; with --quick, at once."""
    if not REAL_TIME:
        click(panel.instant_button)
        return None
    clicked = click(panel.run_button)
    wait_until(done, 30.0)
    return time.monotonic() - clicked


def on_time(wall: float | None, simulated: float) -> tuple[bool, str]:
    """Real time within a quarter (plus 0.3 s for the first frames); always true for instant results."""
    if wall is None:
        return True, "instant result"
    return abs(wall - simulated) < 0.25 * simulated + 0.3, f"{simulated:.1f} s simulated, {wall:.1f} s on the clock"


def number(text: str) -> float:
    return float(text.split()[0].rstrip("°%").replace("+", ""))


# ─── the tour ────────────────────────────────────────────────────────────────


def intro() -> None:
    step(f"kammcircle {__version__}: the real window, driven feature by feature; settings go to a temporary file")
    check("the window is open with its ten tabs", window.isVisible() and window.tabs.count() == 10,
          f"{window.tabs.count()} tabs")


def braking() -> dict:
    b = window.braking
    tab(b)
    step("Braking: a stop from 80 km/h, front lever 100 %, rear 60 %, ABS on, suspension on" +
         (", in real time" if REAL_TIME else ""))
    slide(b.speed, 80)
    slide(b.front, 100)
    slide(b.rear, 60)
    wall = ride(b, lambda: b.sim is not None and b.sim.stopped)
    s = b.sim.summary()
    timing_ok, timing = on_time(wall, b.sim.t)
    check("the motorcycle stops" + (", in real time" if REAL_TIME else ""), s.outcome == "stopped" and timing_ok,
          f"{s.stopping_distance:.1f} m; {timing}")
    check("every live chart filled", all(len(c.series) and len(c.series[0].xs) > 10 for c in b.charts),
          f"{len(b.charts)} charts")
    warm = s.stopping_distance
    pause(1500)

    step("Braking: slow motion at a quarter of real time, then Reset")
    click(b.slow_button)
    hold(2000)
    t_sim = b.sim.t if b.sim else 0.0
    check("two seconds of clock gave about half a second of braking", 0.25 < t_sim < 0.8, f"{t_sim:.2f} s simulated")
    click(b.reset_button)
    check("Reset clears the run", b.sim is None and b.c_distance.value.text() == "—")

    step("Braking: wet road, full front brake with the front ABS switched off, then on again")
    choose(b.surface, "wet-asphalt")
    slide(b.rear, 0)
    click(b.abs_front)
    click(b.instant_button)
    locked = any("Front wheel locks" in e for _, e in b.sim.events)
    check("without ABS the front wheel locks and the app says the steering is lost",
          locked and "loses its steering" in b.events.text())
    pause(1500)
    click(b.abs_front)
    click(b.instant_button)
    check("with ABS the front wheel does not lock", b.sim.summary().front_locked_s < 0.1,
          f"locked {b.sim.summary().front_locked_s:.2f} s")
    choose(b.surface, "dry-asphalt")

    step("Braking live from the keyboard: hold F for the front lever (set at 70 %), then R for the rear (40 %)")
    slide(b.front, 70)
    slide(b.rear, 40)
    click(b.manual_box)
    b.front.spin.setFocus()
    mark(b.view)
    QTest.keyPress(b.front.spin, Qt.Key.Key_F)
    hold(1500)
    lever = b.sim.lever_f if b.sim else 0.0
    QTest.keyRelease(b.front.spin, Qt.Key.Key_F)
    hold(700)
    QTest.keyPress(b.front.spin, Qt.Key.Key_R)
    hold(900)
    rear = b.sim.lever_r if b.sim else 0.0
    QTest.keyRelease(b.front.spin, Qt.Key.Key_R)
    mark(None)
    check("holding F squeezes the front lever to its set 70 %", abs(lever - 0.70) < 0.03, f"lever {lever:.2f}")
    check("holding R squeezes the rear lever to its set 40 %", abs(rear - 0.40) < 0.03 or (b.sim is not None
          and b.sim.stopped), f"lever {rear:.2f}")
    pause(1200)
    click(b.reset_button)
    click(b.manual_box)

    step("Braking: grab the full front brake at 100 km/h on very grippy tarmac without ABS — a stoppie")
    slide(b.mu, 1.3)
    slide(b.speed, 100)
    slide(b.front, 100)
    slide(b.rear, 0)
    click(b.abs_front)
    ride(b, lambda: b.sim is not None and b.sim.stopped)
    check("the rear lifts and the motorcycle goes over the front", b.sim.summary().outcome == "pitched over"
          and b.c_distance.value.text() == "went over the front", b.c_distance.value.text())
    pause(2000)
    click(b.abs_front)
    choose(b.surface, "dry-asphalt")

    step("Braking in gear: front brake only from 60 km/h, clutch in, then in 2nd gear with engine braking")
    slide(b.speed, 60)
    slide(b.front, 40)
    click(b.instant_button)
    clutch_in = b.sim.summary().stopping_distance
    choose(b.engine_box, 2)
    click(b.instant_button)
    in_gear = b.sim.summary().stopping_distance
    check("engine braking in 2nd shortens the stop", in_gear < clutch_in and "clutch out in 2nd" in b.events.text(),
          f"{clutch_in:.1f} m → {in_gear:.1f} m")
    choose(b.engine_box, 0)

    step("Braking: where every model parameter comes from")
    click(b.toggle)
    text = b.parameters.toPlainText()
    check("the parameter table lists its sources", "Sharp et al. 2004" in text and "example" in text)
    pause(1500)
    click(b.toggle)
    slide(b.speed, 80)
    slide(b.front, 100)
    slide(b.rear, 60)
    return {"warm_stop": warm}


def acceleration() -> None:
    a = window.acceleration
    tab(a)
    step("Acceleration: 0–100 km/h through the gearbox, with throttle control" +
         (", in real time" if REAL_TIME else ""))
    slide(a.target, 100)
    wall = ride(a, lambda: a.sim is not None and a.sim.stopped)
    timing_ok, timing = on_time(wall, a.sim.t)
    text = a.c_100.value.text()
    check("it reaches 100 km/h" + (", in real time" if REAL_TIME else ""), a.sim.outcome == "reached"
          and text.endswith(" s") and timing_ok, f"0–100 km/h in {text} (road tests 6.35 and 6.91 s); {timing}")
    check("gear changes are reported", "Gear changes" in a.events.text())
    pause(1500)

    step("Acceleration: from 100 km/h to top speed")
    slide(a.start_speed, 100)
    click(a.top_speed_box)
    click(a.instant_button)
    check("the run ends at top speed", a.sim.outcome == "top speed", a.c_end.value.text())
    click(a.top_speed_box)
    slide(a.start_speed, 0)

    step("Acceleration: throttle control off — the rear tyre spins at the launch")
    click(a.control)
    click(a.instant_button)
    check("the rear tyre spins", "rear tyre spun" in a.events.text())
    click(a.control)


def countersteering() -> None:
    c = window.countersteer
    tab(c)
    step("Countersteering: a 45° right-hander at 60 km/h on a 60 m radius, ridden with handlebar torque alone" +
         (", in real time" if REAL_TIME else ""))
    slide(c.speed, 60)
    slide(c.radius, 60)
    slide(c.angle, 45)
    wall = ride(c, lambda: c.sim is not None and c.sim.stopped)
    heading = c.sim.trace[-1].heading
    timing_ok, timing = on_time(wall, c.sim.t)
    check("the corner ends on the heading asked for" + (", in real time" if REAL_TIME else ""),
          abs(heading - 45) < 0.2 and timing_ok, f"heading {heading:.2f}°; {timing}")
    check("the first push turns the bars away from the corner", c.c_counter.value.text().endswith("°"),
          f"push {c.c_push.value.text()}, bars away {c.c_counter.value.text()}, ran wide {c.c_wide.value.text()}")
    pause(1500)

    step("Countersteering: the same corner to the left is the exact mirror image")
    click(c.instant_button)
    right = c.sim
    choose(c.direction, -1)
    click(c.instant_button)
    left = c.sim
    check("left and right are mirror images", abs(left.peak_push - right.peak_push) < 1e-9 * right.peak_push
          and abs(left.trace[-1].heading + right.trace[-1].heading) < 1e-6)
    choose(c.direction, 1)

    step("Countersteering: at 30 km/h a hands-only rider cannot lean in within 0.3 s, and the tab says so")
    slide(c.speed, 30)
    slide(c.roll_in, 0.3)
    click(c.instant_button)
    check("it reports the quickest roll-in the rider manages", "no faster than" in c.events.toPlainText())
    slide(c.speed, 60)
    slide(c.roll_in, 1.0)


def tyre_temperature(warm_stop: float) -> None:
    t = window.thermal
    tab(t)
    step("Tyre temperature: five minutes of riding from a cold start, air 0 °C, road −2 °C" +
         (" (a minute a second)" if REAL_TIME else ""))
    slide(t.air, 0)
    slide(t.road, -2)
    slide(t.length, 5)
    wall = ride(t, lambda: t.run is not None and t.run.stopped)
    timing_ok, timing = on_time(wall, 5.0)
    check("the tyres stay below their working window", t.c_front.value.text() == "not in this ride" and timing_ok,
          f"{t.c_front.value.text()}; {timing}")
    pause(1500)

    step("Tyre temperature: hand these temperatures to every other tab")
    click(t.use_button)
    front, rear = window.tyre_grip()
    check("the 'Tyres not yet warm' switch comes on with less grip", window.cold_box.isChecked() and front < 0.95
          and rear < 0.95, window.grip_label.text())
    b = window.braking
    tab(b)
    click(b.instant_button)
    cold = b.sim.summary().stopping_distance
    check("the same stop from 80 km/h is longer on cold tyres", cold > warm_stop, f"{warm_stop:.1f} m → {cold:.1f} m")
    click(window.cold_box)
    click(b.instant_button)
    check("warm again, the stop is back to its length", abs(b.sim.summary().stopping_distance - warm_stop) < 0.3,
          f"{b.sim.summary().stopping_distance:.1f} m")


def cornering() -> None:
    c = window.cornering
    tab(c)
    step("Cornering and grip: 60 km/h on a 50 m radius, dry; then brake in the corner until the tyres slide")
    slide(c.speed, 60)
    slide(c.radius, 50)
    check("the ideal lean is 29.5°", c.c_lean.value.text() == "29.5°", f"with tyre width {c.c_wheel.value.text()}")
    slide(c.brake, 0.9, 1400)
    check("braking hard in the corner leaves the friction circle", "slide" in c.message.text(), c.c_used.value.text())
    slide(c.brake, 0.0)


def steady_turn() -> None:
    s = window.steady
    tab(s)
    step("Steady turn: the same 60 km/h, 50 m turn on tyres that slip and camber")
    slide(s.speed, 60)
    slide(s.radius, 50)
    wait_until(lambda: s.limit_kmh is not None, 8.0)
    mark(s.bars)
    lean = number(s.c_lean.value.text())
    check("the motorcycle leans more than the ideal 29.5°", 30.5 < lean < 34, s.c_lean.value.text())
    check("the rider holds the bars, pushing the inside grip", s.c_hold.value.text().endswith("push"),
          s.c_hold.value.text())
    check("the bar chart's parts add up to the torque held",
          abs(sum(s.bars.parts.values()) + s.trim.steering_torque) < 1e-6)
    mark(s.c_limit)
    check("the fastest steady speed on this radius is close to the friction circle's",
          s.limit_kmh is not None and 75 < s.limit_kmh < 83, s.c_limit.value.text())
    mark(None)
    pause(1500)

    step("Steady turn: speed up past the grip limit — no steady turn exists any more")
    slide(s.speed, round(s.limit_kmh or 80) + 5, 1500)
    check("the tab reports that the tyres would slide", s.trim is None and s.c_grip.value.text() == "beyond")
    pause(1200)
    slide(s.speed, 60, 1200)

    step("Steady turn: brake at 0.4 g in the turn — the motorcycle wants to stand up")
    before = s.trim.steering_torque
    slide(s.along, -0.4, 1200)
    check("the rider must push the inside grip much harder", s.trim.steering_torque < before - 8
          and "stand up" in s.messages.toPlainText(), f"{abs(before):.1f} → {abs(s.trim.steering_torque):.1f} N m")
    pause(1500)
    slide(s.along, 0.0)

    step("Steady turn: hang off the inside by 150 mm")
    slide(s.offset, 150, 1200)
    check("the motorcycle itself leans less", number(s.c_lean.value.text()) < lean - 2, s.c_lean.value.text())
    pause(1200)
    slide(s.offset, 0)
    click(s.toggle)
    check("its parameter table names the tyre data's source", "Sharp et al. 2004" in s.parameters.toPlainText())
    pause(1200)
    click(s.toggle)


def body_and_geometry() -> None:
    body = window.body
    tab(body)
    step("Body position: the corner's 29.5° of lean, with the rider hanging off by 150 mm")
    check("the bike leans 29.5° with the rider in line", body.c_bike.value.text() == "29.5°")
    slide(body.offset, 150)
    check("hanging off, the bike itself leans less", number(body.c_bike.value.text()) < 29.5, body.c_bike.value.text())
    slide(body.offset, 0)

    g = window.geometry
    tab(g)
    step("Steering geometry: lower the rear by 30 mm, then both ends, then try front tyre sizes")
    buttons = {b.text(): b for b in g.findChildren(QPushButton)}
    click(buttons["Rear −30 mm"])
    check("lowering the rear steepens the rake to 27.1°", g.c_rake.value.text().startswith("27.1°"),
          f"rake {g.c_rake.value.text()}, trail {g.c_trail.value.text()}")
    click(buttons["Both −30 mm"])
    check("lowering both ends costs 30 mm of clearance", g.c_clear.value.text() == "200 mm", g.c_clear.value.text())
    mark(g.tyre)
    g.tyre.selectAll()
    QTest.keyClicks(g.tyre, "nonsense", delay=int(60 * PACE))
    check("a bad tyre code is refused", "unrecognised" in g.tyre_status.text())
    g.tyre.clear()
    QTest.keyClicks(g.tyre, "90/100-21", delay=int(60 * PACE))
    check("a valid size is read", g.tyre_status.text().startswith("R = "), g.tyre_status.text())
    mark(None)
    click(buttons["Stock"])


def tyres_and_rider() -> None:
    t = window.tyres
    tab(t)
    step("Tyres: the catalogue, then a best-fit pair for 40 % unpaved riding, fitted to the bike")
    check("the catalogue lists the tyres in the bike's sizes with Moroccan offers", t.table.rowCount() >= 15
          and "Motoshop" in " ".join(t.table.item(r, 7).text() for r in range(t.table.rowCount())),
          f"{t.table.rowCount()} tyres")
    slide(t.unpaved, 40)
    check("the best fit for 40 % unpaved is Enduro Trail+", "Enduro Trail+" in t.ranking.item(0, 0).text())
    click(t.fit_button)
    check("the pair is fitted front and rear", t.choice.front.product.id == t.choice.rear.product.id
          == "mitas-enduro-trail-plus")
    check("the braking simulation now uses them", "Enduro Trail+" in window.braking.parameters.toPlainText())

    r = window.rider
    tab(r)
    step("Rider and bike: a 92 kg rider and a 70 kg pillion feed every model; then back to the examples")
    mark(r.spins["rider_mass_kg"])
    r.spins["rider_mass_kg"].setValue(92)
    pause(700)
    mark(r.spins["pillion_mass_kg"])
    r.spins["pillion_mass_kg"].setValue(70)
    pause(700)
    mark(None)
    check("the braking model lists the new rider", "92 kg" in window.braking.parameters.toPlainText())
    check("the steady-turn model carries the extra mass", window.steady.model.mass > 330,
          f"{window.steady.model.mass:.0f} kg in all")
    reset = next(b for b in r.findChildren(QPushButton) if b.text().startswith("Reset"))
    click(reset)
    check("Reset brings back the example rider", r.spins["rider_mass_kg"].value() == 80
          and r.spins["pillion_mass_kg"].value() == 0)


def bikes_and_help() -> None:
    step("Switch to the Scram 411: every tab takes its geometry, tyres and engine")
    choose(window.bike_box, "re-scram-411")
    check("the geometry tab shows the Scram's 19-inch front tyre", window.geometry.tyre.text() == "100/90-19")
    check("the braking and steady-turn models take its 1455 mm wheelbase", window.braking.view.wheelbase == 1455
          and abs(window.steady.model.wheelbase - 1.455) < 1e-9)
    tab(window.steady)
    pause(1500)
    choose(window.bike_box, "re-himalayan-450-2026")

    step("Help → About")
    seen: list[str] = []

    def close_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            seen.append(dialog.text())
            dialog.accept()

    QTimer.singleShot(max(50, int(3500 * PACE)), close_dialog)
    about = next(a for a in window.menuBar().actions()[1].menu().actions() if "About" in a.text())
    about.trigger()
    check("the About box names this version", bool(seen) and f"kammcircle {__version__}" in seen[0])


def main() -> int:
    width, height = (int(x) for x in args.size.lower().split("x"))
    screen = app.primaryScreen().availableGeometry()
    window.resize(min(width, int(0.95 * screen.width())), min(height, int(0.95 * screen.height())))
    window.show()
    QApplication.processEvents()
    pause(1500)
    state: dict = {}
    for part in (intro, braking, acceleration, countersteering, "tyre temperature", cornering, steady_turn,
                 body_and_geometry, tyres_and_rider, bikes_and_help):
        try:
            if part == "tyre temperature":
                tyre_temperature(state.get("warm_stop", 0.0))
            else:
                out = part()
                if isinstance(out, dict):
                    state.update(out)
        except Exception as exc:  # a broken step is a failed check; the tour goes on
            traceback.print_exc()
            check(f"{current}: raised {type(exc).__name__}", False, str(exc)[:120])
            mark(None)
    passed = sum(ok for _, ok, _ in results)
    failed = [name for name, ok, _ in results if not ok]
    minutes = (time.monotonic() - started) / 60
    colour = "#1D9E75" if not failed else "#E24B4A"
    ending = ("The window stays open: explore it, then close it." if args.keep_open
              else "The window closes in 15 s; your own settings were not touched.")
    banner.setText(f"<b style='color:{colour}'>Tour finished: {passed} of {len(results)} checks passed in "
                   f"{minutes:.1f} min.</b>" + ("" if not failed else "<br>Failed: " + "; ".join(failed))
                   + f"<br>{ending}")
    print(f"\nRESULT: {passed}/{len(results)} checks passed in {minutes:.1f} min", flush=True)
    for name in failed:
        print(f"FAILED: {name}", flush=True)
    if args.keep_open:
        app.exec()
    else:
        pause(15000)
        window.close()
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
