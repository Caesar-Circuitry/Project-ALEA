"""
The Brev run: every condition in the study config x 1,000,000 shots.

  python -m alea.sim.run_study                       # self-test, speed check, then the full study
  python -m alea.sim.run_study --shots 10000         # quick trial
  python -m alea.sim.run_study --plan                # just print the conditions and the estimate
  python -m alea.sim.run_study --config conf/study/brev72.yaml

Command-line flags override the config file. Results go to the output directory (default
results/study, git-ignored): one file per condition (so a stopped run picks up where it left
off), then summary.csv and plots once everything is done.

Fidelity "hifi" (--fidelity hifi, or `fidelity: hifi` plus a `hifi:` block in the YAML) runs the
same fast shot kernel and then the dsim hive sessions (alea/hifi/hive_session.py). Its results
are labelled and kept apart: default directory results/study-hifi, files cond_hifi_XXX.npz and
summary_hifi.csv. A directory holding fast results refuses hifi output and vice versa.
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
import warp as wp
import yaml

from alea.hifi import FIDELITY_CHOICES, check_fidelity
from alea.hifi.hifi_study import DEFAULT_OUT as HIFI_DEFAULT_OUT
from alea.hifi.hifi_study import HifiParams, params_match, run_condition
from alea.sim import plots, results, selftest
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
    ap.add_argument(
        "--fidelity", default=None, choices=FIDELITY_CHOICES, help="fast (default) or hifi"
    )
    ap.add_argument("--skip-selftest", action="store_true")
    ap.add_argument("--plan", action="store_true", help="print the plan and estimate only")
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    with Path(a.config).open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    fidelity = check_fidelity(a.fidelity if a.fidelity is not None else cfg.get("fidelity", "fast"))
    hifi_params = HifiParams.from_config(cfg.get("hifi")) if fidelity == "hifi" else None
    shots = int(a.shots if a.shots is not None else cfg.get("shots", 1e6))
    batch = int(a.batch if a.batch is not None else cfg.get("batch", 1e6))
    seed = int(a.seed if a.seed is not None else cfg.get("seed", 24331))
    out = Path(a.out if a.out is not None else cfg.get("out", "results/study"))
    if fidelity == "hifi" and a.out is None and out == Path("results/study"):
        # The YAML's fast default must not receive hifi results. We cannot tell an explicit
        # `out: results/study` from the default, so say so rather than redirect silently.
        out = Path(HIFI_DEFAULT_OUT)
        print(f"fidelity hifi: output redirected from results/study to {out} (--out overrides)")
    held = results.detect_fidelity(out) if out.exists() else None
    if held is not None and held != fidelity:
        sys.exit(f"{out} holds {held} results; refusing to write {fidelity} results there")
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
    rate_shots_s = n / (time.time() - t0)
    eta_s = shots * len(conds) / rate_shots_s
    eta_min = eta_s / 60
    print(
        f"speed: {rate_shots_s:,.0f} shots/s  ->  estimated {eta_min:.1f} min for the whole study"
    )
    if a.plan:
        for c in conds:
            print(c)
        return

    out.mkdir(parents=True, exist_ok=True)
    print(f"fidelity: {fidelity}   output: {out}")
    t_start = time.time()
    for i, c in enumerate(conds):
        fn = results.cond_path(out, c["id"], fidelity)
        if fn.exists():
            z = np.load(fn)
            if (
                int(z["shots"]) == shots
                and int(z["seed"]) == seed
                and (hifi_params is None or params_match(z, hifi_params))
            ):
                print(f"[{i + 1}/{len(conds)}] already done, skipping")
                continue
        t0 = time.time()
        if hifi_params is not None:
            tries, fired, hits, sess = run_condition(st, c, shots, seed, batch, hifi_params)
            np.savez_compressed(
                fn,
                tries=tries,
                fired=fired,
                hits=hits,
                shots=shots,
                seed=seed,
                fidelity="hifi",
                **sess,
                **c,
            )
        else:
            tries, fired, hits = st.run(c, shots, seed=seed + 1000 * c["id"], batch=batch)  # pyright: ignore[reportAssignmentType]
            np.savez_compressed(
                fn, tries=tries, fired=fired, hits=hits, shots=shots, seed=seed, **c
            )
        p = hits.sum() / max(fired.sum(), 1)
        print(
            f"[{i + 1}/{len(conds)}] aim {c['aim_deg']} deg, speed {c['speed_pct']}%, "
            f"moving {c['robot_ips']} in/s, ball {c['ball_in']} in, bounce {c['bounce']}: "
            f"{p:.1%} of fired shots scored  ({time.time() - t0:.1f} s)",
            flush=True,
        )

    rows = []
    for c in conds:
        z = np.load(results.cond_path(out, c["id"], fidelity))
        row = results.summary_row(c, z)
        if fidelity == "hifi":
            row["fidelity"] = "hifi"
            row.update({k: z[k].item() for k in z.files if k.startswith("hive_")})
        rows.append(row)
    summary_fn = results.summary_path(out, fidelity)
    with summary_fn.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\ndone in {(time.time() - t_start) / 60:.1f} min -> {summary_fn}")
    plots.main(out)


if __name__ == "__main__":
    main()
