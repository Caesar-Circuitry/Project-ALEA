"""Replay the dsim spill, deflect and trig traces through alea.hifi.hive and hive_math."""

import math

from alea.hifi.hive import hive_deflect, spill_poses
from alea.hifi.hive_math import dcos, dsin
from tests.hifi_replay import Dev, cycled, hive_from_json, load, mulberry32, vec3, vec_json

# Float tolerances (inches, in/s, or unitless sin/cos). dsin/dcos are ported with the same IEEE
# operations in the same order, and the spill and deflect arithmetic follows the TypeScript
# expressions, so the measured maximum deviation is 0 in all three files; equality is demanded.
TOL_SPILL = 0.0
TOL_DEFLECT = 0.0
TOL_TRIG = 0.0

# math.sin / math.cos would NOT be exact: dsim's polynomial differs from them by about 6e-12
# (dsin(0) is 0 but dcos(0) = 0.99999999999398). This bound documents why dsin/dcos were ported.
MATH_SIN_COS_DEVIATION_BOUND = 1e-10


def test_spill_replay() -> None:
    doc = load("spill.json")
    rngs = doc["inputs"]["rng"]
    dev = Dev()
    kinds = set()
    for i, c in enumerate(doc["cases"]):
        if c["rng"] == "mulberry32":
            rng = mulberry32(rngs["mulberry32"]["seed"])
        else:
            rng = cycled(rngs["cycle"]["values"])
        draws = 0

        def counted(rng=rng) -> float:
            nonlocal draws
            draws += 1
            return rng()

        poses = spill_poses(hive_from_json(c["hive"]), c["alliance"], c["count"], counted)
        assert draws == c["draws"] == 6 * c["count"], f"case {i}"
        got = [{"pos": vec_json(p.pos), "vel": vec_json(p.vel)} for p in poses]
        dev.cmp(got, c["poses"], f"case {i} {c['label']}")
        kinds.add(c["rng"])
    assert kinds == {"mulberry32", "cycle"}
    assert dev.n_floats > 500
    assert dev.abs_dev <= TOL_SPILL


def test_mulberry32_matches_fixture_stream() -> None:
    """The test's own mulberry32 reproduces the first recorded x draw of a 1-pose case."""
    doc = load("spill.json")
    c = next(c for c in doc["cases"] if c["rng"] == "mulberry32" and c["count"] == 1)
    r = mulberry32(doc["inputs"]["rng"]["mulberry32"]["seed"])
    draws = [r() for _ in range(6)]
    assert all(0 <= d < 1 for d in draws)
    from alea.hifi.hive import hive_cell_pos
    from alea.hifi.hive_constants import BB_CELL_OPEN

    h = hive_from_json(c["hive"])
    emptying = h.up if h.tipping > 0 else ("south" if h.up == "north" else "north")
    cx = hive_cell_pos(c["alliance"], emptying).x
    assert cx + (draws[0] * 2 - 1) * (BB_CELL_OPEN.w / 2) == c["poses"][0]["pos"]["x"]


def test_deflect_replay() -> None:
    doc = load("deflect.json")
    dev = Dev()
    n_none = 0
    for r in doc["rows"]:
        out = hive_deflect(
            hive_from_json(r["hive"]),
            r["alliance"],
            vec3(r["prev"]),
            vec3(r["pos"]),
            vec3(r["vel"]),
        )
        got = None if out is None else {"pos": vec_json(out.pos), "vel": vec_json(out.vel)}
        n_none += got is None
        dev.cmp(got, r["result"], r["name"])
    assert 0 < n_none < len(doc["rows"])
    assert dev.abs_dev <= TOL_DEFLECT


def test_trig_replay() -> None:
    doc = load("trig.json")
    dev = Dev()
    worst_math = 0.0
    n = 0
    for key in ("degrees_0_360", "degrees_neg"):
        for r in doc[key]:
            dev.cmp(
                {"sin": dsin(r["a"]), "cos": dcos(r["a"])}, {"sin": r["sin"], "cos": r["cos"]}, key
            )
            worst_math = max(
                worst_math, abs(math.sin(r["a"]) - r["sin"]), abs(math.cos(r["a"]) - r["cos"])
            )
            n += 1
    for r in doc["spill_stream_angles"]:
        for part in ("fan", "kick"):
            e = r[part]
            dev.cmp(
                {"sin": dsin(e["a"]), "cos": dcos(e["a"])}, {"sin": e["sin"], "cos": e["cos"]}, part
            )
            n += 1
    for e in doc["fan_extremes"]:
        dev.cmp(
            {"sin": dsin(e["a"]), "cos": dcos(e["a"])}, {"sin": e["sin"], "cos": e["cos"]}, "fan"
        )
        n += 1
    assert n > 400
    assert dev.abs_dev <= TOL_TRIG
    assert 0 < worst_math < MATH_SIN_COS_DEVIATION_BOUND  # math.sin/cos is close but not equal


def test_trig_non_finite_is_nan() -> None:
    """dsim: Math.round(+-Infinity) = +-Infinity, so inf - inf is NaN. No exception."""
    for v in (math.nan, math.inf, -math.inf):
        assert math.isnan(dsin(v))
        assert math.isnan(dcos(v))
