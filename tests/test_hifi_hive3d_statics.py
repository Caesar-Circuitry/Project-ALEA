"""3D hive constants and pure functions replayed against tests/hifi_traces/sim3d.

Both fixtures are the pure arithmetic of hive3d.ts; the expected values are exact doubles, so
the tests demand equality (measured max deviation 0 is printed with `-s` and recorded in
alea/hifi/PORTING.md).
"""

import dataclasses
import math
from typing import Any

import pytest

from alea.hifi import hive3d, hive3d_constants
from tests.hifi_replay import Dev
from tests.hifi_replay3d import fill_cell, fresh_hive, load3d


def _plain(v: Any) -> Any:
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {k: _plain(x) for k, x in dataclasses.asdict(v).items()}
    if isinstance(v, (tuple, list)):
        return [_plain(x) for x in v]
    return v


def test_config_constants_match_constants3d_json() -> None:
    doc = load3d("constants3d.json")
    for name, want in doc["config"].items():
        assert _plain(getattr(hive3d_constants, name)) == want, name
    assert hive3d_constants.GRAVITY == doc["GRAVITY"]
    assert hive3d_constants.SIM_DT == doc["SIM_DT"]
    assert hive3d_constants.BB_TIP_SWING_S == doc["BB_TIP_SWING_S"]
    assert doc["use_hive_dynamic_default"] is hive3d_constants.BB3_HIVE_DYNAMIC


@pytest.mark.parametrize("alliance", ["red", "blue"])
def test_body_helpers_match_constants3d_json(alliance: str) -> None:
    doc = load3d("constants3d.json")
    props = hive3d.hive_tray_mass_props(alliance)  # type: ignore[arg-type]
    want = doc["mass_props"][alliance]
    assert (props.mass, props.com_w, props.inertia) == (want["mass"], want["comW"], want["inertia"])
    assert hive3d.hive_tray_com_w(alliance) == doc["tray_com_w"][alliance]  # type: ignore[arg-type]
    assert hive3d.hive_pivot_x(alliance) == doc["pivot_x_in"][alliance]  # type: ignore[arg-type]
    assert hive3d.hive_tray_ref_theta(alliance) == doc["ref_theta"][alliance]  # type: ignore[arg-type]
    for side, sign in (("north", 1), ("south", -1)):
        box = hive3d.hive_cell_local_box(sign, alliance)  # type: ignore[arg-type]
        w = doc["cell_local_box"][alliance][side]
        got = {
            "xHalf": box.x_half,
            "vMin": box.v_min,
            "vMax": box.v_max,
            "wMin": box.w_min,
            "wMax": box.w_max,
            "refTheta": box.ref_theta,
        }
        assert got == w, (alliance, side)
    assert hive3d.element_mass(False) == doc["element_mass"]["pollen"]
    assert hive3d.element_mass(True) == doc["element_mass"]["nectar"]


def test_rest_and_stop_angles() -> None:
    assert hive3d.REST_RAD == 0.5235987755982988  # recorded as the 'near stop' angle
    assert hive3d.stop_angle(1) == hive3d.REST_RAD
    assert hive3d.stop_angle(-1) == -hive3d.REST_RAD
    assert hive3d.stop_angle(0) == hive3d.REST_RAD  # dsim: sign >= 0


def test_torque_rows() -> None:
    doc = load3d("statics3d.json")
    dev = Dev()
    cache: dict[tuple[str, int, int], list[hive3d.Ball]] = {}
    for alliance, p, n, theta, want in doc["torque_rows"]:
        balls = cache.setdefault((alliance, p, n), fill_cell(alliance, p, n))
        dev.cmp(hive3d.hive_contents_torque(balls, alliance, theta), want, f"{alliance} {p}P{n}N")
    print(f"torque_rows n={len(doc['torque_rows'])} max abs {dev.abs_dev!r} rel {dev.rel_dev!r}")
    assert dev.abs_dev == 0


def test_restoring_and_hold_rows() -> None:
    doc = load3d("statics3d.json")
    dev = Dev()
    for alliance, theta, restoring, hold in doc["restoring_rows"]:
        dev.cmp(hive3d.hive_restoring_torque(alliance, theta), restoring, "restoring")
        dev.cmp(hive3d.hive_hold_torque(alliance, theta), hold, "hold")
    print(f"restoring/hold n={len(doc['restoring_rows'])} max abs {dev.abs_dev!r}")
    assert dev.abs_dev == 0


def test_inside_cell_rows() -> None:
    doc = load3d("statics3d.json")
    n_true = 0
    for alliance, side, theta, min_depth, x, y, z, want in doc["inside_rows"]:
        got = hive3d.inside_cell(x, y, z, alliance, side, theta, min_depth)
        assert got is want, (alliance, side, theta, min_depth, x, y, z)
        n_true += got
    assert 0 < n_true < len(doc["inside_rows"])  # grid hits both outcomes


def test_fresh_hive_tilt_is_signed_rest() -> None:
    assert hive3d.hive_tilt_angle(fresh_hive("blue")) == hive3d.REST_RAD
    assert hive3d.hive_tilt_angle(fresh_hive("red")) == -hive3d.REST_RAD
    assert hive3d.hive_tilt_angle(None) == hive3d.REST_RAD


def test_tipping_from_angle_follows_js_nan_and_clamps() -> None:
    assert math.isnan(hive3d.tipping_from_angle(math.nan, 1))
    # JS Math.min/max clamp: a tilt beyond the stop gives p = 0 (full 4 s) or the 1e-4 floor
    assert hive3d.tipping_from_angle(2 * hive3d.REST_RAD, 1) == 4.0
    assert hive3d.tipping_from_angle(-hive3d.REST_RAD, 1) == 1e-4
