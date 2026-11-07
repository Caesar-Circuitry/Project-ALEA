"""Run the same sweep as the Java LutSweep tool and compare."""

import time
from pathlib import Path

import numpy as np

from alea.sim.shotsim import ShotSim, aim_heading

sim = ShotSim()
xs, ys = np.meshgrid(np.arange(30, 91, 4), np.arange(6, 43, 4), indexing="ij")
xs, ys = xs.ravel(), ys.ravel()
tps = np.arange(800, 2801, 20)
X = np.repeat(xs, len(tps))
Y = np.repeat(ys, len(tps))
T = np.tile(tps, len(xs))
H = aim_heading(X, Y)
sim.run(X[:10], Y[:10], H[:10], T[:10])  # compile
t = time.time()
r = sim.run(X, Y, H, T)
dt = time.time() - t
print(f"{len(X)} shots on {sim.device} in {dt:.2f} s = {dt / len(X) * 1e6:.1f} us/shot")
r = r.reshape(len(xs), len(tps)) == 1
mine = {}
for i in range(len(xs)):
    if r[i].any():
        w = tps[r[i]]
        mine[(xs[i], ys[i])] = (r[i].sum(), w.min(), w.max())
ref = {}
for line in open(Path(__file__).with_name("java_ref.txt")):
    p = line.split()
    ref[(int(p[0]), int(p[1]))] = (int(p[5]), *map(float, p[7].split("..")))
keys = sorted(set(ref) | set(mine))
same = sum(1 for k in keys if (k in ref) == (k in mine))
print(
    f"spots that score: java {len(ref)}, gpu kernel {len(mine)}; agree on scores/doesn't for {same}/{len(keys)}"
)
dn = [abs(ref[k][0] - mine[k][0]) for k in keys if k in ref and k in mine]
tot_ref = sum(v[0] for v in ref.values())
tot_me = sum(v[0] for v in mine.values())
print(
    f"scoring (spot, speed) pairs: java {tot_ref}, kernel {tot_me}; per-spot speed-count diff max {max(dn) if dn else 0}, mean {np.mean(dn) if dn else 0:.2f}"
)
for k in keys:
    if ref.get(k) != tuple(mine.get(k, ())) and (
        k not in ref or k not in mine or abs(ref[k][0] - mine[k][0]) > 1
    ):
        print(k, "java", ref.get(k), "kernel", mine.get(k))
