"""V2: the study kernel's robot logic and randomness, checked against the REAL robot code and
the Java sim. Needs ../rtout (AimDump, built from the robot code) and ../bb/out (ShotDump)."""

import math
import os
import subprocess
import tempfile

import numpy as np
import warp as wp

wp.config.quiet = True
from alea.sim.conditions import all_conditions
from alea.sim.shotsim import FX0, FY0
from alea.sim.study import (
    CELL,
    GX,
    GY,
    ROBOT_HALF,
    X_MAX,
    X_MIN,
    Y_MAX,
    Y_MIN,
    Study,
    frame_footprint,
)

S = os.environ.get(
    "ALEA_JAVA_ROOT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."),
)  # folder holding rtout/ and bb/

TMP = os.path.join(tempfile.gettempdir(), "alea_tmp.txt")
st = Study("cpu")
res = []


def check(name, ok, detail=""):
    res.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


cond = dict(all_conditions()[0])
cond.update(robot_ips=10.0, ball_in=2.9, bounce=0.6, aim_deg=1.0, speed_pct=2.0)
N = 40000
t, f, h, d = st.run(cond, N, seed=24331, batch=13000, debug=True)
x, y, th, dist, lut, can, hd, tps, rvx, rvy, result, rej = d.T

# --- 1. aim logic vs the robot code (aimAssist + launchLUT) on 4,000 spots
k = np.arange(4000)
np.savetxt(TMP, np.c_[x[k], y[k]], fmt="%.9f")
j = np.loadtxt(
    subprocess.run(
        ["java", "-cp", os.path.join(S, "rtout"), "AimDump", TMP], capture_output=True, text=True
    ).stdout.splitlines()
)
dh = np.abs((th[k] - j[:, 0] + np.pi) % (2 * np.pi) - np.pi)
check(
    "target heading matches aimAssist",
    dh.max() < 1e-5,
    f"max diff {math.degrees(dh.max()):.2e} deg",
)
check(
    "distance matches aimAssist",
    np.abs(dist[k] - j[:, 1]).max() < 1e-3,
    f"max diff {np.abs(dist[k] - j[:, 1]).max():.1e} in",
)
check(
    "LUT speed matches launchLUT",
    np.abs(lut[k] - j[:, 2]).max() < 0.05,
    f"max diff {np.abs(lut[k] - j[:, 2]).max():.3f} ticks/s",
)
fire_mismatch = (can[k] != j[:, 3]).sum()
check(
    "fire / hold-fire decision matches aimAssist.inRange()",
    fire_mismatch == 0,
    f"{fire_mismatch} of 4000 differ; fires on {can[k].mean():.1%}",
)

# --- 2. the study's shots, replayed in the Java sim (robot moving, big bouncy ball)
fi = np.nonzero(can == 1)[0][:3000]
np.savetxt(TMP, np.c_[x[fi], y[fi], hd[fi], tps[fi], rvx[fi], rvy[fi]], fmt="%.9f")
jr = np.array(
    subprocess.run(
        [
            "java",
            "-cp",
            os.path.join(S, "bb", "out"),
            "ShotDump",
            str(cond["ball_in"]),
            str(cond["bounce"]),
            TMP,
        ],
        capture_output=True,
        text=True,
    ).stdout.split(),
    dtype=int,
)
agree = (jr == result[fi]).mean()
check(
    "study shots give the same result in the Java sim",
    agree >= 0.999,
    f"{agree:.2%} of {len(fi)}; {np.mean(jr == 1):.1%} scored",
)

# --- 3. randomness
err = (hd - th)[can == 1]
check(
    "aim error mean ~0, s.d. = 1.0 deg",
    abs(np.degrees(err.mean())) < 0.03 and abs(np.degrees(err.std()) - 1.0) < 0.03,
    f"mean {np.degrees(err.mean()):+.3f}, sd {np.degrees(err.std()):.3f} deg",
)
sp = (tps / lut - 1)[can == 1]
check(
    "speed error mean ~0, s.d. = 2%",
    abs(sp.mean()) < 0.0006 and abs(sp.std() - 0.02) < 0.0006,
    f"mean {sp.mean():+.4%}, sd {sp.std():.3%}",
)
spd = np.hypot(rvx, rvy)[can == 1]
ang = np.arctan2(rvy, rvx)[can == 1]
check(
    "robot speed is 10 in/s in a random direction",
    np.abs(spd - 10).max() < 1e-3
    and abs(np.cos(ang).mean()) < 0.02
    and abs(np.sin(ang).mean()) < 0.02,
    f"speed {spd.min():.3f}-{spd.max():.3f}, mean dir ({np.cos(ang).mean():+.3f}, {np.sin(ang).mean():+.3f})",
)
check(
    "no spot outside the robot's area",
    x.min() >= X_MIN and x.max() <= X_MAX and y.min() >= Y_MIN and y.max() <= Y_MAX,
)
foot = frame_footprint()


def blocked_np(px, py):
    xs = np.arange(int(np.floor(px - ROBOT_HALF)), int(np.floor(px + ROBOT_HALF)) + 1) - FX0
    ys = np.arange(int(np.floor(py - ROBOT_HALF)), int(np.floor(py + ROBOT_HALF)) + 1) - FY0
    xs = xs[(xs >= 0) & (xs < foot.shape[1])]
    ys = ys[(ys >= 0) & (ys < foot.shape[0])]
    return foot[np.ix_(ys, xs)].any() if len(xs) and len(ys) else False


bad = sum(blocked_np(a, b) for a, b in zip(x, y))
check("no robot placed on the hive frame rails", bad == 0, f"{int(rej.sum())} spots were re-drawn")
# uniform: compare the share of spots in the left vs right third (both rail-free) to their areas
l = (x < 30).mean()
r = (x > X_MAX - (30 - X_MIN)).mean()
check("spots spread evenly", abs(l - r) < 0.01, f"left {l:.3f} right {r:.3f}")
dup = N - len(np.unique(np.c_[x, y], axis=0))
check("no repeated spots (random streams don't overlap)", dup == 0, f"{dup} repeats in {N:,}")

# --- 4. counting
gx = np.minimum((x / CELL).astype(int), GX - 1)
gy = np.minimum((y / CELL).astype(int), GY - 1)
T = np.zeros((GX, GY), int)
F = T.copy()
H = T.copy()
np.add.at(T, (gx, gy), 1)
np.add.at(F, (gx, gy), (can == 1).astype(int))
np.add.at(H, (gx, gy), (result == 1).astype(int))
check(
    "heat-map grids equal a recount of every shot",
    (t == T).all() and (f == F).all() and (h == H).all(),
    f"{t.sum():,} tries, {f.sum():,} fired, {h.sum():,} scored",
)
os.remove(TMP)
print("\nALL PASS" if all(res) else f"\n{res.count(False)} FAILED")
