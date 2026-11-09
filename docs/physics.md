# Physics reference

Every formula below is implemented in `kammcircle.physics` and tested in `tests/test_physics.py`. Source ids resolve in [`sources.md`](sources.md).

## 1. Steady cornering lean

Rear view, steady speed `v`, constant radius `r`, flat road. The road pushes on the contact patch with a normal force `N = mg` (up) and a grip force `F = mv²/r` (towards the centre of the turn). For the bike neither to fall in nor to stand up, their sum must point straight at the combined (bike + rider) centre of gravity:

```
tan θ = F / N = v² / (g·r) = lateral acceleration in g
```

| Lateral g | 0.25 | 0.5 | 0.7 | 1.0 | 1.2 |
|---|---|---|---|---|---|
| Lean θ | 14.0° | 26.6° | 35.0° | 45.0° | 50.2° |

`lean_angle_deg(60, 50)` → 29.5° (0.57 g). Illustration: `illustrations/04-lean-force-balance.svg`.

## 2. Grip limit

The tyre can supply at most `F ≤ μ·N`, so the bike slides when `tan θ > μ`:

```
θ_max = atan(μ)        (no braking, point mass)
```

| Surface (`data/surfaces.json`) | μ used | θ_max |
|---|---|---|
| Dry asphalt (motorcycle tyres peak ≈ 1.2, locked 0.7–0.9) [sae-2010-01-0054] | 1.0 | 45.0° |
| Wet asphalt 0.50–0.70 [hpwizard] | 0.6 | 31.0° |
| Gravel 0.60 — gravel slides on itself [hpwizard] | 0.55 | 28.8° |
| Loose gravel / sand 0.2–0.3 (indicative) [learndrivingtheory] | 0.3 | 16.7° |

45° of lean already needs 1 g [cornerspeed], so on dry asphalt the hard parts often touch down first: Carter, Rose and Pentecost put the maximum lean of most motorcycles between 25° and 50° and conclude that, for many of them, the geometric limit is more restrictive than the friction limit [jsheld-lean]. On wet asphalt (μ 0.5–0.7) the grip ceiling falls to 27–35°, and on loose gravel lower still, so grip becomes the limit for any bike whose hard parts clear that angle.

## 3. Friction circle (braking and cornering share one budget)

```
√(a_lat² + a_long²) ≤ μ·g          grip_usage(lat, brake, μ) = √(lat² + brake²) / μ
v_max(r, μ, b) = √( √(μ² − b²) · g · r )
```

Braking at 0.6 g on μ = 1.0 leaves only 0.8 g for cornering. Illustration: `illustrations/05-lean-grip-friction-circle.html`.

## 4. Real lean is larger than the ideal formula

The basic formulas consistently underestimate measured lean [jsheld-lean]. The main reason is that a tyre has width: as it leans, the contact point moves off the wheel's centre plane towards the inside, so the bike must lean further to keep the force line through the centre of gravity. With `t` the radius of the tyre's cross-section at the crown and `h` the height of the combined centre of gravity with the bike upright:

```
φ = φ0 + asin( t·sin φ0 / (h − t) )
```

**Derivation.** The contact point P lies directly below the crown centre C, at depth `t`. The centre of gravity G lies in the wheel plane, at distance `h − t` from C, so CG leans at the wheel's lean φ. The road force runs from P to G and must lean at φ0. In triangle PCG the angle at P is φ0, the angle at C is 180° − φ, and therefore the angle at G is φ − φ0. The law of sines gives `t / sin(φ − φ0) = (h − t) / sin φ0`, which rearranges to the formula above. `tests/test_physics.py` checks it against an explicit construction of the leaned bike.

Carter, Rose and Pentecost give the same correction, after Cossalter's *Motorcycle Dynamics*, as their equations (16) and (17), writing `t` for the full tyre width so that `t/2` plays the role of the crown radius here [jsheld-lean]. In their riding tests the correction reduced the average error of the basic formula, but the measured leans still sat above it on average. Wider tyres (140 against 120 mm) therefore need slightly more lean for the same corner. In the app, `lean_angle_with_tyre_deg(v, r, t, h)` takes `t` and `h` from the rider and bike variables.

## 5. Rider position (illustration 03)

For a given corner the combined lean is fixed. Moving the rider's centre of gravity sideways by `s` (relative to the bike's plane) changes only how far the bike leans. The combined centre of gravity is a fixed vector in the bike's frame, so:

```
φ_bike = φ_combined − atan( m_r·s / (m_b·h_b + m_r·h_r) )
s > 0 (inside, tarmac)  → the bike leans less → more tyre and clearance margin
s < 0 (outside, gravel) → the bike leans more under an upright rider; weight on the outside peg
```

`bike_lean_for_rider_offset_deg(...)`. Royal Enfield publishes no centre-of-gravity heights for these bikes, so the app asks for measured or assumed values and labels its examples as such.

## 6. Hard-part clearance angle

Royal Enfield publishes no lean angle for the Scram 411 (it is in neither the India nor the US owner's manual, nor in the specification sheets) nor for the Himalayan 450. Measure instead: with the rider aboard and the bike upright, take the footpeg tip's height `h` and its lateral distance `w` from the tyre centreline:

```
h·cos θ − w·sin θ = 0   →   θ_clearance = atan(h / w)
```

`clearance_angle_deg(h, w)` ignores tyre width, so the real value is a few degrees higher.

## 7. Steering geometry

- **Rake** θ: the steering axis's angle from vertical (head angle 64° → rake 26° on the Himalayan 450 [mur-450-datasheet]).
- **Fork offset** d: the perpendicular distance from the steering axis to the front axle.
- **Trail**: the ground distance from where the steering axis meets the road to the contact patch, which sits behind it. It is the self-centring lever.

```
trail = (R·sin θ − d) / cos θ
```

Himalayan 450: R = 347.7 mm (90/90-21), published rake 26° and trail 124 mm ⇒ d = R·sin θ − trail·cos θ ≈ 41 mm (derived with `fork_offset_mm()`). Scram 411: 26.2° / 104.6 mm [nz-autocar-scram] with R = 331.3 mm (100/90-19) ⇒ d ≈ 52.4 mm (derived).

## 8. Lowering

Lowering one end pitches the chassis about the other:

```
Δpitch = atan( (rear_drop − front_drop) / wheelbase )     rake' = rake + Δpitch
```

Himalayan 450, wheelbase 1510 mm, 30 mm drop (`lowering_geometry()`):

| Setup | Rake | Trail | Ground clearance (≈ mean drop) | Feel |
|---|---|---|---|---|
| Stock | 26.0° | 124 mm | 230 mm | — |
| Rear −30 | 27.1° | ≈ 132 mm | ≈ 215 mm | slower, heavier turn-in; stable; runs wide |
| Front −30 | 24.9° | ≈ 116 mm | ≈ 215 mm | quicker, lighter; less stable; headshake risk |
| Both −30 | 26.0° | 124 mm | ≈ 200 mm | handling kept, clearance lost |

Not modelled: a rear lowering link also changes the linkage leverage ratio (a softer rear, more dynamic sag, hence more dynamic rake); rear-axle drop is not seat drop; side-stand length. Illustration: `illustrations/01-lowering-geometry.html` (angle changes drawn ×5).

## 9. Tyre size arithmetic

```
sidewall = width × aspect / 100          D = 2·sidewall + 25.4·rim (in)
```

90/90-21 → 695.4 mm · 140/80-17 → 655.8 mm · 100/90-19 → 662.6 mm · 120/90-17 → 647.8 mm. Going from 120/90 to 120/80 lowers the sidewall from 108 to 96 mm, so the axle sits 12 mm lower.

## 10. Not modelled yet

- Tyre force from slip angle **and camber thrust** (for example a motorcycle "magic formula" tyre model) instead of a single μ.
- Load transfer under braking and acceleration (front and rear μ demand differ), suspension sag and pitch dynamics.
- Countersteering dynamics, gyroscopic and steering-head torques, weave and wobble modes (where trail and rake matter dynamically).
- Temperature, pressure and wear effects on μ and on the contact patch (see `modifiers_not_quantified` in `data/surfaces.json`).
- Road camber and banking: subtract the bank angle from the lean relative to the road.
