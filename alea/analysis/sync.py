"""Offset between video time and robot-log time.

Convention: `offset_s = t_log_s - t_video_s`, so `t_video_s + offset_s` lands on the log clock.

Decision 0007: the launch detector marks the first loop of the flywheel dip, a constant bias of
about +20 to +40 ms after the true release. A constant bias is absorbed by the offset; it does
not hurt the join (window 0.25 s) but means the offset is not the camera-to-robot clock offset.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import numpy as np

from alea.analysis.hivelab import LogLaunch, ShotMeasurement, apply_launch


def offset_from_cue(cue_video_s: float, cue_log_s: float) -> float:
    """Offset from one event seen in both clocks (clap, LED flash)."""
    return cue_log_s - cue_video_s


@dataclass
class SyncResult:
    offset_s: float
    n_pairs: int
    residual_rms_s: float
    pairs: list[tuple[int, int]] = field(default_factory=list)  # (video idx, log idx), sorted
    method: str = "burst-gap"
    ambiguous: bool = False


def _pair(video: np.ndarray, log: np.ndarray, offset_s: float, window_s: float):
    """Greedy one-to-one pairing by closeness; returns [(video idx, log idx)]."""
    shifted = video + offset_s
    cand = [
        (abs(float(shifted[i] - log[j])), i, int(j))
        for i in range(len(video))
        for j in np.nonzero(np.abs(log - shifted[i]) <= window_s)[0]
    ]
    cand.sort()
    used_v: set[int] = set()
    used_l: set[int] = set()
    out: list[tuple[int, int]] = []
    for _, i, j in cand:
        if i in used_v or j in used_l:
            continue
        used_v.add(i)
        used_l.add(j)
        out.append((i, j))
    return sorted(out)


def _score(video: np.ndarray, log: np.ndarray, offset_s: float, window_s: float):
    """(pairs within window, summed absolute error) for one candidate offset."""
    shifted = video + offset_s
    idx = np.clip(np.searchsorted(log, shifted), 1, len(log) - 1)
    err = np.minimum(np.abs(log[idx] - shifted), np.abs(log[idx - 1] - shifted))
    hit = err <= window_s
    return int(hit.sum()), float(err[hit].sum())


def match_offset(
    video_times_s: Sequence[float],
    log_times_s: Sequence[float],
    window_s: float = 0.05,
    grid_s: float = 0.001,
    search: tuple[float, float] = (-np.inf, np.inf),
) -> SyncResult:
    """Find the offset that aligns the most video shot times with log launch times.

    Candidates are every `log - video` difference inside `search` (exact; no scan needed, and
    `grid_s` only merges candidates closer than it). Each is scored by how many video times
    land within +-`window_s` of a log time; the best is refined to the median difference of its
    pairs. Tolerates a missed and a spurious shot. `ambiguous` is True when another alignment,
    more than 2*`window_s` away, scores within one pair of the best. Pair indices refer to the
    time-sorted inputs.
    """
    video = np.asarray(sorted(video_times_s), dtype=float)
    log = np.asarray(sorted(log_times_s), dtype=float)
    if len(video) == 0 or len(log) < 2:
        return SyncResult(0.0, 0, float("nan"), [], "burst-gap", True)
    diffs = (log[None, :] - video[:, None]).ravel()
    diffs = diffs[(diffs >= search[0]) & (diffs <= search[1])]
    if len(diffs) == 0:
        return SyncResult(0.0, 0, float("nan"), [], "burst-gap", True)
    diffs = np.unique(np.round(diffs / grid_s) * grid_s)
    scored = []
    for c in diffs:
        n, abs_err = _score(video, log, float(c), window_s)
        scored.append((-n, abs_err, float(c)))
    scored.sort()
    n_best, c_best = -scored[0][0], scored[0][2]
    runner_up = max((-s[0] for s in scored if abs(s[2] - c_best) > 2 * window_s), default=0)

    offset = c_best
    pairs = _pair(video, log, offset, window_s)
    for _ in range(2):  # median-refine, re-pair
        if not pairs:
            break
        offset = float(np.median([log[j] - video[i] for i, j in pairs]))
        pairs = _pair(video, log, offset, window_s)
    resid = [log[j] - (video[i] + offset) for i, j in pairs]
    rms = float(np.sqrt(np.mean(np.square(resid)))) if resid else float("nan")
    return SyncResult(
        offset_s=offset,
        n_pairs=len(pairs),
        residual_rms_s=rms,
        pairs=pairs,
        method="burst-gap",
        ambiguous=runner_up >= n_best - 1,
    )


def _note(old: str, new: str) -> str:
    return f"{old}; {new}" if old else new


def join_launches(
    measurements: Sequence[ShotMeasurement],
    launches: Sequence[LogLaunch],
    offset_s: float,
    max_dt_s: float = 0.25,
) -> list[ShotMeasurement]:
    """Attach to each measurement the nearest launch within +-`max_dt_s` of its shifted time.

    Each launch is used at most once (closest pairs win). Unmatched measurements are kept and
    get a note.
    """
    cand = sorted(
        (abs(m.t_video_s + offset_s - ln.t_s), mi, li)
        for mi, m in enumerate(measurements)
        for li, ln in enumerate(launches)
        if abs(m.t_video_s + offset_s - ln.t_s) <= max_dt_s
    )
    chosen: dict[int, int] = {}
    used: set[int] = set()
    for _, mi, li in cand:
        if mi in chosen or li in used:
            continue
        chosen[mi] = li
        used.add(li)
    out: list[ShotMeasurement] = []
    for mi, m in enumerate(measurements):
        if mi in chosen:
            out.append(apply_launch(m, launches[chosen[mi]]))
        else:
            out.append(replace(m, notes=_note(m.notes, f"no launch within {max_dt_s} s")))
    return out
