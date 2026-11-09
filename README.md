# kammcircle

kammcircle is a desktop motorcycle simulator built on Kamm's circle, the idea that braking and cornering draw on one shared grip budget. Version 0.2 adds its first time-stepped simulation, braking: you set the speed, the surface and the levers, or brake live from the keyboard, and watch the tyres slip, the load move onto the front wheel, the ABS cycle, a wheel lock or the rear rise into a stoppie. Calculators for steady cornering, body position, footpeg clearance and steering geometry complete it. It ships with sourced data for the Royal Enfield Himalayan 450 (2026) and Scram 411.

![The braking simulation, halfway through an ABS stop from 80 km/h](docs/screenshots/00-braking.png)

## What it does

| Tab | What you can explore |
|---|---|
| Braking (simulation) | A real-time run, in slow motion if you like, of a stop from any speed on any surface: front and rear brake levers (set in advance or held live on F and R), ABS on or off at each wheel, and the outcome, from a clean stop to a locked front wheel or a stoppie that goes over the bars. Live charts show speed, deceleration, the load on each wheel, wheel slip, and how much of each lever's demand reaches the brake. Every model parameter is listed with where it comes from. |
| Cornering and grip | Speed, corner radius, surface grip and braking give the lean the corner needs, the grip-limited lean, how much of the friction circle is in use, and the fastest speed the corner allows. An optional correction accounts for tyre width, which makes a real bike lean further than the ideal formula says. |
| Body position | For the lean a corner demands, moving the rider inside or outside the bike's plane changes how far the bike itself leans: less when hanging off on tarmac, more when standing on the outside peg on gravel. |
| Steering geometry | Lowering the rear, the front or both changes rake, trail and ground clearance. The side view exaggerates the angle changes five times so that they are visible, while the numbers stay real. A different front tyre size changes the trail too. |
| Rider and bike | Your own values (rider mass, centre-of-gravity heights, tyre crown radius and footpeg geometry) are saved for your user account only, and the footpeg clearance lean follows from them. The selected bike's catalogue figures are listed with their status and links to their sources. |

## Install and run

kammcircle needs Python 3.10 or later and uses PySide6 (Qt 6).

```bash
git clone https://github.com/achrafsoltani/kammcircle.git
cd kammcircle
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/kammcircle
```

`python -m kammcircle` starts the app as well.

## The physics

Every formula is a small pure function in `kammcircle.physics`, written with degrees at its interface, millimetres for chassis and tyre geometry, and metres, metres per second and kilograms for dynamics. [`docs/physics.md`](docs/physics.md) gives each formula with its derivation and worked numbers. The test suite pins the reference values below, and it checks the two derived formulas (the tyre-width lean and the rider-offset lean) against explicit geometric constructions rather than against their own output.

| Quantity | Value |
|---|---|
| Lean for 1 g of lateral acceleration | 45.0° |
| 60 km/h on a 50 m radius | 0.57 g, 29.5° |
| Grip-limited lean for μ = 1.0 / 0.6 / 0.3 | 45.0° / 31.0° / 16.7° |
| Himalayan 450 front tyre radius (90/90-21) | 347.7 mm |
| Himalayan 450 fork offset, back-solved from 26° and 124 mm | ≈ 41 mm |
| Himalayan 450 rear lowered 30 mm | rake 27.1°, trail ≈ 132 mm |
| Himalayan 450 front lowered 30 mm | rake 24.9°, trail ≈ 116 mm |
| Himalayan 450 both ends lowered 30 mm | rake 26°, trail 124 mm, ground clearance 230 → 200 mm |

## The braking simulation

Every 0.5 ms the simulation solves the contact loads of a rigid motorcycle and rider on two spinning wheels, turns each wheel's slip into braking force with the Magic Formula tyre fit published by Sharp, Evangelou and Limebeer (2004), and integrates the wheels' spin, the speed, and the pitch once the rear wheel lifts. Its equations, its ABS model and its parameters, each with its source or labelled as a stand-in, are in section 10 of [`docs/physics.md`](docs/physics.md). The tests check it against the textbook load transfer, the rear-lift threshold `g·(L − b)/h`, the limit `v²/(2·μ·g)`, and a skilled rider's best lever split.

## Data and provenance

The bike, tyre and surface figures live in `src/kammcircle/data/`. Each one carries a status: `verified` when it was read from a cited source, `derived` when it is computed from verified figures with the formula recorded, and `unpublished` when the manufacturer gives no figure, in which case the value stays empty rather than being guessed. Royal Enfield, for instance, publishes no lean angle for either bike, so the app asks you to measure the footpeg geometry instead. Source ids resolve in [`docs/sources.md`](docs/sources.md), and the tests fail if a status is unknown, a source id does not resolve or a derived value no longer recomputes.

## Limitations

The braking simulation has no suspension yet, so it shows no fork dive and moves the load to the front without the springs' delay; it also leaves out aerodynamic drag and engine braking, and a locked front wheel does not make the motorcycle fall as it would on the road (the app says so). The other tabs are steady-state calculators: constant speed on a constant radius over a flat road, with one friction coefficient per surface. Next come suspension, a cornering tyre model with camber thrust, a corner ridden in time with countersteering, and the stability modes; the list is at the end of [`docs/physics.md`](docs/physics.md).

## Development

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest                                           # physics, data provenance and offscreen UI tests
.venv/bin/python tools/gen_sources_md.py                   # regenerate docs/sources.md after editing sources.json
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/screenshots.py   # regenerate docs/screenshots/
```

The reference illustrations in [`docs/illustrations/`](docs/illustrations.md) are the design masters for the app's views.

## Licence

kammcircle is released under the MIT Licence; see [`LICENSE`](LICENSE).
