"""Provenance rules for the packaged data: every status is known, every source resolves, derived values recompute."""

import math
import subprocess
import sys
from pathlib import Path

import pytest

from kammcircle import catalogue
from kammcircle import physics as P

ROOT = Path(__file__).resolve().parents[1]


def _walk(node, path=""):
    """Yield (path, dict) for every dict in a JSON tree, skipping documentation keys such as ``_schema``."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            if not key.startswith("_"):
                yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, f"{path}[{i}]")


DATA_FILES = ["bikes.json", "surfaces.json", "tyres.json", "lowering-options.json", "sim-parameters.json"]


@pytest.mark.parametrize("name", DATA_FILES)
def test_every_status_is_known(name):
    for path, node in _walk(catalogue.load_json(name)):
        if "status" in node:
            assert node["status"] in catalogue.STATUSES, f"{name}{path}: unknown status {node['status']!r}"


@pytest.mark.parametrize("name", DATA_FILES)
def test_every_source_id_resolves(name):
    known = catalogue.sources()
    for path, node in _walk(catalogue.load_json(name)):
        for source_id in node.get("source", []):
            assert source_id in known, f"{name}{path}: source {source_id!r} missing from sources.json"


@pytest.mark.parametrize("name", DATA_FILES)
def test_unpublished_values_stay_null(name):
    for path, node in _walk(catalogue.load_json(name)):
        if node.get("status") == "unpublished":
            assert node.get("value") is None, f"{name}{path}: an unpublished figure must stay null"


def test_every_source_is_cited_or_further_reading():
    cited = set()
    for name in DATA_FILES:
        for _, node in _walk(catalogue.load_json(name)):
            cited.update(node.get("source", []))
    physics_doc = (ROOT / "docs" / "physics.md").read_text(encoding="utf-8")
    for source in catalogue.sources().values():
        assert (
            source.id in cited or source.id in physics_doc or source.group == "Further reading"
        ), f"source {source.id!r} is cited nowhere"


def test_derived_tyre_radii_recompute():
    for bike in catalogue.bikes():
        derived = bike.raw["derived"]
        assert bike.front_wheel_radius_mm == pytest.approx(derived["front_tyre_radius_mm"]["value"], abs=0.05)
        assert bike.rear_wheel_radius_mm == pytest.approx(derived["rear_tyre_radius_mm"]["value"], abs=0.05)
        assert bike.fork_offset_mm == pytest.approx(derived["fork_offset_mm"]["value"], abs=0.05)


def test_head_angle_and_rake_agree():
    for bike in catalogue.bikes():
        chassis = bike.raw["chassis"]
        if "head_angle_deg" in chassis:
            assert chassis["head_angle_deg"] + chassis["rake_deg"] == pytest.approx(90)


def test_surface_max_lean_matches_mu():
    for raw in catalogue.load_json("surfaces.json")["surfaces"]:
        assert raw["max_lean_deg"] == pytest.approx(P.max_lean_deg(raw["ui_default"]), abs=0.05)


def test_sources_are_https_and_unique():
    raw = catalogue.load_json("sources.json")["sources"]
    ids = [s["id"] for s in raw]
    assert len(ids) == len(set(ids))
    assert all(s["url"].startswith("https://") for s in raw)


def test_sources_markdown_is_up_to_date():
    generated = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "gen_sources_md.py"), "--stdout"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert (ROOT / "docs" / "sources.md").read_text(encoding="utf-8") == generated, (
        "docs/sources.md is stale: run tools/gen_sources_md.py"
    )


def test_illustration_manifest_names_real_functions_and_files():
    import json

    manifest = json.loads((ROOT / "docs" / "illustrations" / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["illustrations"]:
        assert (ROOT / "docs" / "illustrations" / item["file"]).is_file(), item["file"]
        for name in item.get("physics", []):
            assert callable(getattr(P, name, None)), f"{item['file']}: kammcircle.physics has no {name}()"
        for path in item.get("data", []):
            assert (ROOT / path).is_file(), path


def test_catalogue_loads():
    assert {b.id for b in catalogue.bikes()} == {"re-himalayan-450-2026", "re-scram-411"}
    assert all(0 < s.mu <= 1.3 for s in catalogue.surfaces())
    assert not math.isnan(catalogue.bike("re-scram-411").fork_offset_mm)


def test_tyre_formula_matches_the_mitas_catalogue_design_diameters():
    """Our nominal diameter must agree with the manufacturer's E.T.R.T.O. design diameter for every fitment listed."""
    for tyre in catalogue.load_json("tyres.json")["tyres"]:
        for position in ("front", "rear"):
            fit = tyre.get("himalayan_450_fitment", {}).get(position)
            if not fit:
                continue
            size = P.parse_tyre_size(fit["size"])
            width, diameter = fit["design"]
            assert P.tyre_diameter_mm(size.width_mm, size.aspect_pct, size.rim_in) == pytest.approx(diameter, abs=1.0)
            assert abs(width - size.width_mm) <= 2  # design section width within 2 mm of the nominal width


def test_himalayan_fitments_name_the_himalayan_sizes():
    bike = catalogue.bike("re-himalayan-450-2026")
    front = P.parse_tyre_size(bike.front_tyre)
    rear = P.parse_tyre_size(bike.rear_tyre)
    for tyre in catalogue.load_json("tyres.json")["tyres"]:
        fit = tyre.get("himalayan_450_fitment")
        if fit:
            assert P.parse_tyre_size(fit["front"]["size"]) == front
            if fit["rear"]:
                assert P.parse_tyre_size(fit["rear"]["size"]) == rear
