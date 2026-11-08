"""Synthetic launcher measurements, CSV I/O and summary helpers (roadmap phase 6).

CSV columns are the phase-3 contract written by ``alea/analysis/hivelab``.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import numpy as np

# placeholder: last factor of alea.game.TICKS_TO_IN_S; a physics-reviewed PR should export it
# from alea.game
SIM_ASSUMED_EFFICIENCY = 0.45

COLUMNS = [
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
_INT = {"shot_index", "burst_index", "burst_size"}
_STR = {"measurement_id", "source", "video_file", "launch_id", "result", "notes"}
_WHEEL_IN_PER_TICK = 1.0 / 28 * 2 * math.pi * 1.89  # StarterBot, 1:1 drive


def synthetic_rows(seed: int = 24331, n_shots: int = 40) -> list[dict[str, Any]]:
    """Seeded rows: ``n_shots`` shots over 3 sessions, bursts of 1-3, efficiency ~0.40."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    shot = 0
    t_s = 0.0
    while shot < n_shots:
        session = shot * 3 // n_shots
        burst_size = int(min(rng.integers(1, 4), n_shots - shot))
        for b in range(burst_size):
            ticks_before = float(rng.uniform(900, 1300))
            wheel = ticks_before * _WHEEL_IN_PER_TICK
            eff = float(rng.normal(0.40, 0.03))
            t_s += float(rng.uniform(0.4, 1.0)) if b else float(rng.uniform(4, 10))
            rows.append(
                {
                    "measurement_id": f"m{shot:03d}",
                    "source": "video",
                    "video_file": f"session{session + 1}.mp4",
                    "shot_index": shot,
                    "burst_index": b,
                    "burst_size": burst_size,
                    "t_video_s": round(t_s, 3),
                    "t_log_s": round(t_s + 0.12, 3),
                    "launch_id": f"L{shot:03d}",
                    "v_exit_in_s": eff * wheel,
                    "angle_deg": float(rng.normal(55, 2)),
                    "apex_in": float(rng.uniform(30, 60)),
                    "drag_per_s": float(rng.uniform(0.05, 0.1)),
                    "fit_rms_in": float(rng.uniform(0.2, 0.8)),
                    "result": "hit" if rng.random() < 0.6 else "miss",
                    "flywheel_ticks_per_s_before": ticks_before,
                    "flywheel_ticks_per_s_after": ticks_before - float(rng.uniform(40, 120)),
                    "dip_ticks_per_s": float(rng.uniform(40, 120)),
                    "wheel_surface_speed_in_s": wheel,
                    "efficiency": eff,
                    "notes": "",
                }
            )
            shot += 1
    return rows


def write_measurements_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    """Write rows with the contract header."""
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def read_measurements_csv(path: str | Path) -> list[dict[str, Any]]:
    """Read a measurement CSV with typed values; raise ``ValueError`` on a bad header.

    Empty numeric cells become ``nan`` (empty int cells become -1).
    """
    with Path(path).open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or list(reader.fieldnames) != COLUMNS:
            raise ValueError(f"unexpected CSV header in {path}: {reader.fieldnames}")
        out: list[dict[str, Any]] = []
        for raw in reader:
            row: dict[str, Any] = {}
            for c in COLUMNS:
                v = raw[c]
                if c in _STR:
                    row[c] = v
                elif c in _INT:
                    row[c] = int(v) if v != "" else -1
                else:
                    row[c] = float(v) if v != "" else math.nan
            out.append(row)
    return out


def column(rows: list[dict[str, Any]], name: str) -> np.ndarray:
    """Return a float array of one column, dropping NaN."""
    a = np.array([r[name] for r in rows], dtype=float)
    return a[~np.isnan(a)]


def mean_sd(values: np.ndarray) -> tuple[float, float]:
    """Mean and sample sd (0 for fewer than two values; nan for none)."""
    if values.size == 0:
        return math.nan, math.nan
    return float(values.mean()), float(values.std(ddof=1)) if values.size > 1 else 0.0


def _group(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    out = []
    for k in sorted({r[key] for r in rows}):
        sub = [r for r in rows if r[key] == k]
        m, s = mean_sd(column(sub, "efficiency"))
        out.append({key: k, "n": len(sub), "mean": m, "sd": s})
    return out


def per_session(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Efficiency n/mean/sd per ``video_file``."""
    return _group(rows, "video_file")


def per_burst_index(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Efficiency n/mean/sd per ``burst_index``."""
    return _group(rows, "burst_index")
