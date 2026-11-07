# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Study results
#
# Loads a finished study from `results/study` (the Brev run or `just study`). If there is
# none, runs a tiny 4-condition CPU study into a temporary folder so the notebook still works;
# those numbers are noisy. All logic lives in `alea.sim.results`.

# %%
import tempfile
from pathlib import Path

import numpy as np
from IPython.display import Image, display

from alea.sim import plots, results
from alea.sim.conditions import all_conditions
from alea.sim.study import Study

STUDY_DIR = Path("results/study")
TINY_SHOTS = 20_000  # per condition in the fallback run
SEED = 24331

# %%
tmp = tempfile.TemporaryDirectory()
if (STUDY_DIR / "summary.csv").exists() or any(STUDY_DIR.glob("cond_*.npz")):
    out_dir = STUDY_DIR
else:
    out_dir = Path(tmp.name)
    study = Study("cpu")
    grid = dict(
        aim_deg=[1.0, 2.0], speed_pct=[2.0], robot_ips=[0.0, 10.0], ball_in=[2.5], bounce=[0.5]
    )
    for c in all_conditions(grid):
        tries, fired, hits = study.run(c, TINY_SHOTS, seed=SEED + 1000 * c["id"])
        np.savez_compressed(
            out_dir / f"cond_{c['id']:03d}.npz",
            tries=tries,
            fired=fired,
            hits=hits,
            shots=TINY_SHOTS,
            seed=SEED,
            **c,
        )
rows = results.load_summary(out_dir)
print(f"{len(rows)} conditions from {out_dir}")

# %% [markdown]
# ## Effect of each variable (averaged over all the others)

# %%
for label, effect in results.factor_effects(rows).items():
    print(f"{label:28s}", "  ".join(f"{v:g}: {pct:5.1f}%" for v, pct in effect))

# %% [markdown]
# ## Worst and best conditions

# %%
worst, best = results.worst_best(rows, n=3)
print("worst")
for r in worst:
    print("  ", results.describe(r))
print("best")
for r in best:
    print("  ", results.describe(r))

# %% [markdown]
# ## Heat map of the worst condition

# %%
r = worst[0]
with np.load(out_dir / f"cond_{r['id']:03d}.npz") as z:
    png = Path(tmp.name) / "heatmap_worst.png"
    plots.heatmap(z, results.describe(r), png)
    display(Image(data=png.read_bytes()))
