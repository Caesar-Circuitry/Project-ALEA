"""
The Brev run: every condition in the study config x 1,000,000 shots.

  python -m alea.sim.run_study                       # self-test, speed check, then the full study
  python -m alea.sim.run_study --shots 10000         # quick trial
  python -m alea.sim.run_study --plan                # just print the conditions and the estimate
  python -m alea.sim.run_study --config conf/study/brev72.yaml

Command-line flags override the config file. Results go to the output directory (default
results/study, git-ignored): one file per condition (so a stopped run picks up where it left
off), then summary.csv and plots once everything is done.
"""

import argparse
import csv
import math
import sys
import time
from pathlib import Path

import numpy as np
import warp as wp
import yaml

from alea.sim import plots, selftest
from alea.sim.conditions import all_conditions
from alea.sim.study import Study

wp.config.quiet = True  # pyright: ignore[reportAttributeAccessIssue]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "conf" / "study" / "brev72.yaml"


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="study YAML (default brev72)")
    ap.add_argument("--shots", type=float, default=None, help="shots per condition")
    ap.add_argument("--batch", type=float, default=None, help="shots per GPU launch")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default=None, help="output directory")
    ap.add_argument("--device", default=None, help="cuda / cuda:0 / cpu (default: GPU if any)")
    ap.add_argument("--skip-selftest", action="store_true")
    ap.add_argument("--plan", action="store_true", help="print the plan and estimate only")
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    with open(a.config, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    shots = int(a.shots if a.shots is not None else cfg.get("shots", 1e6))
    batch = int(a.batch if a.batch is not None else cfg.get("batch", 1e6))
    seed = int(a.seed if a.seed is not None else cfg.get("seed", 24331))
    out = Path(a.out if a.out is not None else cfg.get("out", "results/study"))
    if shots > 2_000_000_000:
        sys.exit("at most 2 billion shots per condition (random-number offsets are 32-bit)")

    conds = all_conditions(cfg.get("conditions"))
    st = Study(a.device)
    print(
        f"device: {st.device}   conditions: {len(conds)}   shots each: {shots:,}   "
        f"total: {shots * len(conds):,}"
    )
    if st.device == "cpu":
        print("WARNING: no GPU found, this will be slow (about 5,000 shots/s per core).")

    if not a.skip_selftest and not a.plan and not selftest.main(st.device):
        sys.exit("self-test failed: not running the study")

    # speed check on the normal condition
    n = min(200_000, shots)
    st.run(conds[0], 1000, seed=0)  # compile
    wp.synchronize()
    t0 = time.time()
    st.run(conds[0], n, seed=0, batch=batch)
    wp.synchronize()
    rate = n / (time.time() - t0)
    eta = shots * len(conds) / rate
    print(f"speed: {rate:,.0f} shots/s  ->  estimated {eta / 60:.1f} min for the whole study")
    if a.plan:
        for c in conds:
            print(c)
        return

    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    for i, c in enumerate(conds):
        fn = out / f"cond_{c['id']:03d}.npz"
        if fn.exists():
            z = np.load(fn)
            if int(z["shots"]) == shots and int(z["seed"]) == seed:
                print(f"[{i + 1}/{len(conds)}] already done, skipping")
                continue
        t0 = time.time()
        tries, fired, hits = st.run(c, shots, seed=seed + 1000 * c["id"], batch=batch)  # pyright: ignore[reportAssignmentType]
        np.savez_compressed(fn, tries=tries, fired=fired, hits=hits, shots=shots, seed=seed, **c)
        p = hits.sum() / max(fired.sum(), 1)
        print(
            f"[{i + 1}/{len(conds)}] aim {c['aim_deg']} deg, speed {c['speed_pct']}%, "
            f"moving {c['robot_ips']} in/s, ball {c['ball_in']} in, bounce {c['bounce']}: "
            f"{p:.1%} of fired shots scored  ({time.time() - t0:.1f} s)",
            flush=True,
        )

    rows = []
    for c in conds:
        z = np.load(out / f"cond_{c['id']:03d}.npz")
        T, F, H = z["tries"].sum(), z["fired"].sum(), z["hits"].sum()
        p = H / F if F else float("nan")
        ci = 1.96 * math.sqrt(p * (1 - p) / F) if F else float("nan")
        rows.append(
            dict(
                c,
                shots=int(T),
                fired=int(F),
                scored=int(H),
                pct_fired=round(100 * F / T, 2),
                pct_scored_of_fired=round(100 * p, 2),
                plus_minus_95=round(100 * ci, 2),
            )
        )
    with open(out / "summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\ndone in {(time.time() - t_start) / 60:.1f} min -> {out / 'summary.csv'}")
    plots.main(out)


if __name__ == "__main__":
    main()
