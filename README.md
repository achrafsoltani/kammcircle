# kammcircle

kammcircle is a desktop motorcycle simulator built on Kamm's circle, the idea that braking and cornering draw on one shared grip budget. Its first time-stepped simulation is braking: you set the speed, the surface and the levers, or brake live from the keyboard, and watch the fork dive, the load move onto the front wheel, the tyres slip, the ABS cycle, a wheel lock or the rear rise into a stoppie. Version 0.5 adds a second simulation, acceleration, with the manufacturers' gearing, launch and gear changes, wheelspin, wheelies and air drag. Version 0.4 added a tyre catalogue that feeds the simulation and records what is on sale in Morocco, a best-fit ranking of tyre pairs for your riding, and the load of a pillion and luggage. Calculators for steady cornering, body position, footpeg clearance and steering geometry complete it. It ships with sourced data for the Royal Enfield Himalayan 450 (2026) and Scram 411.

![The braking simulation with suspension, halfway through an ABS stop from 80 km/h](docs/screenshots/00-braking.png)

## What it does

| Tab | What you can explore |
|---|---|
| Braking (simulation) | A real-time run, in slow motion if you like, of a stop from any speed on any surface: front and rear brake levers (set in advance or held live on F and R), ABS on or off at each wheel, and the outcome, from a clean stop to a locked front wheel or a stoppie that goes over the bars. Live charts show speed, deceleration, the load on each wheel, suspension travel, pitch, wheel slip, and how much of each lever's demand reaches the brake; the view also shows how far the rake and trail shrink as the nose dives. Every model parameter is listed with where it comes from. |
| Acceleration (simulation) | A launch or a roll-on, in real time or at once, through the published gearing: launch speed, shift speed, throttle and optional throttle control (a skilled rider or traction control), on any surface, to a target speed or to the top speed. Live charts show speed, acceleration and the load on each wheel, engine speed and gear, rear-wheel slip, squat and pitch; results give the 0–50 and 0–100 km/h times. |
| Cornering and grip | Speed, corner radius, surface grip and braking give the lean the corner needs, the grip-limited lean, how much of the friction circle is in use, and the fastest speed the corner allows. An optional correction accounts for tyre width, which makes a real bike lean further than the ideal formula says. |
| Body position | For the lean a corner demands, moving the rider inside or outside the bike's plane changes how far the bike itself leans: less when hanging off on tarmac, more when standing on the outside peg on gravel. |
| Steering geometry | Lowering the rear, the front or both changes rake, trail and ground clearance. The side view exaggerates the angle changes five times so that they are visible, while the numbers stay real. A different front tyre size changes the trail too. |
| Tyres | Fit a front and a rear tyre from the catalogue: the simulation takes their size (wheel radius, crown radius) and the tab checks their load and speed ratings against your load and the original fitment. The catalogue lists every tyre recorded in the bike's sizes, with its road/off-road split where the maker publishes one, the maker's dimensions, and the prices and stock seen at Moroccan retailers with the date checked. A best-fit ranking scores front-and-rear pairs against your share of unpaved riding and says why it left any tyre out. |
| Rider and bike | Your own values (rider mass, centre-of-gravity heights, sag, tyre crown radius, footpeg geometry, and a pillion's and luggage's mass and position) are saved for your user account only, and the footpeg clearance lean follows from them. The selected bike's catalogue figures are listed with their status and links to their sources. |

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

Every 0.5 ms the simulation moves the sprung motorcycle and rider, a fork that slides along the steering axis, a rear wheel that travels up and down, compliant tyres that can leave the road, and two spinning wheels, turning each wheel's slip into braking force with the Magic Formula tyre fit published by Sharp, Evangelou and Limebeer (2004). A rigid model, without suspension, remains a tick-box away. Their equations, the ABS model and every parameter, each with its source or labelled as a stand-in, are in sections 10 and 11 of [`docs/physics.md`](docs/physics.md). The tests check the rigid model against the textbook load transfer, the rear-lift threshold `g·(L − b)/h`, the limit `v²/(2·μ·g)` and a skilled rider's best lever split, and the suspended one for exact static equilibrium, energy conservation and agreement with the rigid model when its springs are made stiff.

## Data and provenance

The bike, tyre and surface figures live in `src/kammcircle/data/`. Tyre prices are what two Moroccan retailers showed on the date recorded with them; check before buying. Each one carries a status: `verified` when it was read from a cited source, `derived` when it is computed from verified figures with the formula recorded, and `unpublished` when the manufacturer gives no figure, in which case the value stays empty rather than being guessed. Royal Enfield, for instance, publishes no lean angle for either bike, so the app asks you to measure the footpeg geometry instead. Source ids resolve in [`docs/sources.md`](docs/sources.md), and the tests fail if a status is unknown, a source id does not resolve or a derived value no longer recomputes.

## Limitations

The braking simulation's springs are linear, without preload or the rising rate of a real fork, so its dive is probably exaggerated; the rear wheel moves straight up and down rather than on the swingarm's arc; aerodynamic drag and engine braking are left out; and a locked front wheel does not make the motorcycle fall as it would on the road (the app says so). The other tabs are steady-state calculators: constant speed on a constant radius over a flat road, with one friction coefficient per surface. Next come a cornering tyre model with camber thrust, a corner ridden in time with countersteering, and the stability modes; the list is at the end of [`docs/physics.md`](docs/physics.md).

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
