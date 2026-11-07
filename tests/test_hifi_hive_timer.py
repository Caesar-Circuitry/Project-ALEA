"""Replay the dsim timer traces (hive_timer_step and hive_step) through alea.hifi.hive.

Caveats from tests/hifi_traces/README.md: hive_timer_step never clears `contents`, and the
recorder keeps the tray full, so a timer run starts a second swing after the settle (tips can
reach 2 where hive_step rows show 1). Each series is replayed on its own against its own
recorded rows; the two are never compared with each other.
"""

import math
from dataclasses import replace
from typing import Any

import pytest

from alea.hifi.hive import (
    BbElementKind,
    HiveState,
    Vec2,
    Vec3,
    hive_accepts,
    hive_approach_sign,
    hive_cell_pos,
    hive_step,
    hive_taking_side,
    hive_timer_step,
)
from alea.hifi.hive_constants import BB_HIVE_OPEN_Z
from tests.hifi_replay import Dev, hive_to_json, load

# Float tolerance (seconds of `tipping`, rate multipliers). The timer is repeated subtraction
# `tipping - dt * rate` in IEEE doubles, same order as dsim; measured max deviation over all
# rows of all three files is 0, so equality is demanded.
TOL = 0.0

FILES = ["timer_dt60_threshold.json", "timer_dt60_surplus.json", "timer_coarse.json"]
Z_MID = (BB_HIVE_OPEN_Z[0] + BB_HIVE_OPEN_Z[1]) / 2  # the recorder's launch height


def _replay(run: dict[str, Any], fn: str, dev: Dev) -> int:
    """Replay one run with 'timer' or 'step'; returns the number of rows compared."""
    kinds: list[BbElementKind] = list(run["initial_kinds"])
    hive = HiveState(run["up"], tuple(range(len(kinds))), 0, 0.0, False)
    dt = run["dt_s"]
    rows = run["timer_steps" if fn == "timer" else "step_steps"]
    applied = run["launches_timer" if fn == "timer" else "launches_step"]
    launches = run["launches_offered"]
    n_launch = 0
    for i, row in enumerate(rows):
        for launch in launches:
            if math.floor(launch["t_s"] / dt + 0.5) != i:  # JS Math.round, not banker's
                continue
            side = hive_taking_side(hive)
            c: Vec2 = hive_cell_pos("red", side)
            vel = Vec3(0, hive_approach_sign(side), -10)
            ok = hive_accepts(hive, "red", c, Z_MID, vel)
            rec = applied[n_launch]
            n_launch += 1
            assert (rec["step"], rec["kind"], rec["taking_side"], rec["accepted"]) == (
                i,
                launch["kind"],
                side,
                ok,
            )
            if ok:
                kinds.append(launch["kind"])
                hive = replace(hive, contents=(*hive.contents, len(kinds) - 1))
        if fn == "timer":
            t = hive_timer_step(hive, dt, kinds.__getitem__)
            hive = t.hive
            got: dict[str, Any] = {
                "i": i,
                "hive": hive_to_json(hive, contents=False),
                "tipped": t.tipped,
                "releasing": t.releasing,
            }
        else:
            s = hive_step(hive, dt, kinds.__getitem__)
            hive = s.hive
            got = {
                "i": i,
                "hive": hive_to_json(hive),
                "tipped": s.tipped,
                "spilled": list(s.spilled),
            }
        dev.cmp(got, row, f"{run['name']} dt={dt} {fn} row {i}")
    assert n_launch == len(applied)
    return len(rows)


@pytest.mark.parametrize("fn", ["timer", "step"])
@pytest.mark.parametrize("name", FILES)
def test_timer_replay(name: str, fn: str) -> None:
    doc = load(name)
    dev = Dev()
    rows = sum(_replay(run, fn, dev) for run in doc["runs"])
    assert rows > 100
    assert dev.n_floats > 0
    assert dev.abs_dev <= TOL


def test_coarse_covers_fallback_spill() -> None:
    """dt 3 and 5 s exceed half a swing, so hive_step must spill at the settle."""
    runs = load("timer_coarse.json")["runs"]
    long_dt = [r for r in runs if r["dt_s"] >= 3]
    assert long_dt
    assert any(any(row["spilled"] for row in r["step_steps"]) for r in long_dt)
