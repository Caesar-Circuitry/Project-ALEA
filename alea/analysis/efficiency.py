"""Flywheel efficiency and air-drag estimation from video-measured shots (Phase 3).

Efficiency is ``v_exit_in_s / wheel_surface_speed_in_s``. The sim assumes 0.45, the last factor
of ``alea.game.TICKS_TO_IN_S``. Every estimator here returns an :class:`EfficiencyEstimate`
with an honest uncertainty, so the comparison with the sim is a z-score and a CI, not a guess.
Only numpy is used.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from alea.game.biobuzz import AIR_DRAG, TICKS_TO_IN_S

# placeholder: last factor of alea.game.TICKS_TO_IN_S; export from alea.game via a
# physics-reviewed PR
SIM_ASSUMED_EFFICIENCY = 0.45

Z95 = 1.959963984540054
DEFAULT_RESULTS_KEEP = ("IN", "LOW", "HIGH", "SHORT")

CSV_COLUMNS = [
    "measurement_id",
    "source",
    "video_file",
    "shot_index",
    "burst_index",
    "burst_size",
    "t_video_s",
    "t_log_s",
    "launch_id",
    "v_exit_in_s",
    "angle_deg",
    "apex_in",
    "drag_per_s",
    "fit_rms_in",
    "result",
    "flywheel_ticks_per_s_before",
    "flywheel_ticks_per_s_after",
    "dip_ticks_per_s",
    "wheel_surface_speed_in_s",
    "efficiency",
    "notes",
]
_INT_COLUMNS = {"shot_index", "burst_index", "burst_size"}
_STR_COLUMNS = {"measurement_id", "source", "video_file", "launch_id", "result", "notes"}

Row = dict[str, Any]


@dataclass
class EfficiencyEstimate:
    """A mean with uncertainty. ``sd`` is between-shot, ``se`` the error of the mean."""

    n: int
    mean: float
    sd: float
    se: float
    ci95: tuple[float, float]
    method: str
    groups: dict[str, EfficiencyEstimate] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ci95"] = [float(self.ci95[0]), float(self.ci95[1])]
        return d


# ---------------------------------------------------------------- reading and filtering


def read_measurements_csv(path: Path | str) -> list[dict[str, Any]]:
    """Read the importer's measurements CSV. Empty strings become None, numbers become floats.

    This duplicates the importer's reader (written in parallel); unify the two at merge.
    """
    rows: list[Row] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            row: Row = {}
            for key, text in raw.items():
                if key is None:
                    continue
                text = (text or "").strip()
                if text == "":
                    row[key] = None
                elif key in _STR_COLUMNS:
                    row[key] = text
                elif key in _INT_COLUMNS:
                    row[key] = int(float(text))
                else:
                    try:
                        row[key] = float(text)
                    except ValueError:
                        row[key] = None
            rows.append(row)
    return rows


def exclude(
    rows: Iterable[Row],
    min_fit_rms_in: float | None = None,
    results_keep: Sequence[str] = DEFAULT_RESULTS_KEEP,
) -> tuple[list[Row], dict[str, int]]:
    """Drop poor fits and unwanted results. ``min_fit_rms_in`` is the largest RMS that is kept.

    Rows without a result tag are dropped; rows without an RMS pass the RMS test.
    Returns ``(kept, counts)`` where counts has ``total``, ``kept``, ``bad_fit`` and ``result``.
    """
    kept: list[Row] = []
    counts = {"total": 0, "kept": 0, "bad_fit": 0, "result": 0}
    keep_set = set(results_keep)
    for row in rows:
        counts["total"] += 1
        if row.get("result") not in keep_set:
            counts["result"] += 1
            continue
        rms = row.get("fit_rms_in")
        if min_fit_rms_in is not None and rms is not None and rms > min_fit_rms_in:
            counts["bad_fit"] += 1
            continue
        kept.append(row)
    counts["kept"] = len(kept)
    return kept, counts


def column(rows: Iterable[Row], key: str) -> np.ndarray:
    """Finite float values of ``key``, skipping missing entries."""
    vals = [r[key] for r in rows if r.get(key) is not None]
    arr = np.asarray(vals, dtype=float)
    return arr[np.isfinite(arr)]


# ---------------------------------------------------------------- estimators


def _empty(method: str) -> EfficiencyEstimate:
    nan = float("nan")
    return EfficiencyEstimate(0, nan, nan, nan, (nan, nan), method)


def _ci(mean: float, sd: float) -> tuple[float, float]:
    return (mean - Z95 * sd, mean + Z95 * sd)


def bootstrap_mean(
    values: Sequence[float] | np.ndarray, n_boot: int = 2000, seed: int = 0
) -> EfficiencyEstimate:
    """Mean with a percentile bootstrap 95 % CI (resampling shots)."""
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return _empty("bootstrap")
    rng = np.random.default_rng(seed)
    sd = float(x.std(ddof=1)) if x.size > 1 else float("nan")
    idx = rng.integers(0, x.size, size=(n_boot, x.size))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return EfficiencyEstimate(
        n=int(x.size),
        mean=float(x.mean()),
        sd=sd,
        se=float(means.std(ddof=1)),
        ci95=(float(lo), float(hi)),
        method="bootstrap",
    )


def bayes_normal(
    values: Sequence[float] | np.ndarray,
    prior_mean: float = SIM_ASSUMED_EFFICIENCY,
    prior_sd: float = 0.1,
    seed: int = 0,
) -> EfficiencyEstimate:
    """Normal-normal conjugate posterior for the mean (the simple model).

    Assumes shots are iid normal with known variance equal to the sample variance, and a normal
    prior on the mean. It ignores session clustering, so for clustered data it is overconfident;
    use :func:`hierarchical_by_group` for that. With fewer than two values the prior sd is used
    as the data sd. ``seed`` is accepted for a uniform signature; the result is analytic.
    """
    del seed
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    n = int(x.size)
    if n == 0:
        return EfficiencyEstimate(
            0, prior_mean, prior_sd, prior_sd, _ci(prior_mean, prior_sd), "bayes_normal"
        )
    s = float(x.std(ddof=1)) if n > 1 else prior_sd
    s = max(s, 1e-12)
    prec = 1.0 / prior_sd**2 + n / s**2
    post_var = 1.0 / prec
    post_mean = post_var * (prior_mean / prior_sd**2 + float(x.sum()) / s**2)
    post_sd = math.sqrt(post_var)
    return EfficiencyEstimate(
        n=n,
        mean=post_mean,
        sd=s,
        se=post_sd,
        ci95=_ci(post_mean, post_sd),
        method="bayes_normal",
        extra={"prior_mean": prior_mean, "prior_sd": prior_sd, "sample_mean": float(x.mean())},
    )


def hierarchical_by_group(
    values: Sequence[float] | np.ndarray,
    groups: Sequence[str],
    n_boot: int = 2000,
    seed: int = 0,
) -> EfficiencyEstimate:
    """Per-group (session) means plus a pooled estimate that respects clustering.

    The pooled mean is the mean of group means. Its CI comes from a two-level bootstrap
    (resample groups, then shots within each chosen group). ``sd`` is the between-group sd of
    group means; ``extra`` holds ``between_group_sd`` and ``within_group_sd`` (pooled).
    """
    x = np.asarray(values, dtype=float)
    g = np.asarray([str(k) for k in groups])
    ok = np.isfinite(x)
    x, g = x[ok], g[ok]
    if x.size == 0:
        return _empty("hierarchical_bootstrap")
    names = sorted(set(g.tolist()))
    data = [x[g == k] for k in names]
    per = {
        k: bootstrap_mean(d, n_boot=n_boot, seed=seed + i + 1)
        for i, (k, d) in enumerate(zip(names, data, strict=True))
    }
    gmeans = np.array([d.mean() for d in data])
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(data), size=len(data))
        boots[b] = np.mean([rng.choice(data[j], size=data[j].size).mean() for j in pick])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    between = float(gmeans.std(ddof=1)) if len(data) > 1 else float("nan")
    dof = sum(d.size - 1 for d in data)
    within = (
        math.sqrt(sum(float(((d - d.mean()) ** 2).sum()) for d in data) / dof)
        if dof > 0
        else float("nan")
    )
    return EfficiencyEstimate(
        n=int(x.size),
        mean=float(gmeans.mean()),
        sd=between,
        se=float(boots.std(ddof=1)),
        ci95=(float(lo), float(hi)),
        method="hierarchical_bootstrap",
        groups=per,
        extra={"n_groups": len(data), "between_group_sd": between, "within_group_sd": within},
    )


def by_burst_index(
    values: Sequence[float] | np.ndarray,
    burst_index: Sequence[int] | np.ndarray,
    n_boot: int = 2000,
    seed: int = 0,
) -> EfficiencyEstimate:
    """Mean efficiency per position in a burst, plus a linear slope per index in ``extra``.

    A negative ``slope_per_index`` means later balls in a burst are slower.
    """
    x = np.asarray(values, dtype=float)
    k = np.asarray(burst_index, dtype=float)
    ok = np.isfinite(x) & np.isfinite(k)
    x, k = x[ok], k[ok]
    if x.size == 0:
        return _empty("by_burst_index")
    out = bootstrap_mean(x, n_boot=n_boot, seed=seed)
    out.method = "by_burst_index"
    for i, idx in enumerate(sorted({int(v) for v in k})):
        out.groups[str(idx)] = bootstrap_mean(x[k == idx], n_boot=n_boot, seed=seed + i + 1)
    slope = float("nan")
    slope_ci = (float("nan"), float("nan"))
    if np.unique(k).size > 1:
        slope = float(np.polyfit(k, x, 1)[0])
        rng = np.random.default_rng(seed)
        sl = []
        for _ in range(n_boot):
            j = rng.integers(0, x.size, size=x.size)
            if np.unique(k[j]).size > 1:
                sl.append(np.polyfit(k[j], x[j], 1)[0])
        if sl:
            slope_ci = (float(np.percentile(sl, 2.5)), float(np.percentile(sl, 97.5)))
    out.extra = {"slope_per_index": slope, "slope_ci95": list(slope_ci)}
    return out


def estimate_drag(
    drag_per_s_values: Sequence[float] | np.ndarray, n_boot: int = 2000, seed: int = 0
) -> EfficiencyEstimate:
    """Bootstrap estimate of the fitted linear drag k (1/s)."""
    est = bootstrap_mean(drag_per_s_values, n_boot=n_boot, seed=seed)
    est.method = "bootstrap_drag"
    return est


def compare_to_sim(est: EfficiencyEstimate, sim_value: float) -> dict[str, Any]:
    """Compare an estimate to the sim constant: z-score, CI membership, relative difference."""
    z = (est.mean - sim_value) / est.se if est.se and est.se > 0 else float("nan")
    inside = bool(est.ci95[0] <= sim_value <= est.ci95[1])
    rel = (est.mean - sim_value) / sim_value if sim_value else float("nan")
    return {
        "sim_value": float(sim_value),
        "estimate": float(est.mean),
        "z": float(z),
        "sim_inside_ci95": inside,
        "relative_difference": float(rel),
    }


def speed_model_fit(
    ticks_before: Sequence[float] | np.ndarray,
    v_exit: Sequence[float] | np.ndarray,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, Any]:
    """Least squares ``v = a * ticks`` (through the origin) and ``v = a * ticks + b``.

    ``a`` is in in/s per tick/s. The sim's value is ``TICKS_TO_IN_S``, which equals
    ``wheel_circumference/28 * 0.45``, so comparing ``a`` to it is the same test as efficiency
    against 0.45: ``a / TICKS_TO_IN_S`` is the efficiency relative to the sim (ratio 1 = agree).
    The CI on ``a`` is a pairs bootstrap.
    """
    t = np.asarray(ticks_before, dtype=float)
    v = np.asarray(v_exit, dtype=float)
    ok = np.isfinite(t) & np.isfinite(v)
    t, v = t[ok], v[ok]
    n = int(t.size)
    nan = float("nan")
    if n < 2:
        return {"n": n, "a_origin": nan, "a_origin_ci95": [nan, nan], "sim_a": TICKS_TO_IN_S}

    def fit_origin(tt: np.ndarray, vv: np.ndarray) -> float:
        return float(np.linalg.lstsq(tt[:, None], vv, rcond=None)[0][0])

    a0 = fit_origin(t, v)
    coef = np.linalg.lstsq(np.column_stack([t, np.ones(n)]), v, rcond=None)[0]
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        j = rng.integers(0, n, size=n)
        boots[b] = fit_origin(t[j], v[j])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    resid = v - a0 * t
    return {
        "n": n,
        "a_origin": a0,
        "a_origin_ci95": [float(lo), float(hi)],
        "a_origin_se": float(boots.std(ddof=1)),
        "a_intercept": float(coef[0]),
        "intercept_in_s": float(coef[1]),
        "rms_resid_in_s": float(math.sqrt(float((resid**2).mean()))),
        "sim_a": TICKS_TO_IN_S,
        "a_over_sim": a0 / TICKS_TO_IN_S,
        "sim_a_inside_ci95": bool(lo <= TICKS_TO_IN_S <= hi),
    }


__all__ = [
    "AIR_DRAG",
    "SIM_ASSUMED_EFFICIENCY",
    "EfficiencyEstimate",
    "bayes_normal",
    "bootstrap_mean",
    "by_burst_index",
    "column",
    "compare_to_sim",
    "estimate_drag",
    "exclude",
    "hierarchical_by_group",
    "read_measurements_csv",
    "speed_model_fit",
]
