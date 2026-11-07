"""Replay the dsim capture, load and sides traces through alea.hifi.hive."""

from alea.hifi.hive import (
    HiveLoad,
    HiveState,
    Vec3,
    hive_accepts,
    hive_approach_sign,
    hive_cell_pos,
    hive_load,
    hive_pivot,
    hive_surplus,
    hive_swing_rate,
    hive_taking_side,
    hive_will_tip,
    other_side,
)
from alea.hifi.hive_constants import BB_TIP_POLLEN
from tests.hifi_replay import Dev, hive_from_json, hive_to_json, load, vec2, vec3

# Float tolerance for these traces (inches, or a rate multiplier). The port repeats dsim's IEEE
# double operations in the same order, so the measured maximum deviation is exactly 0 for every
# float compared here (capture: only inputs and booleans; sides: cell positions; load: swing
# rates). Equality is therefore demanded.
TOL = 0.0


def test_capture_replay() -> None:
    doc = load("capture.json")
    phases = doc["inputs"]["phases"]
    assert len(doc["accepts"]) == 2352
    dev = Dev()
    for i, r in enumerate(doc["accepts"]):
        ph = phases[r["phase"]]
        hive = HiveState(r["up"], (), 0, ph["tipping"], ph["released"], ph.get("swingRate"))
        kw = {} if r["margin"] is None else {"margin": r["margin"]}
        got = hive_accepts(hive, r["alliance"], vec2(r["pos"]), r["z"], vec3(r["vel"]), **kw)
        dev.cmp(got, r["accepts"], f"row {i}")
    # positions and the CELL centres the rows are relative to
    for g in doc["geometry"]:
        dev.cmp({"x": hive_pivot(g["alliance"]).x, "y": hive_pivot(g["alliance"]).y}, g["pivot"])
        for side, pos in g["cell"].items():
            c = hive_cell_pos(g["alliance"], side)
            dev.cmp({"x": c.x, "y": c.y}, pos)
    assert dev.abs_dev <= TOL


def test_capture_has_both_outcomes() -> None:
    accepts = [r["accepts"] for r in load("capture.json")["accepts"]]
    assert any(accepts) and not all(accepts)


def test_sides_replay() -> None:
    doc = load("sides.json")
    dev = Dev()
    for side, other in doc["otherSide"].items():
        assert other_side(side) == other
    for alliance, p in doc["pivot"].items():
        dev.cmp({"x": hive_pivot(alliance).x, "y": hive_pivot(alliance).y}, p)
    for side, sign in doc["approach_sign"].items():
        assert hive_approach_sign(side) == sign
    for r in doc["rows"]:
        hive = hive_from_json(r["hive"])
        taking = hive_taking_side(hive)
        assert taking == r["taking_side"]
        assert hive_approach_sign(hive.up) == r["approach_sign_up"]
        assert hive_approach_sign(taking) == r["approach_sign_taking"]
        c = hive_cell_pos(r["alliance"], taking)
        dev.cmp({"x": c.x, "y": c.y}, r["taking_cell_pos"])
        assert other_side(hive.up) == r["other_side_of_up"]
    assert dev.abs_dev <= TOL


def test_load_cases() -> None:
    doc = load("load.json")
    for case in doc["hiveLoad_cases"]:
        kinds = case["kinds"]
        got = hive_load(case["ids"], lambda i, kinds=kinds: kinds[(i - 1) // 3])
        assert got == HiveLoad(**case["load"]), case["name"]


def test_load_via_contents() -> None:
    doc = load("load.json")
    dev = Dev()
    for r in doc["via_contents"]:
        kinds = r["kinds"]
        ld = hive_load(range(len(kinds)), lambda i, kinds=kinds: kinds[i])
        assert ld == HiveLoad(**r["load"])
        dev.cmp(hive_will_tip(ld), r["will_tip"])
        dev.cmp(hive_surplus(ld), r["surplus"])
        dev.cmp(hive_swing_rate(ld), r["swing_rate"])
    assert dev.abs_dev <= TOL


def test_load_grid() -> None:
    doc = load("load.json")
    assert len(doc["grid"]) == 150  # pollen 0..14 x nectar 0..9
    dev = Dev()
    for r in doc["grid"]:
        ld = HiveLoad(r["pollen"], r["nectar"])
        dev.cmp(hive_will_tip(ld), r["will_tip"])
        dev.cmp(hive_surplus(ld), r["surplus"])
        dev.cmp(hive_swing_rate(ld), r["swing_rate"])
    assert dev.abs_dev <= TOL


def test_tip_table() -> None:
    assert BB_TIP_POLLEN == (8, 7, 6, 3, 1, 0)
    for r in load("constants.json")["tip_table_lookup"]:
        n, pmin = r["nectar"], r["min_pollen_that_tips"]
        assert not hive_will_tip(HiveLoad(pmin - 1, n)) or pmin == 0
        assert hive_will_tip(HiveLoad(pmin, n))


def test_hive_state_is_immutable_and_json_roundtrip() -> None:
    h = HiveState("north", (1, 2), 0, 0.0, False)
    assert hive_from_json(hive_to_json(h)) == h
    try:
        h.tips = 1  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("HiveState must be frozen")
    assert Vec3(0, 0, 0) == Vec3(0.0, 0.0, 0.0)
