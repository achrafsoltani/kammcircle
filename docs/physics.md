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

## 10. Braking dynamics (the simulation)

The Braking tab integrates the equations of motion every 0.5 ms (`kammcircle.sim.braking`). The motorcycle and rider form one rigid body, of mass `m`, with its centre of gravity at height `h` and a distance `b` ahead of the rear contact patch, and pitch inertia `I_G` about it. It rides on two spinning wheels with inertias `I_f`, `I_r` and radii `R_f`, `R_r`. The rider's levers set the brake torques, the tyres turn wheel slip into force, and the contact loads follow.

**Slip and tyre force.** The slip ratio is `κ = (ω·R − v) / |v|`: 0 when the wheel rolls freely, −1 when it is locked. The braking force is `F = N·φ(κ, N)`, from the Magic Formula that Sharp, Evangelou and Limebeer fitted to a 160/70 ZR17 tyre [sharp-2004]:

```
Fx = Dx·sin( Cx·atan( Bx·κ − Ex·(Bx·κ − atan(Bx·κ)) ) )      Dx = λμ·(pDx1 + pDx2·dfz)·Fz      dfz = (Fz − Fz0)/Fz0
```

Its peak coefficient is 1.2017 at the 1600 N nominal load, near 11 % slip, and the locked coefficient is about 0.81, in line with the 0.7–0.9 measured for locked motorcycle tyres [sae-2010-01-0054]. The peak falls slightly as the load rises. Another surface scales the peak to its μ through `λμ` and keeps the slip stiffness, so the peak moves to a smaller slip.

**Wheels.** `I·dω/dt = −R·F − T`. The update is implicit in the tyre's slip stiffness, which keeps the stiff tyre–wheel loop stable. A wheel whose speed reaches zero under braking locks, and it stays locked while the brake torque can hold the tyre's pull, `T ≥ R·|F|`.

**Loads with both wheels down.** Vertical balance, and the balance of angular momentum about the centre of gravity:

```
N_f + N_r = m·g
(L − b)·N_f − b·N_r + h·(F_f + F_r) + I_f·dω_f/dt + I_r·dω_r/dt = 0
```

Without the wheel terms this is the textbook load transfer, `N_f = (m·g·b + m·a·h) / L` for a deceleration `a`. The spinning wheels add a little to it: the calipers must also slow the wheels, so they push the nose down slightly harder.

**Rear lift.** The rear wheel unloads once the deceleration reaches `g·(L − b)/h`. From then on the body pitches about the front axle, and each step solves for three unknowns (the front load, the axle's acceleration and the pitch acceleration) from the two force balances and the angular-momentum balance.

**Point of no return.** A stoppie becomes a flip once the pitch energy about the front axle, `½·I_A·θ'²`, can lift the centre of gravity over the axle: `½·I_A·θ'² ≥ m·g·(d − z)`, with `I_A` the pitch inertia about the axle, `d` the distance from the axle to the centre of gravity and `z` its current height above the axle. The run ends there. With the lever held constant past the lift point the model always ends this way, because the lift threshold falls as the rear rises; riders ease the lever, which the live mode lets you do.

**ABS.** A generic slip-band controller, not any manufacturer's algorithm: while the slip exceeds 1.3 × the tyre's peak slip it removes brake torque at ten times the full torque per second; once the slip has recovered to the peak it restores torque at three times the full torque per second, never beyond the rider's demand. In the tests, from 80 km/h on dry asphalt, it stops within 10 % of the best fixed lever split that never locks a wheel.

**Parameters and where they come from** (`data/sim-parameters.json`; the Braking tab lists each value with its basis):

| Parameter | Basis |
|---|---|
| Tyre braking curve | Sharp, Evangelou and Limebeer (2004), Table I, a sport radial tyre; no curve is published for the Royal Enfield tyres |
| Wheel spin inertias, 0.484 and 0.638 kg m² | Measured on a Suzuki GSX-R1000 (same paper, Table A.II), used as stand-ins |
| Pitch inertia | The same paper's body inertias (main frame with the rider's lower body, 22.013 kg m²; rider's upper body, 1.347 kg m²) plus the parallel-axis terms for the bike's and the rider's centres of gravity |
| Brake torque at full lever or pedal | Modelling choice: 1.3 × 1.2 × the most load the wheel can carry × its radius, enough to lock either wheel on dry asphalt |
| Masses, wheelbase, wheel radii | Catalogue data |
| Centre-of-gravity heights and positions, weight split | The rider's own values, or labelled examples; the Scram 411's split comes from measured axle weights |

**Not modelled in the rigid model:** suspension (section 11 adds it), tyre relaxation length, aerodynamic drag, rolling resistance, engine braking, rear-wheel-lift mitigation in the ABS, and the fall that follows a locked front wheel on a real motorcycle.

## 11. Braking with suspension

With Suspension ticked (the default), the Braking tab runs `kammcircle.sim.suspension`. Three bodies move in the plane: the sprung mass (frame, engine and rider), the front unsprung mass (wheel and fork lowers), which slides along the steering axis, and the rear unsprung mass (wheel and swingarm), which moves perpendicular to the frame. The generalised coordinates are `q = (x, z, θ, s_f, s_r)`: the sprung centre of gravity, the pitch (positive nose down) and the two suspension compressions from full extension. Each axle's position is `r_s + R(θ)·(a + s·e)`, with `e` the direction of travel fixed in the frame, so the equations follow from the bodies' Jacobians by virtual work:

```
M(q)·q'' = Q(q, q')        M = diag(m_s, m_s, I_s, 0, 0) + Σ m_u·Jᵀ·J        Q = Σ Jᵀ·(F_tyre − m_u·g − m_u·c) − (springs and dampers) + (brake reactions on θ)
```

where `c` collects each axle's velocity-product acceleration, `−R(θ)·b·θ'² + 2·R'(θ)·e·s'·θ'`. The 5 × 5 system is solved every 0.5 ms; wheel spin, the tyre force, the ABS and the lock logic are those of section 10.

- **Fork.** The front wheel slides along the steering axis, so the fork carries the component of both the normal force and the braking force along that axis: `F_axial = N·cos ε + |F_x|·sin ε`. The braking force therefore compresses a telescopic fork on top of the load transfer.
- **Springs.** Linear, without preload, with rates set so that the rider-aboard sag is the share of travel you enter (the example is about 30 %, from Touratech's set-up guide [touratech-sag]): `k_f = (N_f − m_uf·g)·cos ε / sag_f` and `k_r = (N_r − m_ur·g) / sag_r`. Stiff end stops act at full extension and full compression.
- **Damping.** A fraction of critical damping, the same in compression and rebound (0.3, a modelling choice: no damping data is published for these bikes).
- **Tyres.** Radial springs with light damping that can leave the road: a stoppie begins when the rear tyre's load reaches zero, with no switch of model. Radial stiffness and the unsprung masses are stand-ins measured on a GSX-R1000 [sharp-2004].
- **Steering under braking.** Nose-down pitch θ reduces the rake to `ε − θ`, and the trail with it (section 7); the Braking tab shows both during the stop. The fork's own compression moves the axle along the steering axis and so leaves rake and trail unchanged.

**Checks** (`tests/test_suspension.py`): the static state is an exact equilibrium (the sag, the loads and zero pitch are held to within 10⁻⁶); with damping and tyre grip removed, the energy error halves when the time step halves (first-order convergence, so the equations conserve energy, including a wheel leaving the road); with very stiff springs and tyres the stopping distance matches the rigid model within 0.1 %; and steady braking reproduces the textbook load transfer for the current geometry within 4 %.

**Not modelled with suspension yet:** spring preload, progressive (rising-rate) fork and linkage springs, separate compression and rebound damping, the swingarm's arc and the anti-squat and anti-rise geometry it brings, frame and fork flex, tyre relaxation length, aerodynamic drag, rolling resistance and engine braking. Linear springs without preload or progression probably exaggerate the dive of a real fork, whose rising rate resists bottoming.

## 12. Tyres in the simulation

The Tyres tab fits a front and a rear tyre from `data/tyres.json`, which records each listing's size, load index, speed symbol, tube type, the maker's E.T.R.T.O. design dimensions where they are published, and the prices and stock seen at Moroccan retailers, with the date checked [motoshop-ma-tyres] [evobike-ma-tyres]. The fitted tyres change the simulation in three ways:

- **Wheel radius.** Half the maker's design overall diameter when it is published, otherwise the nominal size from the code (section 9). It sets the slip ratio, the brake torque needed to lock the wheel, and the geometry.
- **Crown radius.** Half the section width, the round-profile approximation of section 4, used by the tyre-width lean correction unless you enter your own.
- **Ratings.** The load index and speed symbol are read through the standard tables [tire-code-wikipedia] (54 = 212 kg, 69 = 325 kg; S = 180, T = 190, H = 210 km/h). The tab compares them with your load at rest and with the original fitment's ratings, and a braking run that starts above a tyre's speed rating says so.

Grip does **not** change with the tyre: no maker publishes grip curves for these tyres, and no measured motorcycle comparison of braking between tyre classes was found [motorcycle-com-adv-tyres], so every tyre uses the curve of section 10.

## 13. Best fit for your riding

`kammcircle.advice.rank_pairs` ranks every front-and-rear pair in the bike's sizes from data alone:

- **Hard limits:** optionally, a load index and speed symbol at least those of the original fitment; a load rating at least your load at rest; optionally, on sale in Morocco when last checked.
- **Score:** for each tyre, 100 − 2 × |its published off-road share − your share of unpaved riding|, or 30 when the maker publishes no split; the pair's mean, +10 for a matched front and rear, −10 for mixing models the maker does not say may be mixed, +5 for each tyre seen on sale in Morocco, and the pair's price in dirhams ÷ 1000 subtracted as a tie-breaker.

The tab lists every tyre left out and why. On 9 November 2026, for instance, the only 140/80-17 rear seen at the two Moroccan retailers (Mitas Enduro Trail+, 1350 DH) was out of stock, so no complete pair passes the "on sale in Morocco" filter.

## 14. Pillion and luggage

A pillion and luggage are point masses on the sprung body, at the heights and positions you enter (examples until you measure; a negative position is behind the rear axle). They change the total mass, the centre of gravity, the pitch inertia, the static tyre loads checked against the load ratings, and the suspension: the springs stay those sized for the rider alone (section 11), so a pillion or luggage adds sag, as on the road. The brakes are a property of the motorcycle, sized once for the rider alone, so the same squeeze gives the same torque however loaded the bike is, and a loaded bike takes longer to stop. Luggage behind the rear axle moves the centre of gravity back and raises the deceleration at which the rear wheel lifts.

## 15. Acceleration (the simulation)

The Acceleration tab drives the rear wheel of the suspended model (section 11) with an engine and gearbox.

- **Gearing** is the manufacturer's: for the Himalayan 450, a primary ratio of 2.028, gears of 3.083, 2.059, 1.600, 1.286, 1.087 and 0.958, and a secondary ratio of 3.133 [re-450-tech-spec]; for the Scram 411, 2.312, five gears from 2.916 to 1.000, and 2.533 [re-scram-manual-in]. The engine turns `ω_wheel × primary × gear × secondary` faster than the rear wheel.
- **Torque curve.** The engine reaches its published peak torque at the published speed, and its power curve peaks, flat, at the published power and speed: above peak torque `T = T_pk − a·d² − b·d³` with `d = n − n_T`, where `a` and `b` follow from `T(n_P) = P / ω` and `dP/dn = 0` at `n_P`; below it, a parabola down to 65 % of the peak at idle. Only the two published points are data; the shape between and beyond them is an assumption, and so is the rev limit, 1000 rpm above peak power.
- **Clutch, shifts, throttle.** The clutch slips with the engine held at the launch speed until the motorcycle itself, not a spinning tyre, reaches that speed; drive is cut for 0.15 s at each upshift and at the rev limit. Optional throttle control, standing for a skilled rider or traction control, eases off when the rear tyre's slip passes 1.15 × its peak or the front wheel leaves the road. Without it, a full-throttle launch can spin the tyre past its peak, where the published tyre fit gives less force, and the spin feeds on itself.
- **Road load.** Rolling resistance (0.02 of each tyre's load, a stand-in) acts at the axles and aerodynamic drag `½·ρ·CdA·v²` on the sprung mass. With no measured drag area, `CdA` is back-solved so that the rear-wheel power in the best gear just balances drag and rolling resistance at the reported top speed (about 140 km/h for the Himalayan 450 [reallybigbikeride]).
- **Wheelie.** The front tyre can leave the road like the rear one in a stoppie; the run ends if the nose-up pitch energy about the rear axle could lift the centre of gravity over it.

**Checks** (`tests/test_acceleration.py`): the torque curve passes through the published figures and the power peaks where the maker says; the derived drag area reproduces the reported top speed within 2.5 km/h; shifts happen at the shift speed; throttle control cuts wheelspin; and enough torque lifts the front, which throttle control then holds down. With the example rider, the Himalayan 450 reaches 100 km/h in about 6.9 s from a standing start; one published figure, of unknown method, is 6.1 s.

**Not modelled:** chain pull on the swingarm (anti-squat), engine braking and engine inertia, clutch heat, and drag's own pitching moment.

## 16. Not modelled yet

- Tyre force from slip angle **and camber thrust** (for example a motorcycle "magic formula" tyre model) instead of a single μ in cornering.
- Anti-squat from the swingarm and chain, and engine braking (acceleration is in section 15).
- Countersteering dynamics, gyroscopic and steering-head torques, weave and wobble modes (where trail and rake matter dynamically).
- Temperature, pressure and wear effects on μ and on the contact patch (see `modifiers_not_quantified` in `data/surfaces.json`).
- Road camber and banking: subtract the bank angle from the lean relative to the road.
