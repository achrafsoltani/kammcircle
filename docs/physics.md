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

**Not modelled with suspension yet:** spring preload, progressive (rising-rate) fork and linkage springs, separate compression and rebound damping, the swingarm's arc and the anti-squat and anti-rise geometry it brings, frame and fork flex, and tyre relaxation length. Aerodynamic drag and rolling resistance were added with the acceleration model (section 15), and engine braking in a chosen gear after it. Linear springs without preload or progression probably exaggerate the dive of a real fork, whose rising rate resists bottoming.

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
- **Engine drag and inertia (stand-ins).** No motoring torque or rotating inertia is published for either engine, so both are labelled assumptions in `sim-parameters.json`. With the throttle shut the engine drags with a torque that rises linearly with engine speed, from 10 % of its peak torque at idle to 30 % at the rev limit: 4 to 12 N m for the Himalayan 450, a motoring mean effective pressure of about 1.1 to 3.3 bar. A part-open throttle blends the two, `T = θ·T_full(n) − (1 − θ)·T_drag(n)`. The drivetrain's 90 % efficiency always works against the flow of power, so the wheel receives `0.9·T·ratio` under drive and `T·ratio / 0.9` when it drives the engine. With the clutch home and no shift under way, the engine's rotating parts, 0.012 kg m² at crankshaft speed, add `I·ratio²` to the rear wheel's inertia: 4.6 kg m² in the Himalayan's first gear, seven times the wheel's own.

**Checks** (`tests/test_acceleration.py`): the torque curve passes through the published figures and the power peaks where the maker says; the derived drag area reproduces the reported top speed within 2.5 km/h; shifts happen at the shift speed; throttle control cuts wheelspin; and enough torque lifts the front, which throttle control then holds down. With the example rider (80 kg) and gear changes at 8500 rpm, the model takes the Himalayan 450 from rest to 100 km/h in 7.3 s, or 6.9 s without the engine's rotating inertia; the closed-throttle drag plays no part at full throttle. Changing gear at 8000 rpm instead costs another 0.4 s. Two road tests measured 6.35 s [autocar-india-450-road-test] and 6.91 s [bikedekho-450-road-test], neither stating its method, and one aggregated figure is 6.1 s. Cycle World measured 37.44 hp at 7,700 rpm at the rear wheel on its chassis dynamometer [cycleworld-450-dyno], 5 % more than the 90 % efficiency stand-in gives; with that power, a 150 km/h top speed ("will pull all the way to 150kph" [autocar-india-450-road-test]) and a 70 kg rider, the model takes 6.6 s, inside the tested range. Fitted to the road tests alone, the drag area would be 0.48 m², implying a top speed near 159 km/h, against 0.58 to 0.72 m² from top speeds of 150 and 140 km/h: the 0–100 km/h time does carry information about drag on a 30 kW motorcycle, but no more than about the shift point, the rotating inertia and the rider's weight, so it cannot pin the drag down on its own.

**Engine braking (the Braking tab).** Riding in a gear rather than with the clutch in, the rider shuts the throttle as the brakes come on (`kammcircle.sim.engine_braking`). The engine's drag then slows the rear wheel through the gearing until the engine falls to 1.2 times its idle speed, when the rider pulls the clutch in before it stalls. A gear too low for the speed would over-rev the engine, so the rider holds the clutch in until the engine can take it. The Himalayan 450's own figures give a coasting deceleration of 0.156 g in first gear at 30 km/h, 0.137 g in second at 60 km/h and 0.053 g in sixth at 90 km/h. From 60 km/h with 40 % of the front brake alone, the stop takes 22.2 m with the clutch in, 21.1 m in fourth and 20.2 m in second, where the engine takes 16 % of the motorcycle's energy of motion. On loose ground (μ 0.3), first-gear engine braking alone at 30 km/h drives the rear tyre to 43 % slip, far past its peak, which is the slide riders meet on steep gravel descents; on tarmac the same coast stays within the tyre's peak. The tests check the drag curve, the losses' direction, the order of the gears, a coast against the quasi-static estimate within 10 %, the shorter stop from the same brake speed, the wait for a gear too low, and the slide on loose ground. The Himalayan 450's slip-and-assist clutch [re-450-tech-spec] would limit the back-torque of a hard downshift; that limit is not modelled.

**Not modelled:** chain pull on the swingarm (anti-squat), a slipper clutch's back-torque limit, clutch heat, and drag's own pitching moment.

## 16. Countersteering and self-stability (the simulation)

**Why the first push goes the wrong way.** Åström, Klein and Lennartsson (2005) [astrom-2005] reduce a two-wheeler to an inverted pendulum that the steering moves sideways (their eq. 1, with roll φ positive to the right and steer δ positive to the left):

$$J\,\ddot\varphi - m g h\,\varphi = \frac{D V}{b}\,\dot\delta + \frac{m V^2 h}{b}\,\delta, \qquad J \approx m h^2,\; D \approx m a h,$$

where $h$ is the height of the centre of mass, $a$ its distance ahead of the rear contact and $b$ the wheelbase. Upright, gravity gives no moment, so the only way to start a roll towards a right-hand corner is a steer angle to the left: the wheels run out from under the centre of mass, which falls towards the corner. Once the motorcycle leans, gravity takes over and the rider steers into the turn to hold the lean. That is countersteering, and it follows from the equation without any rule about it.

**The model the simulation uses.** The tab integrates the linearised Whipple model in the benchmark form of Meijaard, Papadopoulos, Ruina and Schwab (2007) [meijaard-2007], eq. 5.3:

$$\mathbf M\,\ddot{\mathbf q} + v\,\mathbf C_1\,\dot{\mathbf q} + \left(g\,\mathbf K_0 + v^2\,\mathbf K_2\right)\mathbf q = \mathbf f, \qquad \mathbf q = (\varphi, \delta),\; \mathbf f = (T_\varphi, T_\delta),$$

with lean, steer and the handlebar torque $T_\delta$ positive to the right (SAE axes: $x$ forward, $y$ to the right, $z$ down). It has a rear frame that carries the rider, a steered front frame, and two wheels whose spin makes the gyroscopic moments; the coefficients follow from 25 design parameters through the paper's Appendix A. The tests reproduce the paper's benchmark: its four matrices to 10⁻¹², its eigenvalues at every tabulated speed from 0 to 10 m/s to 10⁻¹¹, and its weave and capsize speeds, 4.2924 and 6.0243 m/s, to 10⁻⁹. The heading and the path come from Appendix B: $\dot\psi = (v\,\delta + c\,\dot\delta)\cos\lambda / w$ and $\dot x = v\cos\psi$, $\dot y = v\sin\psi$, and the front contact sits $c\,\delta\cos\lambda$ to the side of the frame's line, where $c$ is the trail, $\lambda$ the rake and $w$ the wheelbase.

**This motorcycle's parameters.** The rake (as the steering axis's tilt), the trail and the wheelbase come from the catalogue and the wheel radii from the fitted tyres. Royal Enfield publishes no masses or inertias of parts, so the rest are stand-ins measured on a Suzuki GSX-R1000 and its rider by Sharp, Evangelou and Limebeer (2004, Tables A.I–A.III) [sharp-2004]. They cover the wheels' masses and inertias and the steered front frame, 17.24 kg whose centre of mass lies on the steering axis 0.30 m above the front axle. They also give the main frame's inertias for the motorcycle and the upper body's for each rider. The rear frame is the motorcycle less its wheels and front frame, plus the rider, pillion and luggage of the Rider and bike tab, all rigid together. A test checks that the parts add up to the loaded motorcycle's mass and centre of mass, and that every inertia is physical.

**The rider.** The rider steers by handlebar torque alone, in the form Sharp et al. (2004, section 6) use, from the lean error and the lean rate. The torque the steady turn needs is fed forward in place of their integral term, since the linear model gives it exactly:

$$T_\text{command} = T_\text{steady} + k_p\,(\varphi - \varphi_\text{target}) + k_d\,\dot\varphi,$$

and the arms deliver it through a first-order lag of 0.1 s, the neuromuscular delay for steering torque that Åström et al. report from a study of motorcyclists. With the lag, the closed loop's characteristic polynomial is $(0.1\,s + 1)\det\mathbf A(s) + A_{\varphi\delta}(s)\,(k_p + k_d\,s)$, with $\mathbf A(s) = \mathbf M s^2 + v\mathbf C_1 s + g\mathbf K_0 + v^2\mathbf K_2$. That polynomial is affine in the two gains, so asking for a double root at $s = -\omega$, with $\omega = 3.89 / t_\text{roll-in}$, gives two linear equations; a critically damped response to a step reaches 90 % in $3.89/\omega$. When the other roots would be slower than half of $\omega$, the tab takes the nearest roll-in time the rider can manage and says so. The target lean is the linear model's own steady lean for the corner's radius. The rider stands the motorcycle up when the heading still to turn equals the heading the roll-out itself takes, which is computed once from the steady turn and is exact in a linear model.

**What it shows.** With the example rider (80 kg, alone) on the Himalayan 450 at 60 km/h on an 80 m radius, with a 1 s roll-in:

| Result | Value |
|---|---|
| Peak push on the inside grip | 10.3 N m |
| Bars turned away from the corner, at most | 0.43° |
| How far the wheels run wide first, rear / front | 9.5 / 10.3 cm |
| 90 % of the lean | after 1.16 s, 19 m |
| Lean in the turn | 20.5° (the linear model; 19.5° from tan φ = v²/gR) |
| Torque held in the steady turn | 0.1 N m |

Asking for a 0.6 s roll-in raises the push to 16.4 N m, turns the bars 0.74° away and runs the rear wheel 14 cm wide; at this speed the quickest roll-in the rider manages is 0.55 s (0.45 s at 80 km/h, 0.37 s at 100 km/h), which takes 18.6 N m. The corner ends within 0.1° of the heading asked for, and a left-hand corner is the exact mirror of a right-hand one.

**Self-stability.** Left alone, the motorcycle has four motions: weave, an oscillation of lean and steer; capsize, a slow fall into a tightening turn; castering, the front wheel swinging into line like a trolley's castor; and, at walking pace, two plain falls. The tab plots each motion's growth rate against speed. With the stand-ins above, the Himalayan 450 steadies itself between 26 and 57 km/h. Above that the capsize root is slightly positive: at 100 km/h it is 0.056 s⁻¹, so an uncorrected lean doubles in about 12 s, slowly enough that a rider corrects it without noticing. The weave there runs at 1.99 Hz with a damping ratio of 0.66.

**Limits.** The model is linear, so its lean and steer are exact only when small: for the same radius its lean is 1.1° above tan φ = v²/gR at 20° and 3.3° above at 30°, and the tab warns beyond 25°. The wheels are knife edges that do not slip, so the tyres' width, slip and aligning moment are missing, and Sharp et al. (2004) find that "predicting the steering torque accurately apparently depends on modelling the front tyre aligning moment well". The steady torque is therefore only indicative. The frame is rigid, although the same authors find that frame flexibility "significantly" compromises high-speed weave stability. The rider cannot shift their body, and at low speed hands alone are slow: on the Himalayan 450 with the example rider, the quickest roll-in this rider manages is 0.64 s at 45 km/h, 1.09 s at 40 km/h, 2.16 s at 30 km/h and 9.4 s at 20 km/h, and at 15 km/h it cannot balance the motorcycle at all. The tab therefore starts at 30 km/h.

## 17. Tyre temperature (the simulation)

**What the makers say.** Michelin writes that in winter "the rubber stiffens with the cold and becomes less effective in terms of grip", that reaching operating temperature takes "a certain number of miles, which varies according to the type of tire", that near freezing grip is reduced even in the dry, and that it does not recommend riding in winter conditions [michelin-cold-weather]. Bridgestone sets tyre warmers "around 50-60 degrees on road tyres" and warns that "you shouldn't bake road tyres to 80 degrees like you do slicks", while Pirelli puts its racing compounds' working range at 80–90 °C [bennetts-warmers]. Rubber friction peaks at a temperature set by the compound: for racing tyres at about 100 °C, with a glass transition near −10 °C, whereas passenger-car tread rubber has its glass transition near −40 °C [persson-2026-tread]. No maker publishes how a road tyre's grip varies with its temperature.

**The heat balance.** The Tyre temperature tab treats each tyre as two heat stores (`kammcircle.sim.tyre_thermal`): the tread, a band as wide as the tyre and 7 mm deep, and the carcass, the casing under the tread and the sidewalls. The rubber's density, specific heat and conductivity, 1110 kg/m³, 2080 J/kg K and 0.3 W/m K, are the means of three tread compounds measured by Mousavi and Sandu [mousavi-sandu-2020]; the layer thicknesses are stand-ins. Heat enters in two ways:

- **Rolling.** The rubber's hysteresis turns all the rolling-resistance work into heat inside the tyre, `P = C_rr·N·v`, half in the tread and half in the carcass (a stand-in). With the 0.02 rolling-resistance stand-in, the Himalayan 450's rear tyre takes 482 W at 60 km/h with the example rider.
- **Slip.** The friction work at the contact patch, `F·κ·v`, is released at the tread's surface. A riding style sets the mean share of the grip in use at each tyre, 5 %, 15 % or 50 %, and the slip it takes comes from the longitudinal tyre fit of section 10, used for cornering as well, which probably understates hard cornering. That gives 2 W, 22 W and about 400 W at the rear.

Heat leaves the tread's surface to the air and to the road, and the carcass through its sidewalls:

- **Air.** Forced convection with the Churchill–Bernstein correlation for a cylinder in cross-flow, `Nu = 0.3 + 0.62·Re^½·Pr^⅓ / [1 + (0.4/Pr)^⅔]^¼ · [1 + (Re/282,000)^⅝]^⅘` [incropera-cylinder], the tyre being a cylinder of its own diameter in the riding wind. Air properties are taken at 10 °C [etb-air-conductivity, etb-air-prandtl]. At 60 km/h this gives 37 W/m² K.
- **Road.** Each piece of tread touches the road for `t = L/v` once a revolution, where `L` is the contact length that the tyre's radial stiffness and load give. Two semi-infinite bodies in contact for that time exchange `2·e·ΔT·√(t/π)` per unit area, with `e` the effusivities `√(k·ρ·c)` of rubber and road in series. Only the real contact conducts, where the rubber touches the tops of the road's roughness, which is much smaller than the footprint [persson-2026-tread]; it is taken as 10 % of it, a stand-in, as are the asphalt's properties. Averaged over the band, this gives 46 W/m² K at 60 km/h.

The tread's surface is a massless node that balances conduction from the tread's bulk against these two sinks and the slip heat. It is the temperature that sets the grip, and in steady riding it sits well below the bulk, because the wind and the road cool it while the heat is made inside. The model conserves energy to rounding error, and a long ride settles exactly at the analytic steady state; the tests check both.

**The grip window (a stand-in).** The grip is full between 30 °C and 60 °C at the tread surface, which is consistent with Bridgestone's 50–60 °C warmers for road tyres. Below the window it eases down to 80 % at 0 °C and keeps falling below that. Above it, it loses 0.5 % per degree. The window's edges and the grip at 0 °C can be set in the tab, and every result below depends on them.

**What it shows.** These figures are for the Himalayan 450 with the example rider, from parked tyres at the air temperature:

| Weather and riding | Tread surfaces settle at, front / rear | Grip after 5 min, then settled | In the window |
|---|---|---|---|
| 20 °C air, 25 °C road, gentle at 60 km/h | 34 / 32 °C | full | after 6.7 / 10.7 min |
| 10 °C air, 8 °C road, brisk at 60 km/h | 22 / 19 °C | 96 / 95 %, then 99 / 98 % | never |
| 5 °C air, 3 °C road, gentle at 60 km/h | 16 / 14 °C | 92 / 91 %, then 96 / 94 % | never |
| 5 °C air, 3 °C road, hard at 90 km/h | 31 / 25 °C | full / 98 % | front after 13.7 min |
| −2 °C air, −4 °C road, brisk at 60 km/h | 10 / 7 °C | 86 / 84 %, then 91 / 89 % | never |

The tread's bulk covers two-thirds of its rise in about 6 minutes of gentle riding and 4.5 minutes of hard riding, which matches the makers' "several kilometres". Tyre warmers at 70 °C, followed by gentle riding at 3 °C, give full grip at the start. The grip then drains to 95 / 93 % within half an hour, as Michelin warns. The main finding for cold places does not depend on the exact window: gentle riding cannot bring a road tyre into its window in cold weather, because the wind and the cold road take the heat away as fast as rolling makes it. Only brisk riding over many minutes narrows the gap.

**Limits.** The grip window, the layer thicknesses, the share of real contact and the asphalt's properties are stand-ins, and no measured temperatures of these tyres exist to check the model against. Rain, a wet road, frost and ice, tyre pressure, wear and the camber of the tyre at lean are not modelled, and the inflation air inside the tyre is ignored.

## 18. Not modelled yet

- Tyre force from slip angle **and camber thrust** (for example a motorcycle "magic formula" tyre model) instead of a single μ in cornering.
- Anti-squat from the swingarm and chain (acceleration and engine braking are in section 15).
- Tyre slip, width and aligning moment in the lean-and-steer model (section 16 uses knife-edge wheels), frame and fork flexibility, wobble, and the rider's upper-body lean.
- Pressure and wear effects on μ and on the contact patch, and tyre temperature in the braking, acceleration and cornering runs (section 17 models it on its own; see `modifiers_not_quantified` in `data/surfaces.json`).
- Road camber and banking: subtract the bank angle from the lean relative to the road.
