"""Per-tick bookkeeping replay against sim3d/loads_*.json, fed with RECORDED Rapier readback.

What this is and is not. The traces were produced by dsim's Rapier engine. The port has no
engine, so the swing itself (angle, angular velocity per tick) is NOT reproduced: it is read from
the recording (`hive_angle_rad`, `hive_ang_vel_rad_s`, the 4-decimal values dsim's world JSON
holds, which are what `hiveDynamicTick` reads) and fed in tick by tick. What is tested is that
the ported state machine (tipping countdown, release, the SPILLS and TIP events, nectar due, the
up-side flip) turns that recorded motion into the recorded bookkeeping, and that the detent
DECISION agrees with the recorded `tray_held`. Spill tags are not re-derived here (element
positions are not recorded per tick); the recorded `spill_n` stands in for `bb.spill`, so the
SPILLS count is checked against it. `contents` is rebuilt from `contents_n`.
"""

from typing import Any

import pytest

from alea.hifi.hive3d import STOP_RAD, Hive3dState, TrayBody, detent_decision, hive_dynamic_tick
from alea.hifi.hive_constants import BB_HIVE_UP_STAGED
from tests.hifi_replay import Dev
from tests.hifi_replay3d import load3d

FILES = ["loads_no_tip_blue.json", "loads_tip_blue.json", "loads_red.json"]
ROWS = [
    pytest.param(f, i, id=f"{f[:-5]}[{i}] {r['pollen']}P{r['nectar']}N")
    for f in FILES
    for i, r in enumerate(load3d(f)["rows"])
]


def _replay(row: dict[str, Any]) -> tuple[Dev, list[tuple[int, str]], dict[str, list[Any]]]:
    a = row["alliance"]
    c = row["columns"]
    hive = Hive3dState(up=BB_HIVE_UP_STAGED[a], contents=(), tips=0, tipping=0, released=False)  # type: ignore[arg-type]
    nectar_due = 0
    events: list[tuple[int, str]] = []
    dev = Dev()
    got: dict[str, list[Any]] = {
        k: [] for k in ("tipping_s", "released", "tips", "up", "nectar_due")
    }
    for t in range(row["ticks"]):
        hive = Hive3dState(
            up=hive.up,
            contents=tuple(range(1, c["contents_n"][t] + 1)),
            tips=hive.tips,
            tipping=hive.tipping,
            released=hive.released,
            angle=c["hive_angle_rad"][t],
            ang_vel=c["hive_ang_vel_rad_s"][t],
        )
        spill = {k: a for k in range(c["spill_n"][t])}
        res = hive_dynamic_tick(a, hive, c["tray_theta_rad"][t], [], spill)  # type: ignore[arg-type]
        hive = res.hive
        nectar_due += res.nectar_due_inc
        events += [(t, e) for e in res.events]
        got["tipping_s"].append(hive.tipping)
        got["released"].append(int(hive.released))
        got["tips"].append(hive.tips)
        got["up"].append(hive.up)
        got["nectar_due"].append(nectar_due)
    for k, v in got.items():
        dev.cmp(v, c[k], k)
    return dev, events, got


@pytest.mark.parametrize(("name", "idx"), ROWS)
def test_bookkeeping_follows_recorded_motion(name: str, idx: int) -> None:
    row = load3d(name)["rows"][idx]
    dev, events, _ = _replay(row)
    assert events == [(t, e) for t, e in row["events"]]
    s = row["summary"]
    c = row["columns"]
    assert next((t for t, x in enumerate(c["tipping_s"]) if x > 0), None) == s["first_tipping_tick"]
    assert next((t for t, x in enumerate(c["released"]) if x), None) == s["first_released_tick"]
    print(f"{name}[{idx}] ticks={row['ticks']} max abs dev {dev.abs_dev!r}")
    assert dev.abs_dev == 0


def test_every_trace_class_is_present() -> None:
    all_events = [e for f in FILES for r in load3d(f)["rows"] for _, e in r["events"]]
    assert any("SPILLS" in e for e in all_events)
    assert any("TIP" in e and "SPILLS" not in e for e in all_events)
    assert len(ROWS) == 4 + 5 + 2


@pytest.mark.parametrize(("name", "idx"), ROWS)
def test_detent_decision_matches_recorded_hold(name: str, idx: int) -> None:
    """`detent_decision` on the recorded pre-step body and hive reproduces `tray_held`.

    Skipped ticks: tick 0 (the fresh world's sentinel contents) and ticks at a stop with a
    partial `contents_n`, whose kinds are not recorded.
    """
    row = load3d(name)["rows"][idx]
    a = row["alliance"]
    c = row["columns"]
    total = row["pollen"] + row["nectar"]
    nectar = row["nectar"]

    def kind_of(i: int) -> Any:
        return a if i <= nectar else "pollen"

    checked = skipped = 0
    for t in range(1, row["ticks"]):
        theta = c["tray_theta_rad"][t - 1]
        n = c["contents_n"][t - 1]
        if abs(theta) >= STOP_RAD and 0 < n < total:
            skipped += 1
            continue
        hive = Hive3dState(
            up=c["up"][t - 1],
            contents=tuple(range(1, n + 1)),
            tips=c["tips"][t - 1],
            tipping=c["tipping_s"][t - 1],
            released=bool(c["released"][t - 1]),
        )
        body = TrayBody(theta, (c["tray_omega_rad_s"][t - 1], 0.0, 0.0))
        d = detent_decision(body, hive, kind_of, bool(c["tray_held"][t - 1]))
        assert d.held == bool(c["tray_held"][t]), (t, theta, n)
        checked += 1
    print(f"{name}[{idx}] detent checked {checked} skipped {skipped}")
    assert checked > row["ticks"] // 2
