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
# # CPU study and heat map (tiny run)
#
# Runs the "normal robot" condition of the Brev study on the CPU with a very small shot
# count, then draws the scoring heat map. Numbers are noisy at this size; use
# `just study` or the Brev run for real results. All logic lives in `alea`.

# %%
import tempfile
from pathlib import Path

from IPython.display import Image, display

from alea.sim import plots
from alea.sim.conditions import all_conditions
from alea.sim.study import Study

SHOTS = 20_000  # per condition; the real study uses 1,000,000
SEED = 24331

# %%
study = Study("cpu")
cond = all_conditions()[0]  # first value of every list = the normal robot
tries, fired, hits = study.run(cond, SHOTS, seed=SEED)
print(cond)
print(f"fired {fired.sum():,} of {SHOTS:,} shots, {hits.sum() / max(fired.sum(), 1):.1%} scored")

# %%
with tempfile.TemporaryDirectory() as tmp:
    png = Path(tmp) / "heatmap.png"
    z = {"tries": tries, "fired": fired, "hits": hits}
    plots.heatmap(z, f"normal robot, {SHOTS:,} shots (CPU)", png)
    display(Image(data=png.read_bytes()))
