# Illustrations

The reference illustrations in `illustrations/` are the design masters for the app's views and for articles. They are self-contained (no network, no build step), follow the system's light or dark setting, and share one palette: teal `#1D9E75` for grip and good, coral `#D85A30` for force and warning, purple `#534AB7` for the line, the centre of gravity and the resultant, red `#E24B4A` for a limit, amber `#BA7517` for near the limit, and greys `#888780`, `#5F5E5A` and `#B4B2A9` for structure. They are drawn on a 380-unit-wide viewBox (phone width), with live text in the system sans-serif font.

| # | File | Type | Shows | Model and caveats |
|---|---|---|---|---|
| 01 | `01-lowering-geometry.html` | interactive | Himalayan 450 side view (facing left), with sliders for the rear and front drop (0–40 mm) and presets; live rake, trail, ground clearance and a handling note | Pitch about the axles; trail with R = 347.7 mm and d = 41 mm (derived). **Angle changes drawn ×5** so that they are visible; the numbers are real. Clearance loss = mean drop. |
| 02 | `02-corner-line-late-apex.svg` | static | Top-down right-hand bend in one lane: braking zone, late turn-in, late apex, exit; an early-apex line running wide | Schematic; "wide" means the outer part of your own lane. |
| 03 | `03-body-position-tarmac-vs-gravel.svg` | static | Rear view of the same corner: tarmac (seated, bike at 25°) against gravel (standing, outside peg, bike at 40°), with the same total-lean line through the combined centre of gravity | Angles illustrative; quantified by `bike_lean_for_rider_offset_deg()`. |
| 04 | `04-lean-force-balance.svg` | static | Rear view at 35°: mg, N, F and the resultant through the centre of gravity; tan θ = F/N = v²/(g·r), sliding when it exceeds μ | Point mass, steady state. |
| 05 | `05-lean-grip-friction-circle.html` | interactive | Speed, radius, μ and braking sliders with surface presets; lean needed against the grip limit; friction circle with the demand dot; maximum corner speed | Same formulas as `kammcircle.physics`; presets from `src/kammcircle/data/surfaces.json`. Underestimates real lean (tyre width). |
| 06 | `06-tyre-contact-at-lean.svg` | static | Rear-view tyre sections: road-biased at 35° (continuous contact), 60/40 knobby at 35° (one knob), worn squared-off rear at 15° (edge contact) | Schematic, not to scale. |
| 07 | `07-tyre-width-lean.svg` | static | Rear view of a leaned round-section tyre: contact point P below the section centre C, the centre of gravity G in the wheel plane, the force line P–G at φ0 and the wheel plane at φ | Schematic, tyre width exaggerated; geometry drawn exactly for φ0 = 30°, t = 40, h − t = 150 units. Quantified by `lean_angle_with_tyre_deg()`. |

Coordinate conventions: rear views lean to the right for a right-hand bend; side views have the bike facing left (travelling ←). The app's views (`src/kammcircle/ui/views.py`) follow the same conventions and colours.
