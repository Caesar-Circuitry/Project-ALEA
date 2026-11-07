"""Read a finished study as plain data (no pandas, no GPU needed).

rows = load_summary("results/study")      # one dict per condition
factor_effects(rows)                      # score rate per factor value, other factors averaged
worst_best(rows, n=3)                     # (worst n rows, best n rows) by score rate
"""

import csv
import math
from pathlib import Path

import numpy as np

# (label, key) of each factor the study varies; keys match alea.sim.conditions.
FACTORS = [
    ("aim error (deg)", "aim_deg"),
    ("flywheel speed error (%)", "speed_pct"),
    ("robot moving (in/s)", "robot_ips"),
    ("ball size (in)", "ball_in"),
    ("ball bounce", "bounce"),
]
_COND_KEYS = [k for _, k in FACTORS] + ["id"]
SCORE_KEY = "pct_scored_of_fired"  # % of fired shots that scored
_INT_KEYS = {"id", "shots", "fired", "scored"}


def summary_row(cond: dict, z) -> dict:
    """One summary.csv row from a condition dict and its loaded cond_XXX.npz."""
    tries, fired, hits = int(z["tries"].sum()), int(z["fired"].sum()), int(z["hits"].sum())
    p = hits / fired if fired else float("nan")
    ci = 1.96 * math.sqrt(p * (1 - p) / fired) if fired else float("nan")
    return dict(
        cond,
        shots=tries,
        fired=fired,
        scored=hits,
        pct_fired=round(100 * fired / tries, 2),
        pct_scored_of_fired=round(100 * p, 2),
        plus_minus_95=round(100 * ci, 2),
    )


def load_summary(out_dir) -> list[dict]:
    """Rows from summary.csv (ints for id/shots/fired/scored, floats otherwise); if the file
    is missing, rebuilt from cond_XXX.npz. Sorted by id."""
    out = Path(out_dir)
    fn = out / "summary.csv"
    if fn.exists():
        with fn.open(newline="", encoding="utf-8") as fh:
            return [
                {k: int(float(v)) if k in _INT_KEYS else float(v) for k, v in r.items()}
                for r in csv.DictReader(fh)
            ]
    rows = []
    for npz in sorted(out.glob("cond_*.npz")):
        with np.load(npz) as z:
            cond = {k: (int(z[k]) if k == "id" else float(z[k])) for k in _COND_KEYS}
            rows.append(summary_row(cond, z))
    if not rows:
        raise FileNotFoundError(f"no summary.csv or cond_*.npz in {out}")
    return rows


def factor_effects(rows: list[dict]) -> dict[str, list[tuple[float, float]]]:
    """Per factor label: sorted (value, mean % scored of fired) averaged over all other factors."""
    effects = {}
    for label, key in FACTORS:
        vals = sorted({r[key] for r in rows})
        effects[label] = [
            (v, float(np.mean([r[SCORE_KEY] for r in rows if r[key] == v]))) for v in vals
        ]
    return effects


def worst_best(rows: list[dict], n: int = 3) -> tuple[list[dict], list[dict]]:
    """(n lowest, n highest) rows by score rate; each list is ordered worst first / best first."""
    ranked = sorted(rows, key=lambda r: r[SCORE_KEY])
    return ranked[:n], ranked[::-1][:n]


def describe(r: dict) -> str:
    """One-line description of a condition row."""
    return (
        f"aim {r['aim_deg']:g} deg, speed {r['speed_pct']:g}%, moving {r['robot_ips']:g} in/s, "
        f"ball {r['ball_in']:g} in, bounce {r['bounce']:g}: {r[SCORE_KEY]:.1f}% scored"
    )
