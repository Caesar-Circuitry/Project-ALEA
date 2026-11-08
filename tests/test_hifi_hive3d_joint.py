"""hive3dJointTick bookkeeping replayed against sim3d/joint_tick.json (single calls).

The angle and angular velocity are INPUTS here (staged by the recorder), so no engine is needed.
The staged elements are rebuilt by the test-side `fill_cell` to drive the spill tagging.
"""

from typing import Any

import pytest

from alea.hifi.hive3d import Hive3dState, TrayBody, detent_decision, hive_dynamic_tick
from alea.hifi.hive3d_constants import BB3_HIVE_TIP_CREEP_W
from tests.hifi_replay import Dev
from tests.hifi_replay3d import fill_cell, load3d

CASES = load3d("joint_tick.json")["cases"]


def _hive(h: dict[str, Any]) -> Hive3dState:
    return Hive3dState(
        up=h["up"],
        contents=tuple(h["contents"]),
        tips=h["tips"],
        tipping=h["tipping"],
        released=h["released"],
        angle=h.get("angle"),
        ang_vel=h.get("angVel"),
    )


def _hive_json(h: Hive3dState) -> dict[str, Any]:
    d: dict[str, Any] = {
        "up": h.up,
        "contents": list(h.contents),
        "tips": h.tips,
        "tipping": h.tipping,
        "released": h.released,
    }
    if h.angle is not None:
        d["angle"] = h.angle
    if h.ang_vel is not None:
        d["angVel"] = h.ang_vel
    return d


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['alliance']}: {c['label'][:40]}")
def test_joint_tick_case(case: dict[str, Any]) -> None:
    alliance = case["alliance"]
    balls = fill_cell(alliance, case["staged"]["pollen"], case["staged"]["nectar"])
    # the 'angle undefined' case reads the Rapier body; it sat pinned on its own stop (the loads
    # traces record 0.5235987851049739 for a pinned blue tray at tick 0). The stop is +30 deg
    # for blue and -30 deg for red, so the sign follows the alliance; the cases that carry an
    # explicit hive angle ignore this value.
    body_stop_rad = 0.5235987851049739
    body_theta_rad = -body_stop_rad if alliance == "red" else body_stop_rad
    res = hive_dynamic_tick(alliance, _hive(case["hive_in"]), body_theta_rad, balls, None)
    dev = Dev()
    dev.cmp(_hive_json(res.hive), case["hive_out"], case["label"])
    assert dev.abs_dev == 0
    assert res.nectar_due_inc == case["nectar_due"]
    assert list(res.events) == case["events"]
    want_spill = case["spill"]
    if want_spill is None:
        assert res.spill is None
    else:
        assert res.spill is not None
        assert {str(k): v for k, v in res.spill.items()} == want_spill


def test_joint_tick_cases_cover_every_branch() -> None:
    labels = {c["label"] for c in CASES}
    assert len(CASES) == 19
    assert any("TIP" in e for c in CASES for e in c["events"])
    assert any("SPILLS" in e for c in CASES for e in c["events"])
    assert len(labels) == 10


def test_input_state_is_not_mutated() -> None:
    case = CASES[1]
    hive = _hive(case["hive_in"])
    balls = fill_cell("blue", 4, 0)
    seed: dict[int, Any] = {99: "red"}
    res = hive_dynamic_tick("blue", hive, 0.0, balls, seed)
    assert seed == {99: "red"}
    assert res.spill is not seed and res.spill is not None and res.spill[99] == "red"
    assert hive == _hive(case["hive_in"])


# --- detent decision: hand-derived from hive3d.ts:242-330 (no fixture isolates it) -----------


def _kind_of(i: int) -> Any:
    return "pollen"


def _hs(**kw: Any) -> Hive3dState:
    base: dict[str, Any] = {
        "up": "north",
        "contents": (),
        "tips": 0,
        "tipping": 0,
        "released": False,
    }
    base.update(kw)
    return Hive3dState(**base)


def test_detent_pins_at_stop_below_threshold() -> None:
    d = detent_decision(
        TrayBody(0.5235987851049739, (1e-11, 0, 0)), _hs(contents=(1, 2, 3)), _kind_of, True
    )
    assert d.held and not d.wake and d.zero_angvel
    # 9.5e-9 off the exact stop is inside the 1e-6 dead band: no rotation write, but the
    # non-zero angular velocity is still zeroed
    assert d.pin_angle_rad is None
    far = detent_decision(TrayBody(0.52, (0, 0, 0)), _hs(), _kind_of, True)
    assert far.pin_angle_rad == 0.5235987755982988 and not far.zero_angvel


def test_detent_no_write_when_already_exact() -> None:
    d = detent_decision(TrayBody(0.5235987755982988, (0, 0, 0)), _hs(), _kind_of, True)
    assert d.held and d.pin_angle_rad is None and not d.zero_angvel


def test_detent_lifts_and_wakes_only_on_first_tick() -> None:
    contents = tuple(range(8))  # eight pollen: the table tips
    d1 = detent_decision(TrayBody(0.5235987755982988), _hs(contents=contents), _kind_of, True)
    assert (d1.held, d1.wake, d1.pin_angle_rad) == (False, True, None)
    d2 = detent_decision(TrayBody(0.5235987755982988), _hs(contents=contents), _kind_of, False)
    assert (d2.held, d2.wake) == (False, False)


def test_detent_creep_is_a_floor_toward_the_far_stop() -> None:
    mid = TrayBody(0.1, (0.05, 0, 0))
    d = detent_decision(mid, _hs(tipping=2.0), _kind_of, False)  # up north, far = -1
    assert d.creep_angvel_x_rad_s == -BB3_HIVE_TIP_CREEP_W
    assert not d.held and d.pin_angle_rad is None
    fast = TrayBody(0.1, (-0.3, 0, 0))
    assert detent_decision(fast, _hs(tipping=2.0), _kind_of, False).creep_angvel_x_rad_s is None
    # not tipping: no creep; at either stop: no creep
    assert detent_decision(mid, _hs(), _kind_of, False).creep_angvel_x_rad_s is None
    stop = TrayBody(-0.5235987755982988, (0, 0, 0))
    assert detent_decision(stop, _hs(tipping=2.0), _kind_of, False).creep_angvel_x_rad_s is None
    south = detent_decision(
        TrayBody(-0.1, (0.0, 0, 0)), _hs(up="south", tipping=2.0), _kind_of, False
    )
    assert south.creep_angvel_x_rad_s == BB3_HIVE_TIP_CREEP_W
