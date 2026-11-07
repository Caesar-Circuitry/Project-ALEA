"""V1: the kernel's physics against the Java sim, shot by shot, including the study's variables
(robot moving, ball size, bounciness). Needs the Java sim build (bb/out) next door."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from alea.game.biobuzz import (
    HIVE_AUDIENCE_MOUTH_Y_IN,
    HIVE_RESTITUTION,
    HIVE_X_IN,
    LAUNCH_EXIT_X_IN,
    LUT_DISTANCE_IN,
    LUT_TICKS_PER_SEC,
    POLLEN_RADIUS_IN,
)
from alea.sim.shotsim import ShotSim, aim_heading

# Java sim tree: set ALEA_JAVA_ROOT, default is the repo's parent folder (holds bb/ and rtout/).
JAVA_ROOT = Path(os.environ.get("ALEA_JAVA_ROOT") or Path(__file__).resolve().parents[4])
BB = JAVA_ROOT / "bb"
LUT_D = np.array(LUT_DISTANCE_IN, dtype=float)
LUT_T = np.array(LUT_TICKS_PER_SEC, dtype=float)
BALL_IN = 2 * POLLEN_RADIUS_IN
sim = ShotSim(device="cpu")
rng = np.random.default_rng(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3000


def shots(n, robot_speed):
    x = rng.uniform(15, 126, n)
    y = rng.uniform(9, 42, n)
    h = aim_heading(x, y) + rng.normal(0, np.radians(1.5), n)
    d = np.hypot(HIVE_X_IN[0] - x, HIVE_AUDIENCE_MOUTH_Y_IN - y) + LAUNCH_EXIT_X_IN
    tps = np.interp(d, LUT_D, LUT_T) * (1 + rng.normal(0, 0.03, n))
    ang = rng.uniform(0, 2 * np.pi, n)
    return x, y, h, tps, robot_speed * np.cos(ang), robot_speed * np.sin(ang)


def run_java(*args):
    """Run a Java dump tool; fail loudly (with its stderr) instead of on a later shape error."""
    try:
        return subprocess.run(
            ["java", *map(str, args)], capture_output=True, text=True, check=True
        ).stdout
    except FileNotFoundError:
        sys.exit("java not found on PATH; install a JDK to run this check")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"java {' '.join(map(str, args))} failed ({exc.returncode}):\n{exc.stderr}")


configs = [
    ("nominal ball, robot still", BALL_IN, HIVE_RESTITUTION, 0.0),
    ("robot moving 15 in/s", BALL_IN, HIVE_RESTITUTION, 15.0),
    ("bigger ball 2.9 in", 2.9, HIVE_RESTITUTION, 0.0),
    ("bouncier 0.6", BALL_IN, 0.60, 0.0),
    ("all three at once", 2.9, 0.60, 15.0),
]
allok = True
gold = []
with tempfile.TemporaryDirectory(prefix="alea_") as tmp:
    fn = Path(tmp) / "shots.txt"
    for name, dia, e, spd in configs:
        x, y, h, t, vx, vy = shots(N, spd)
        np.savetxt(fn, np.c_[x, y, h, t, vx, vy], fmt="%.9f")
        java = np.array(list(map(int, run_java("-cp", BB / "out", "ShotDump", dia, e, fn).split())))
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
    Path("results").mkdir(exist_ok=True)
    np.save(Path("results") / "golden_shots_new.npy", np.concatenate(gold))
    print(
        "saved results/golden_shots_new.npy (Java answers; do NOT replace tests/golden without approval)"
    )
