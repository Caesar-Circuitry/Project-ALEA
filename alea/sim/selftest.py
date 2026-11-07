"""
Run this FIRST on the GPU machine. It proves the GPU gives the same answers as the Java sim
before any big run. No Java needed: golden_shots.npy holds 10,000 shots and the Java sim's
answer for each (made by verify_physics.py on a computer that has the Java sim).
  python -m alea.sim.selftest [device]
"""

import sys
from pathlib import Path

import numpy as np
import warp as wp

from alea.sim.conditions import all_conditions
from alea.sim.shotsim import ShotSim
from alea.sim.study import Study

wp.config.quiet = True  # pyright: ignore[reportAttributeAccessIssue]

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden" / "golden_shots.npy"


def golden_agreement(sim):
    """Share of the golden Java shots the kernel reproduces exactly, and the shot count."""
    g = np.load(GOLDEN)
    got = np.empty(len(g), dtype=int)
    for dia, e in sorted({(r[6], r[7]) for r in g}):
        m = (g[:, 6] == dia) & (g[:, 7] == e)
        got[m] = sim.run(g[m, 0], g[m, 1], g[m, 2], g[m, 3], g[m, 4], g[m, 5], dia / 2, e)
    return float((got == g[:, 8].astype(int)).mean()), len(g)


def main(device=None):
    ok = True
    sim = ShotSim(device)
    print(f"device: {sim.device}")
    agree, n_golden = golden_agreement(sim)
    print(f"[1] physics vs Java sim: {agree:.3%} of {n_golden:,} shots agree (need >= 99.9%)")
    ok &= agree >= 0.999

    st = Study(sim.device)
    c = all_conditions()[0]
    t, f, h, dbg = st.run(c, 20000, seed=1, batch=7000, debug=True)  # pyright: ignore[reportAssignmentType]
    fired = dbg[:, 5] == 1
    rep = sim.run(
        dbg[fired, 0],
        dbg[fired, 1],
        dbg[fired, 6],
        dbg[fired, 7],
        dbg[fired, 8],
        dbg[fired, 9],
        c["ball_in"] / 2,
        c["bounce"],
    )
    same = (rep == dbg[fired, 10].astype(int)).mean()
    print(f"[2] study kernel replayed through the physics kernel: {same:.3%} identical (need 100%)")
    ok &= same == 1.0
    counts = (t.sum() == 20000, f.sum() == fired.sum(), h.sum() == (dbg[:, 10] == 1).sum())
    print(f"[3] heat-map counts add up (tries, fired, hits): {counts}")
    ok &= all(counts)
    t2, f2, h2 = st.run(c, 20000, seed=1, batch=20000)  # pyright: ignore[reportAssignmentType]
    rep_ok = (t2 == t).all() and (f2 == f).all() and (h2 == h).all()
    print(f"[4] same seed gives the same answer (batch size changed too): {rep_ok}")
    ok &= bool(rep_ok)
    print("SELF-TEST PASSED" if ok else "SELF-TEST FAILED: do not run the study")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1] if len(sys.argv) > 1 else None) else 1)
