"""Pictures from a finished study:  python -m alea.sim.plots [results/study]
heatmap_normal.png : where the normal robot scores (condition 0)
heatmap_worst.png  : the condition with the lowest score rate
effects.png        : how much each variable changes the score rate (averaged over the others)
"""

import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

from alea.sim import results
from alea.sim.shotsim import FIELD
from alea.sim.study import CELL, TARGET_X, TARGET_Y, Y_MAX

MIN_FIRED = 30  # cells with fewer fired shots than this are left blank (too few to trust)


def heatmap(z, title, fn, label=""):
    T, F, H = z["tries"], z["fired"], z["hits"]
    rate = np.where(F >= MIN_FIRED, H / np.maximum(F, 1), np.nan)
    hold = (T > 0) & (F == 0)
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
    ext = (0, rate.shape[0] * CELL, 0, rate.shape[1] * CELL)
    ax.imshow(
        np.where(hold, 1, np.nan).T,
        origin="lower",
        extent=ext,
        cmap=ListedColormap(["#d9d9d9"]),
        vmin=0,
        vmax=1,
    )
    ax.imshow(
        np.where(T == 0, 1, np.nan).T,
        origin="lower",
        extent=ext,
        cmap=ListedColormap(["#555555"]),
        vmin=0,
        vmax=1,
    )
    im = ax.imshow(rate.T * 100, origin="lower", extent=ext, cmap="RdYlGn", vmin=0, vmax=100)
    ax.plot(TARGET_X, TARGET_Y, "k*", ms=14)
    ax.plot([0, FIELD, FIELD, 0, 0], [0, 0, Y_MAX, Y_MAX, 0], "k-", lw=1)
    ax.set_xlim(0, FIELD)
    ax.set_ylim(0, Y_MAX)
    ax.set_aspect("equal")
    ax.set_xlabel("x (in)")
    ax.set_ylabel("y (in)")
    ax.set_title(f"{label}{title}", fontsize=10)
    fig.colorbar(im, ax=ax, label="% of shots that score", shrink=0.8)
    ax.text(
        1,
        Y_MAX - 3,
        "light grey = robot holds fire (out of LUT range / too far round)   "
        "dark grey = robot can't be there (walls, hive frame rails)",
        fontsize=7,
    )
    if label:
        _hifi_caption(fig, str(z["hive_caveat"]) if "hive_caveat" in z.files else "")
    fig.tight_layout(rect=(0, 0.06, 1, 1) if label else None)
    fig.savefig(fn)
    plt.close(fig)


def _hifi_caption(fig, caveat: str):
    """Bottom caption on hifi plots: the numbers shown are the fast kernel's."""
    text = "shot kernel = fast; hive results in summary_hifi.csv"
    if caveat:
        text += "\n" + caveat
    fig.text(0.5, 0.005, text, ha="center", va="bottom", fontsize=6)


def main(out: str | Path = "results/study"):
    out = Path(out)
    rows = results.load_summary(out)
    fidelity = results.detect_fidelity(out) or "fast"
    tag = f"[{fidelity}] " if fidelity == "hifi" else ""
    prefix = "hifi_" if fidelity == "hifi" else ""

    worst = results.worst_best(rows, 1)[0][0]
    for r, fn in [(rows[0], "heatmap_normal.png"), (worst, "heatmap_worst.png")]:
        heatmap(
            np.load(results.cond_path(out, int(r["id"]), fidelity)),
            results.describe(r),
            out / (prefix + fn),
            tag,
        )

    groups = list(results.factor_effects(rows).items())
    fig, axs = plt.subplots(1, len(groups), figsize=(14, 3.6), dpi=150, sharey=True)
    for ax, (label, effect) in zip(axs, groups, strict=True):
        vals = [v for v, _ in effect]
        m = [pct for _, pct in effect]
        ax.bar([f"{v:g}" for v in vals], m, color="#b3161b")
        for i, v in enumerate(m):
            ax.text(i, v + 1, f"{v:.0f}%", ha="center", fontsize=9)
        ax.set_title(label, fontsize=10)
        ax.set_ylim(0, 100)
    axs[0].set_ylabel("% of fired shots that score")
    fig.suptitle(f"{tag}Effect of each variable (averaged over all the others)", fontsize=11)
    if tag:
        _hifi_caption(fig, str(rows[0].get("hive_caveat", "")))
    fig.tight_layout(rect=(0, 0.06, 1, 1) if tag else None)
    fig.savefig(out / f"{prefix}effects.png")
    plt.close(fig)
    print(f"plots written to {out}/")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/study")
