"""V1: the kernel's physics against the Java sim, shot by shot, including the study's variables
(robot moving, ball size, bounciness). Needs the Java sim build (bb/out) next door."""

import os
import subprocess
import sys
import tempfile

import numpy as np

from alea.sim.shotsim import ShotSim, aim_heading

# Java sim tree: set ALEA_JAVA_ROOT, default is the repo's parent folder (holds bb/ and rtout/).
JAVA_ROOT = os.environ.get(
    "ALEA_JAVA_ROOT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."),
)
BB = os.path.join(JAVA_ROOT, "bb")
LUT_D = np.array([24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80.0])
LUT_T = np.array(
    [1180, 1110, 1100, 1100, 1120, 1140, 1160, 1180, 1200, 1230, 1260, 1290, 1310, 1340, 1360.0]
)
sim = ShotSim(device="cpu")
rng = np.random.default_rng(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3000


def shots(n, robot_speed):
    x = rng.uniform(15, 126, n)
    y = rng.uniform(9, 42, n)
    h = aim_heading(x, y) + rng.normal(0, np.radians(1.5), n)
    d = np.hypot(58.0 - x, 54.47 - y) - 6.1
    tps = np.interp(d, LUT_D, LUT_T) * (1 + rng.normal(0, 0.03, n))
    ang = rng.uniform(0, 2 * np.pi, n)
    return x, y, h, tps, robot_speed * np.cos(ang), robot_speed * np.sin(ang)


configs = [
    ("nominal ball, robot still", 2.8, 0.45, 0.0),
    ("robot moving 15 in/s", 2.8, 0.45, 15.0),
    ("bigger ball 2.9 in", 2.9, 0.45, 0.0),
    ("bouncier 0.6", 2.8, 0.60, 0.0),
    ("all three at once", 2.9, 0.60, 15.0),
]
allok = True
gold = []
for name, dia, e, spd in configs:
    x, y, h, t, vx, vy = shots(N, spd)
    fn = os.path.join(tempfile.gettempdir(), "alea_shots.txt")
    np.savetxt(fn, np.c_[x, y, h, t, vx, vy], fmt="%.9f")
    java = subprocess.run(
        ["java", "-cp", os.path.join(BB, "out"), "ShotDump", str(dia), str(e), fn],
        capture_output=True,
        text=True,
    ).stdout.split()
    java = np.array(list(map(int, java)))
    k = sim.run(x, y, h, t, vx, vy, dia / 2, e)
    agree = (java == k).mean()
    gold.append(np.c_[x, y, h, t, vx, vy, np.full(N, dia), np.full(N, e), java])
    print(
        f"{name:28s} java scored {np.mean(java == 1):6.1%}  kernel {np.mean(k == 1):6.1%}  "
        f"shot-by-shot agreement {agree:.2%} ({(java != k).sum()} of {N} differ)"
    )
    allok &= agree > 0.99
print("PASS" if allok else "FAIL")
if allok and "--save" in sys.argv:
    # Never overwrite tests/golden/golden_shots.npy: it is append-only. Ask the user to adopt a new one.
    os.makedirs("results", exist_ok=True)
    np.save(os.path.join("results", "golden_shots_new.npy"), np.concatenate(gold))
    print(
        "saved results/golden_shots_new.npy (Java answers; do NOT replace tests/golden without approval)"
    )
