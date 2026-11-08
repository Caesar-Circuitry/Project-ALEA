"""Known-truth tests for alea.analysis.efficiency."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from alea.analysis.efficiency import (
    CSV_COLUMNS,
    SIM_ASSUMED_EFFICIENCY,
    bayes_normal,
    bootstrap_mean,
    by_burst_index,
    compare_to_sim,
    estimate_drag,
    exclude,
    hierarchical_by_group,
    read_measurements_csv,
    speed_model_fit,
)
from alea.game.biobuzz import AIR_DRAG, TICKS_TO_IN_S

TRUE_EFF = 0.40
TRUE_DRAG = 0.08


def make_rows(seed: int, n_sessions: int = 6, burst_size: int = 3) -> list[dict]:
    """Synthetic measurements. Burst effect is centred so the population mean is TRUE_EFF."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_sessions):
        sess = rng.normal(0.0, 0.01)
        for i in range(int(rng.integers(15, 26))):
            b = i % burst_size
            ticks = float(rng.uniform(900, 1500))
            eff = TRUE_EFF + sess - 0.01 * (b - (burst_size - 1) / 2) + rng.normal(0, 0.02)
            wheel = ticks * TICKS_TO_IN_S / SIM_ASSUMED_EFFICIENCY
            rows.append(
                {
                    "video_file": f"s{s}.mp4",
                    "burst_index": b,
                    "result": "IN",
                    "fit_rms_in": float(rng.uniform(0.1, 0.5)),
                    "flywheel_ticks_per_s_before": ticks,
                    "v_exit_in_s": eff * wheel,
                    "efficiency": eff,
                    "drag_per_s": TRUE_DRAG + rng.normal(0, 0.02),
                }
            )
    return rows


def col(rows, key):
    return np.array([r[key] for r in rows])


def test_bootstrap_coverage():
    hits = 0
    for seed in range(100):
        x = np.random.default_rng(seed).normal(TRUE_EFF, 0.0224, size=100)
        lo, hi = bootstrap_mean(x, n_boot=200, seed=seed).ci95
        hits += lo <= TRUE_EFF <= hi
    assert hits >= 90


def test_hierarchical_pooled_and_groups():
    rows = make_rows(1, n_sessions=10)
    est = hierarchical_by_group(
        col(rows, "efficiency"), [r["video_file"] for r in rows], n_boot=300, seed=1
    )
    assert len(est.groups) == 10
    assert est.extra["within_group_sd"] > 0.015
    assert abs(est.mean - TRUE_EFF) < 0.02
    assert est.ci95[0] < est.mean < est.ci95[1]


def test_bayes_shrinkage():
    x = np.random.default_rng(3).normal(TRUE_EFF, 0.02, size=100)
    small = bayes_normal(x[:3])
    big = bayes_normal(x)
    assert abs(big.mean - x.mean()) < 0.001
    gap = SIM_ASSUMED_EFFICIENCY - x[:3].mean()
    frac_small = (small.mean - x[:3].mean()) / gap
    frac_big = (big.mean - x.mean()) / (SIM_ASSUMED_EFFICIENCY - x.mean())
    # both move toward the prior, n=3 much more than n=100
    assert 0 < frac_big < frac_small < 1
    assert frac_big < 0.1 * frac_small
    assert big.se < small.se


def test_compare_to_sim_flags_outside():
    x = np.random.default_rng(4).normal(TRUE_EFF, 0.0224, size=60)
    cmp = compare_to_sim(bootstrap_mean(x, n_boot=500, seed=4), SIM_ASSUMED_EFFICIENCY)
    assert not cmp["sim_inside_ci95"]
    assert cmp["z"] < -3
    assert math.isclose(cmp["relative_difference"], -0.111, abs_tol=0.03)


def test_drag_ci():
    rows = make_rows(5, n_sessions=4)
    est = estimate_drag(col(rows, "drag_per_s"), n_boot=500, seed=5)
    assert est.ci95[0] <= TRUE_DRAG <= est.ci95[1]
    assert not est.ci95[0] <= AIR_DRAG <= est.ci95[1]
    assert not compare_to_sim(est, AIR_DRAG)["sim_inside_ci95"]


def test_speed_model_fit_recovers_slope():
    rows = make_rows(6, n_sessions=5)
    fit = speed_model_fit(
        col(rows, "flywheel_ticks_per_s_before"), col(rows, "v_exit_in_s"), n_boot=300, seed=6
    )
    true_a = TRUE_EFF * TICKS_TO_IN_S / SIM_ASSUMED_EFFICIENCY
    assert abs(fit["a_origin"] - true_a) / true_a < 0.03
    assert fit["a_origin_ci95"][0] < fit["a_origin"] < fit["a_origin_ci95"][1]
    assert not fit["sim_a_inside_ci95"]
    assert abs(fit["a_over_sim"] - TRUE_EFF / SIM_ASSUMED_EFFICIENCY) < 0.03


def test_burst_index_negative_trend():
    rows = make_rows(7, n_sessions=8)
    est = by_burst_index(col(rows, "efficiency"), col(rows, "burst_index"), n_boot=300, seed=7)
    assert set(est.groups) == {"0", "1", "2"}
    assert est.extra["slope_per_index"] < 0
    assert est.groups["0"].mean > est.groups["2"].mean
    assert abs(est.extra["slope_per_index"] + 0.01) < 0.006


def test_exclude():
    rows = [
        {"result": "IN", "fit_rms_in": 0.5},
        {"result": "IN", "fit_rms_in": 3.0},
        {"result": "MISS", "fit_rms_in": 0.1},
        {"result": "LOW", "fit_rms_in": None},
        {"result": None, "fit_rms_in": 0.1},
    ]
    kept, counts = exclude(rows, min_fit_rms_in=1.0)
    assert [r["result"] for r in kept] == ["IN", "LOW"]
    assert counts == {"total": 5, "kept": 2, "bad_fit": 1, "result": 2}
    assert len(exclude(rows)[0]) == 3


def test_csv_round_trip_with_empty_fields(tmp_path: Path):
    path = tmp_path / "m.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerow(
            {
                "measurement_id": "a1",
                "video_file": "v.mp4",
                "shot_index": "2",
                "burst_index": "1",
                "v_exit_in_s": "123.5",
                "efficiency": "0.41",
                "result": "IN",
            }
        )
        w.writerow({"measurement_id": "a2", "video_file": "v.mp4"})
    rows = read_measurements_csv(path)
    assert len(rows) == 2
    assert rows[0]["v_exit_in_s"] == 123.5
    assert rows[0]["shot_index"] == 2 and isinstance(rows[0]["shot_index"], int)
    assert rows[0]["notes"] is None
    assert rows[1]["efficiency"] is None and rows[1]["result"] is None
