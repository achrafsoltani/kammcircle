"""Tyres in the simulation, the best-fit ranking, and pillion and luggage loads."""

import pytest

from kammcircle import advice, catalogue
from kammcircle.rider import RiderSetup
from kammcircle.sim import SuspendedBrakingSim, braking_parameters, run_braking, suspension_parameters
from kammcircle.sim.parameters import static_wheel_loads

near = pytest.approx


@pytest.fixture(scope="module")
def himalayan():
    return catalogue.bike("re-himalayan-450-2026")


def choice(front_id, rear_id):
    return catalogue.TyreChoice(catalogue.tyre_listing(front_id), catalogue.tyre_listing(rear_id))


# ─── tyres in the simulation ─────────────────────────────────────────────────


def test_the_chosen_tyres_set_the_wheel_radii(himalayan):
    mitas = choice("mitas-terra-force-r-90-90-21-54h", "mitas-terra-force-r-140-80r17-69v")
    p, notes = braking_parameters(himalayan, RiderSetup(), 1.0, mitas)
    assert p.front_radius == near(0.3475)  # half the maker's 695 mm design diameter
    assert p.rear_radius == near(0.328)
    assert "Terra Force-R" in {n.name: n.value for n in notes}["Tyres"]
    stock, _ = braking_parameters(himalayan, RiderSetup(), 1.0)
    assert stock.front_radius == near(himalayan.front_wheel_radius_mm / 1000)


def test_listing_ratings_and_crown_radius():
    oe = catalogue.original_tyres(catalogue.bike("re-himalayan-450-2026"))
    assert oe.front.load_kg == 212 and oe.front.speed_kmh == 210
    assert oe.rear.load_kg == 325
    assert oe.rear.crown_radius_mm == near(70.0)
    timsun = catalogue.tyre_listing("timsun-ts-712f-90-90-21-54p")
    assert timsun.speed_kmh == 150 and timsun.available_in_morocco and timsun.best_price_mad == 840


# ─── best fit ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("unpaved, expected", [(10, "mitas-terra-force-r"), (40, "mitas-enduro-trail-plus"),
                                               (50, "mitas-e07")])
def test_best_fit_follows_the_share_of_unpaved_riding(himalayan, unpaved, expected):
    ranked = advice.rank_pairs(himalayan, unpaved)
    top = ranked.pairs[0]
    assert top.front.product.id == top.rear.product.id == expected


def test_keeping_the_original_ratings_excludes_slower_tyres(himalayan):
    ranked = advice.rank_pairs(himalayan, 80)
    ids = {p.front.product.id for p in ranked.pairs}
    assert "mitas-enduro-trail-xt-plus" not in ids  # 54T front is below the original H
    assert any("Timsun" in e and "below the original" in e for e in ranked.excluded)
    relaxed = advice.rank_pairs(himalayan, 80, keep_ratings=False)
    assert relaxed.pairs[0].front.product.id == "mitas-enduro-trail-xt-plus"


def test_in_stock_only_leaves_no_complete_pair_and_says_why(himalayan):
    ranked = advice.rank_pairs(himalayan, 30, in_stock_only=True, keep_ratings=False)
    assert ranked.pairs == ()
    assert any("140/80" in e and "not seen in stock" in e for e in ranked.excluded)


def test_an_overload_excludes_a_tyre(himalayan):
    ranked = advice.rank_pairs(himalayan, 20, static_loads_n=(200 * 9.81, 340 * 9.81))
    assert ranked.pairs == ()
    assert any("exceeds its 325 kg rating" in e for e in ranked.excluded)


# ─── pillion and luggage ─────────────────────────────────────────────────────


def test_a_pillion_and_luggage_load_the_rear_and_move_the_cog(himalayan):
    solo = RiderSetup()
    loaded = RiderSetup(pillion_mass_kg=65, luggage_mass_kg=25)
    f0, r0 = static_wheel_loads(himalayan, solo)
    f1, r1 = static_wheel_loads(himalayan, loaded)
    assert (f1 + r1) - (f0 + r0) == near(90 * 9.81)
    assert r1 - r0 > f1 - f0  # most of it on the rear
    p0, _ = braking_parameters(himalayan, solo, 1.0)
    p1, _ = braking_parameters(himalayan, loaded, 1.0)
    assert p1.mass == near(p0.mass + 90)
    assert p1.cog_ahead_of_rear < p0.cog_ahead_of_rear
    assert p1.lift_deceleration_g > p0.lift_deceleration_g  # a loaded tail resists a stoppie
    d0 = run_braking(p0, 80, 0.5, 0.2).summary().stopping_distance
    d1 = run_braking(p1, 80, 0.5, 0.2).summary().stopping_distance
    assert d1 > d0  # the same lever squeeze has more mass to stop


def test_luggage_adds_sag_and_the_loaded_bike_is_still_in_equilibrium(himalayan):
    loaded = RiderSetup(pillion_mass_kg=65, luggage_mass_kg=25)
    p, _ = braking_parameters(himalayan, loaded, 1.0)
    s, notes = suspension_parameters(himalayan, loaded)
    sim = SuspendedBrakingSim(p, s, 60)
    assert sim.static_rear_compression > s.rear_sag + 0.02
    sim.run_for(0.5, 0.0, 0.0)
    assert sim.rear_compression == near(sim.static_rear_compression, abs=1e-6)
    assert sim.nf + sim.nr == near(p.weight, rel=1e-6)
    assert any("Pillion" == n.name for n in braking_parameters(himalayan, loaded, 1.0)[1])
