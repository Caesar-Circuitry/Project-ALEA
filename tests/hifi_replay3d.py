# Ported from dsim by genius0412, commit 62d2446e2ebdf416548fa1641847289bf47cdf36
# (staging rule copied from scripts/smoke-biobuzz/hive3d.ts).
# License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim).
"""Helpers for replaying the dsim 3D hive traces (tests/hifi_traces/sim3d) through alea.hifi.

Not a test module. `fill_cell` is the TEST-SIDE port of the recorder's staging rule
(`fillCell` in tests/hifi_traces/record_3d/record_hive3d.mts, itself copied from dsim's
scripts/smoke-biobuzz/hive3d.ts): it is input construction, not dsim physics. It uses the
port's own `rotate2`, `hive_tilt_angle` and cell boxes, as the recorder used dsim's.
"""

import json
from pathlib import Path
from typing import Any

from alea.hifi.hive import BbCellSide
from alea.hifi.hive3d import (
    Ball,
    Hive3dState,
    hive_cell_local_box,
    hive_pivot_x,
    hive_tilt_angle,
)
from alea.hifi.hive3d_constants import BB3_HIVE_PIVOT_Z, BB_NECTAR_R, BB_POLLEN_R
from alea.hifi.hive_constants import BB_HIVE_UP_STAGED
from alea.hifi.math3 import rotate2

TRACES3D = Path(__file__).parent / "hifi_traces" / "sim3d"


def load3d(name: str) -> dict[str, Any]:
    return json.loads((TRACES3D / name).read_text(encoding="utf-8"))


def fresh_hive(alliance: str) -> Hive3dState:
    """A fresh dsim world's hive record: up cell as staged, no angle yet, nothing tipping."""
    up: BbCellSide = "south" if BB_HIVE_UP_STAGED[alliance] == "south" else "north"
    return Hive3dState(up=up, contents=(), tips=0, tipping=0, released=False)


def fill_cell(
    alliance: str, pollen: int, nectar: int, packing: str = "guide", hive: Hive3dState | None = None
) -> list[Ball]:
    """Elements staged in the up cell: nectar first, then pollen, `per_row` across x at 4.6 in,
    rows outward from the cell's inner end. Ids are 1..n."""
    hv = hive if hive is not None else fresh_hive(alliance)
    theta = hive_tilt_angle(hv)
    side = 1 if hv.up == "north" else -1
    box = hive_cell_local_box(side, alliance)  # type: ignore[arg-type]
    inner_v = box.v_min if side > 0 else box.v_max
    per_row = 2 if packing == "line2" else 4
    balls: list[Ball] = []
    kinds = [True] * nectar + [False] * pollen
    for i, is_nectar in enumerate(kinds):
        r = BB_NECTAR_R if is_nectar else BB_POLLEN_R
        col = i % per_row
        row = i // per_row
        x = (col - (per_row - 1) / 2) * 4.6
        v = inner_v + side * (r + 0.2 + row * 3.4)
        w_local = box.w_min + r + 0.2
        y, z = rotate2(v, w_local, theta)
        balls.append(
            Ball(
                id=i + 1,
                x=hive_pivot_x(alliance) + x,  # type: ignore[arg-type]
                y=y,
                z=BB3_HIVE_PIVOT_Z + z - r,
                r=r,
                state_kind="ground",
                color=alliance if is_nectar else "yellow",
            )
        )
    return balls
