"""Seeded fake shot-study summary for the web app (no Warp, no GPU).

`build_summary(seed)` returns one dict per condition with the keys of
`alea.sim.results.summary_row`, so the page treats it like `load_summary` output.
"""

from __future__ import annotations

import numpy as np

from alea.sim.conditions import all_conditions
from alea.sim.results import summary_row

SHOTS_PER_CONDITION = 1000


def build_summary(seed: int = 0, shots: int = SHOTS_PER_CONDITION) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows = []
    for cond in all_conditions():
        # fake score rate: worse with aim/speed error, motion and a bouncier hive
        p = (
            0.92
            - 0.06 * cond["aim_deg"]
            - 0.03 * cond["speed_pct"]
            - 0.002 * cond["robot_ips"]
            - 0.05 * (cond["bounce"] > 0.5)
            + rng.normal(0, 0.01)
        )
        p = float(np.clip(p, 0.02, 0.98))
        fired = int(shots * rng.uniform(0.9, 1.0))
        hits = int(rng.binomial(fired, p))
        z = {
            "tries": np.array([shots]),
            "fired": np.array([fired]),
            "hits": np.array([hits]),
        }
        rows.append(summary_row(cond, z))
    return rows
