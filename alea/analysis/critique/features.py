"""Driver-critique features from `MatchSignals`. Every numeric field name carries its unit."""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from alea.analysis.critique.signals import MatchSignals

# Match timing, placeholders: Competition Manual section 10, move to alea/game via a
# physics-reviewed PR. Log time 0 is assumed to be the match start.
AUTO_S = 30.0  # placeholder (see above)
TRANSITION_S = 8.0  # placeholder (see above)
TELEOP_S = 120.0  # placeholder (see above)
ENDGAME_S = 30.0  # placeholder (see above)
MATCH_END_S = AUTO_S + TRANSITION_S + TELEOP_S

BURST_GAP_S = 1.0
IDLE_THRESHOLD_S = 8.0
DRIVE_IDLE_TICKS_PER_SEC = 50.0
SHORTFALL_LIMIT_FRACTION = 0.05
SETPOINT_CHANGE_TICKS_PER_SEC = 50.0
SPINUP_TOLERANCE_FRACTION = 0.02
HIST_LOWER_EDGES_S = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 15.0, 30.0]  # last bin is open


def phase_of(t_s: float) -> str:
    """'auto', 'teleop' (transition included) or 'endgame' for a log time."""
    if t_s < AUTO_S:
        return "auto"
    if t_s < MATCH_END_S - ENDGAME_S:
        return "teleop"
    return "endgame"


@dataclass
class CritiqueFeatures:
    duration_s: float = 0.0
    # cycles and bursts
    launch_count: int = 0
    launches_per_min: float | None = None
    launch_auto_count: int = 0
    launch_teleop_count: int = 0
    launch_endgame_count: int = 0
    cycle_count: int = 0
    cycle_mean_s: float | None = None
    cycle_median_s: float | None = None
    cycle_p90_s: float | None = None
    burst_count: int = 0
    burst_size_count: list[int] = field(default_factory=list)
    burst_mean_size_count: float | None = None
    # idle gaps
    idle_threshold_s: float = IDLE_THRESHOLD_S
    idle_gaps: list[dict[str, float | None]] = field(default_factory=list)
    idle_total_s: float = 0.0
    idle_longest_s: float = 0.0
    idle_longest_start_t_s: float | None = None
    idle_drive_idle_fraction: float | None = None
    # cadence
    interval_hist_lower_edges_s: list[float] = field(
        default_factory=lambda: list(HIST_LOWER_EDGES_S)
    )
    interval_hist_count: list[int] = field(default_factory=list)
    quick_follow_fraction: float | None = None
    # flywheel readiness
    flywheel_shortfall_mean_fraction: float | None = None
    flywheel_shortfall_max_fraction: float | None = None
    flywheel_low_launch_fraction: float | None = None
    spinup_wait_mean_s: float | None = None
    spinup_wait_count: int = 0
    # aim
    aimed_fraction: float | None = None
    in_range_fraction: float | None = None
    aimed_and_in_range_fraction: float | None = None
    heading_error_abs_mean_deg: float | None = None
    distance_mean_in: float | None = None
    distance_sd_in: float | None = None
    distance_min_in: float | None = None
    distance_max_in: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary_lines(self) -> list[str]:
        f = self
        lines = [
            f"{f.launch_count} launches in {f.duration_s:.0f} s"
            + (f" ({f.launches_per_min:.1f} per minute)." if f.launches_per_min else "."),
            f"By phase: {f.launch_auto_count} in auto, {f.launch_teleop_count} in teleop, "
            f"{f.launch_endgame_count} in endgame.",
        ]
        if f.cycle_mean_s is not None:
            lines.append(
                f"{f.burst_count} bursts (mean {f.burst_mean_size_count:.1f} launches); "
                f"cycle time mean {f.cycle_mean_s:.1f} s, median {f.cycle_median_s:.1f} s, "
                f"90th percentile {f.cycle_p90_s:.1f} s."
            )
        if f.idle_gaps:
            lines.append(
                f"{len(f.idle_gaps)} idle gaps over {f.idle_threshold_s:.0f} s, "
                f"{f.idle_total_s:.1f} s in total; longest {f.idle_longest_s:.1f} s "
                f"starting at {f.idle_longest_start_t_s:.1f} s."
            )
        else:
            lines.append(f"No gap over {f.idle_threshold_s:.0f} s without a launch.")
        if f.idle_drive_idle_fraction is not None:
            lines.append(
                f"The drive was standing still for {100 * f.idle_drive_idle_fraction:.0f} % "
                "of the idle time."
            )
        if f.quick_follow_fraction is not None:
            lines.append(
                f"{100 * f.quick_follow_fraction:.0f} % of launches came within "
                f"{BURST_GAP_S:.0f} s of the previous one."
            )
        if f.flywheel_shortfall_mean_fraction is not None:
            lines.append(
                f"Flywheel was on average {100 * f.flywheel_shortfall_mean_fraction:.1f} % below "
                f"setpoint at launch "
                f"(worst {100 * (f.flywheel_shortfall_max_fraction or 0):.1f} %); "
                f"{100 * (f.flywheel_low_launch_fraction or 0):.0f} % of launches fired more than "
                f"{100 * SHORTFALL_LIMIT_FRACTION:.0f} % below setpoint."
            )
        if f.spinup_wait_mean_s is not None:
            lines.append(
                f"Mean spin-up wait after a setpoint change: {f.spinup_wait_mean_s:.2f} s "
                f"({f.spinup_wait_count} changes)."
            )
        if f.aimed_fraction is not None:
            lines.append(
                f"At launch: aimed {100 * f.aimed_fraction:.0f} %, in range "
                f"{100 * (f.in_range_fraction or 0):.0f} %, both "
                f"{100 * (f.aimed_and_in_range_fraction or 0):.0f} %; mean heading error "
                f"{f.heading_error_abs_mean_deg:.1f} deg."
            )
        if f.distance_mean_in is not None:
            lines.append(
                f"Launch distance mean {f.distance_mean_in:.1f} in (sd {f.distance_sd_in:.1f}, "
                f"min {f.distance_min_in:.1f}, max {f.distance_max_in:.1f})."
            )
        return lines


def _at(t_ref: np.ndarray, values: np.ndarray, t_s: np.ndarray) -> np.ndarray:
    """Last value at or before each launch time (first sample if before the start)."""
    idx = np.clip(np.searchsorted(t_ref, t_s, side="right") - 1, 0, len(t_ref) - 1)
    return values[idx]


def _spinup_waits_s(sig: MatchSignals) -> list[float]:
    """Time from each setpoint change (> 50 ticks/s) until the flywheel is within 2 % of it."""
    t, lut = sig.t_s, sig.lut_ticks_per_sec
    ft, fv = sig.flywheel_t_s, sig.flywheel_ticks_per_sec
    if len(t) == 0 or len(ft) == 0:
        return []
    ok = np.isfinite(lut)
    t, lut = t[ok], lut[ok]
    if len(t) == 0:
        return []
    events = [0]
    ref = lut[0]
    for i in range(1, len(t)):
        if abs(lut[i] - ref) > SETPOINT_CHANGE_TICKS_PER_SEC:
            events.append(i)
            ref = lut[i]
    events = events[1:]
    waits: list[float] = []
    for n, i in enumerate(events):
        end_t = t[events[n + 1]] if n + 1 < len(events) else t[-1] + 1e-9
        sel = (ft >= t[i]) & (ft <= end_t)
        if not sel.any():
            continue
        set_pts = _at(t, lut, ft[sel])
        within = np.abs(fv[sel] - set_pts) <= SPINUP_TOLERANCE_FRACTION * set_pts
        if within.any():
            waits.append(float(ft[sel][int(np.argmax(within))] - t[i]))
    return waits


def compute_features(
    sig: MatchSignals, idle_threshold_s: float = IDLE_THRESHOLD_S
) -> CritiqueFeatures:
    launches = np.sort(sig.launch_t_s)
    n = len(launches)
    feat = CritiqueFeatures(
        duration_s=float(sig.duration_s), launch_count=n, idle_threshold_s=idle_threshold_s
    )
    feat.interval_hist_count = [0] * len(HIST_LOWER_EDGES_S)
    if sig.duration_s > 0:
        feat.launches_per_min = n / (sig.duration_s / 60.0)
    phases = [phase_of(float(x)) for x in launches]
    feat.launch_auto_count = phases.count("auto")
    feat.launch_teleop_count = phases.count("teleop")
    feat.launch_endgame_count = phases.count("endgame")

    gaps = np.diff(launches)
    cycles = gaps[gaps >= BURST_GAP_S]
    if len(cycles):
        feat.cycle_count = len(cycles)
        feat.cycle_mean_s = float(np.mean(cycles))
        feat.cycle_median_s = float(np.median(cycles))
        feat.cycle_p90_s = float(np.percentile(cycles, 90))
    if n:
        sizes = [1]
        for g in gaps:
            if g < BURST_GAP_S:
                sizes[-1] += 1
            else:
                sizes.append(1)
        feat.burst_count = len(sizes)
        feat.burst_size_count = sizes
        feat.burst_mean_size_count = float(np.mean(sizes))
    if len(gaps):
        bins = np.searchsorted(HIST_LOWER_EDGES_S, gaps, side="right") - 1
        for b in bins:
            feat.interval_hist_count[int(max(b, 0))] += 1
        feat.quick_follow_fraction = float(np.mean(gaps < BURST_GAP_S))

    # idle gaps: match start and end act as bounding events
    bounds = np.concatenate([[0.0], launches, [max(sig.duration_s, launches[-1] if n else 0.0)]])
    drive_idle_n = drive_n = 0
    for a, b in itertools.pairwise(bounds):
        if b - a <= idle_threshold_s:
            continue
        frac: float | None = None
        if len(sig.drive_t_s):
            sel = (sig.drive_t_s >= a) & (sig.drive_t_s < b)
            if sel.any():
                low = np.abs(sig.drive_ticks_per_sec[sel]) < DRIVE_IDLE_TICKS_PER_SEC
                frac = float(np.mean(low))
                drive_idle_n += int(low.sum())
                drive_n += int(sel.sum())
        feat.idle_gaps.append(
            {
                "start_t_s": float(a),
                "end_t_s": float(b),
                "duration_s": float(b - a),
                "drive_idle_fraction": frac,
            }
        )
    if feat.idle_gaps:
        durs = [g["duration_s"] or 0.0 for g in feat.idle_gaps]
        feat.idle_total_s = float(sum(durs))
        k = int(np.argmax(durs))
        feat.idle_longest_s = durs[k]
        feat.idle_longest_start_t_s = feat.idle_gaps[k]["start_t_s"]
    if drive_n:
        feat.idle_drive_idle_fraction = drive_idle_n / drive_n

    # flywheel readiness
    if n and len(sig.t_s) and len(sig.lut_ticks_per_sec):
        set_pt = _at(sig.t_s, sig.lut_ticks_per_sec, sig.launch_t_s)
        before = sig.launch_before_ticks_per_sec
        if len(before) == n:
            valid = np.isfinite(set_pt) & (set_pt > 0)
            if valid.any():
                short = (set_pt[valid] - before[valid]) / set_pt[valid]
                feat.flywheel_shortfall_mean_fraction = float(np.mean(short))
                feat.flywheel_shortfall_max_fraction = float(np.max(short))
                feat.flywheel_low_launch_fraction = float(np.mean(short > SHORTFALL_LIMIT_FRACTION))
    waits = _spinup_waits_s(sig)
    if waits:
        feat.spinup_wait_mean_s = float(np.mean(waits))
        feat.spinup_wait_count = len(waits)

    # aim at launch
    if n and len(sig.t_s):
        aimed = _at(sig.t_s, sig.aimed, launches)
        in_range = _at(sig.t_s, sig.in_range, launches)
        feat.aimed_fraction = float(np.mean(aimed))
        feat.in_range_fraction = float(np.mean(in_range))
        feat.aimed_and_in_range_fraction = float(np.mean(aimed & in_range))
        err = _at(sig.t_s, sig.heading_error_deg, launches)
        if np.isfinite(err).any():
            feat.heading_error_abs_mean_deg = float(np.nanmean(np.abs(err)))
        dist = _at(sig.t_s, sig.distance_in, launches)
        dist = dist[np.isfinite(dist)]
        if len(dist):
            feat.distance_mean_in = float(np.mean(dist))
            feat.distance_sd_in = float(np.std(dist, ddof=1)) if len(dist) > 1 else 0.0
            feat.distance_min_in = float(np.min(dist))
            feat.distance_max_in = float(np.max(dist))
    return feat
