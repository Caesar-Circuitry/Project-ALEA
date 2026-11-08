"""Calibration report: video-measured efficiency and drag against the sim's assumptions.

``python -m alea.analysis.calibration_report measurements.csv --out dir`` writes
``calibration_report.json``, ``calibration_report.md`` and two PNGs.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from alea.analysis.efficiency import (
    SIM_ASSUMED_EFFICIENCY,
    EfficiencyEstimate,
    Row,
    bayes_normal,
    bootstrap_mean,
    by_burst_index,
    column,
    compare_to_sim,
    estimate_drag,
    exclude,
    hierarchical_by_group,
    read_measurements_csv,
    speed_model_fit,
)
from alea.game.biobuzz import AIR_DRAG, TICKS_TO_IN_S

MIN_N_WARN = 10
DEFAULT_N_BOOT = 2000
DEFAULT_MIN_FIT_RMS_IN = 2.0


def _clean(obj: Any) -> Any:
    """Make nested values JSON-safe (NaN and inf become None, numpy scalars become Python)."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _efficiency_rows(rows: list[Row]) -> list[Row]:
    return [r for r in rows if r.get("efficiency") is not None]


def build_report(
    rows: Sequence[Row],
    seed: int = 0,
    n_boot: int = DEFAULT_N_BOOT,
    min_fit_rms_in: float | None = DEFAULT_MIN_FIT_RMS_IN,
) -> dict[str, Any]:
    """Build the JSON-serialisable calibration report from measurement rows."""
    kept, counts = exclude(rows, min_fit_rms_in=min_fit_rms_in)
    eff_rows = _efficiency_rows(kept)
    eff = column(eff_rows, "efficiency")
    sessions = [str(r.get("video_file") or "unknown") for r in eff_rows]
    burst_rows = [r for r in eff_rows if r.get("burst_index") is not None]

    boot = bootstrap_mean(eff, n_boot=n_boot, seed=seed)
    bayes = bayes_normal(eff, seed=seed)
    hier = hierarchical_by_group(eff, sessions, n_boot=n_boot, seed=seed)
    burst = by_burst_index(
        column(burst_rows, "efficiency"),
        [int(r["burst_index"]) for r in burst_rows],
        n_boot=n_boot,
        seed=seed,
    )
    drag = estimate_drag(column(kept, "drag_per_s"), n_boot=n_boot, seed=seed)

    fit_rows = [
        r
        for r in kept
        if r.get("flywheel_ticks_per_s_before") is not None and r.get("v_exit_in_s") is not None
    ]
    speed = speed_model_fit(
        column(fit_rows, "flywheel_ticks_per_s_before"),
        column(fit_rows, "v_exit_in_s"),
        n_boot=n_boot,
        seed=seed,
    )

    warnings: list[str] = []
    if boot.n < MIN_N_WARN:
        warnings.append(f"Only {boot.n} usable efficiency measurements (< {MIN_N_WARN}).")
    if drag.n < MIN_N_WARN:
        warnings.append(f"Only {drag.n} drag measurements (< {MIN_N_WARN}).")
    if hier.extra.get("n_groups", 0) < 3:
        warnings.append("Fewer than 3 sessions: between-session spread is poorly determined.")
    caveats = [
        f"The sim's efficiency {SIM_ASSUMED_EFFICIENCY} is a placeholder: the last factor of "
        "alea.game.TICKS_TO_IN_S, not exported from alea.game.",
        "Speeds are measured in the ball-plane tag scale; a scale error maps one-to-one into "
        "efficiency and drag.",
        "Shots in a session are correlated; the plain bootstrap and Bayes CIs ignore that, the "
        "hierarchical CI does not.",
    ]
    return _clean(
        {
            "inputs": {
                "n_rows": counts["total"],
                "n_kept": counts["kept"],
                "n_with_efficiency": int(eff.size),
                "n_sessions": hier.extra.get("n_groups", 0),
                "seed": seed,
                "n_boot": n_boot,
            },
            "exclusions": {"min_fit_rms_in": min_fit_rms_in, **counts},
            "efficiency": {
                "sim_value": SIM_ASSUMED_EFFICIENCY,
                "bootstrap": boot.to_dict(),
                "bayes_normal": bayes.to_dict(),
                "hierarchical": hier.to_dict(),
                "vs_sim": compare_to_sim(hier if hier.n else boot, SIM_ASSUMED_EFFICIENCY),
                "vs_sim_naive": compare_to_sim(boot, SIM_ASSUMED_EFFICIENCY),
            },
            "by_session": {k: v.to_dict() for k, v in hier.groups.items()},
            "by_burst_index": burst.to_dict(),
            "drag": {
                "sim_value_per_s": AIR_DRAG,
                "estimate": drag.to_dict(),
                "vs_sim": compare_to_sim(drag, AIR_DRAG),
            },
            "speed_model": speed,
            "warnings": warnings,
            "caveats": caveats,
        }
    )


def _fmt_est(d: dict[str, Any]) -> str:
    ci = d["ci95"]
    if d["mean"] is None:
        return "no data"
    return f"{d['mean']:.4f} (se {d['se']:.4f}, 95 % CI {ci[0]:.4f} to {ci[1]:.4f}, n={d['n']})"


def render_markdown(report: dict[str, Any]) -> str:
    """Render the report dict as Markdown."""
    e = report["efficiency"]
    lines = ["# Calibration report", ""]
    inp = report["inputs"]
    lines += [
        f"Rows: {inp['n_rows']}, kept: {inp['n_kept']}, with efficiency: "
        f"{inp['n_with_efficiency']}, sessions: {inp['n_sessions']}, seed {inp['seed']}.",
        "",
        "## Efficiency",
        "",
        f"Sim assumes {e['sim_value']}.",
        "",
        f"- Bootstrap (shots): {_fmt_est(e['bootstrap'])}",
        f"- Bayes normal (prior {e['sim_value']}, sd 0.1): {_fmt_est(e['bayes_normal'])}",
        f"- Hierarchical (sessions): {_fmt_est(e['hierarchical'])}",
    ]
    vs = e["vs_sim"]
    if vs["z"] is not None:
        verdict = "inside" if vs["sim_inside_ci95"] else "outside"
        lines.append(
            f"- Versus sim: z = {vs['z']:.2f}, sim value {verdict} the CI, "
            f"relative difference {100 * vs['relative_difference']:+.1f} %."
        )
    lines += ["", "## By session", ""]
    for name, d in report["by_session"].items():
        lines.append(f"- {name}: {_fmt_est(d)}")
    b = report["by_burst_index"]
    lines += ["", "## By burst index", ""]
    for name, d in b["groups"].items():
        lines.append(f"- {name}: {_fmt_est(d)}")
    slope = b["extra"].get("slope_per_index")
    if slope is not None:
        lines.append(f"- Slope per burst index: {slope:+.4f}")
    d = report["drag"]
    lines += ["", "## Drag", "", f"Sim assumes {d['sim_value_per_s']} 1/s.", ""]
    lines.append(f"- Estimate: {_fmt_est(d['estimate'])}")
    if d["vs_sim"]["z"] is not None:
        lines.append(
            f"- Versus sim: z = {d['vs_sim']['z']:.2f}, "
            f"inside CI: {d['vs_sim']['sim_inside_ci95']}."
        )
    s = report["speed_model"]
    lines += ["", "## Speed model", ""]
    if s.get("a_origin") is not None:
        ci = s["a_origin_ci95"]
        lines += [
            f"- v = a * ticks: a = {s['a_origin']:.5f} (95 % CI {ci[0]:.5f} to {ci[1]:.5f}); "
            f"sim TICKS_TO_IN_S = {s['sim_a']:.5f}; ratio {s['a_over_sim']:.3f}.",
        ]
        if s.get("intercept_in_s") is not None:
            lines.append(
                f"- With intercept: a = {s['a_intercept']:.5f}, b = {s['intercept_in_s']:.2f} in/s."
            )
    else:
        lines.append("- Not enough data.")
    ex = report["exclusions"]
    lines += [
        "",
        "## Exclusions",
        "",
        f"- Max fit RMS kept: {ex['min_fit_rms_in']} in; dropped for bad fit: {ex['bad_fit']}; "
        f"dropped for result tag: {ex['result']}.",
        "",
        "## Warnings",
        "",
    ]
    lines += [f"- {w}" for w in report["warnings"]] or ["- None."]
    lines += ["", "## Caveats", ""] + [f"- {c}" for c in report["caveats"]]
    return "\n".join(lines) + "\n"


def _est_from_dict(d: dict[str, Any]) -> EfficiencyEstimate:
    ci = d["ci95"]
    return EfficiencyEstimate(d["n"], d["mean"], d["sd"], d["se"], (ci[0], ci[1]), d["method"])


def _plot(rows: Sequence[Row], report: dict[str, Any], out_dir: Path) -> list[Path]:
    kept, _ = exclude(rows, min_fit_rms_in=report["exclusions"]["min_fit_rms_in"])
    eff_rows = _efficiency_rows(kept)
    eff = column(eff_rows, "efficiency")
    paths = []

    fig, ax = plt.subplots(figsize=(6, 4))
    if eff.size:
        ax.hist(eff, bins=min(20, max(5, eff.size // 2)), color="#4c78a8", alpha=0.8)
    h = report["efficiency"]["hierarchical"]
    if h["mean"] is not None:
        ax.axvline(h["mean"], color="black", label="mean")
        ax.axvspan(h["ci95"][0], h["ci95"][1], color="grey", alpha=0.3, label="95 % CI")
    ax.axvline(SIM_ASSUMED_EFFICIENCY, color="#e45756", ls="--", label="sim (0.45)")
    ax.set_xlabel("efficiency (v_exit / wheel surface speed)")
    ax.set_ylabel("shots")
    ax.legend()
    fig.tight_layout()
    p = out_dir / "efficiency_hist.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(p)

    fig, ax = plt.subplots(figsize=(6, 4))
    pts = [r for r in eff_rows if r.get("flywheel_ticks_per_s_before") is not None]
    if pts:
        t = column(pts, "flywheel_ticks_per_s_before")
        e = column(pts, "efficiency")
        ax.scatter(t, e, s=14, color="#4c78a8")
        ax.axhline(SIM_ASSUMED_EFFICIENCY, color="#e45756", ls="--", label="sim (0.45)")
        s = report["speed_model"]
        if s.get("a_origin") is not None:
            ax.axhline(
                s["a_origin"] / TICKS_TO_IN_S * SIM_ASSUMED_EFFICIENCY,
                color="black",
                label="fit through origin",
            )
        if s.get("intercept_in_s") is not None and t.size:
            xs = np.linspace(float(t.min()), float(t.max()), 50)
            ax.plot(
                xs,
                (s["a_intercept"] * xs + s["intercept_in_s"])
                / (xs * TICKS_TO_IN_S / SIM_ASSUMED_EFFICIENCY),
                color="#54a24b",
                label="fit with intercept",
            )
        ax.legend()
    ax.set_xlabel("flywheel ticks/s before")
    ax.set_ylabel("efficiency")
    fig.tight_layout()
    p = out_dir / "efficiency_vs_ticks.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(p)
    return paths


def write_report(
    rows: Sequence[Row], out_dir: Path | str, seed: int = 0, n_boot: int = DEFAULT_N_BOOT
) -> dict[str, Path]:
    """Write JSON, Markdown and two PNGs into ``out_dir``; return the paths by name."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = build_report(rows, seed=seed, n_boot=n_boot)
    jpath = out / "calibration_report.json"
    jpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
    mpath = out / "calibration_report.md"
    mpath.write_text(render_markdown(report), encoding="utf-8")
    hist, scatter = _plot(rows, report, out)
    return {"json": jpath, "markdown": mpath, "histogram": hist, "scatter": scatter}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Efficiency and drag calibration report.")
    parser.add_argument("csv", type=Path, help="measurements.csv from the importer")
    parser.add_argument("--out", type=Path, default=Path("calibration_out"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-boot", type=int, default=DEFAULT_N_BOOT)
    args = parser.parse_args(argv)
    paths = write_report(read_measurements_csv(args.csv), args.out, args.seed, args.n_boot)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
