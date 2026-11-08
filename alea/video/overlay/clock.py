"""Match clock series, monotone countdown runs, robust line fit and edge refinement.

The overlay clock counts 2:30 -> 0:00 once per match. A *run* is a maximal sequence of readings
that never increases (holds at 2:30 before the start and at 0:00 after the end are allowed, as
are gaps and the odd misread). For each run ``t_video = a - clock_s`` (slope fixed at -1 because
the clock runs in real time) is fitted for the intercept ``a`` by iteratively reweighted
(Huber) least squares. If the clock holds at 2:00 during the AUTO -> TELEOP transition, the AUTO
and TELEOP parts get separate intercepts.

UNVERIFIED on real footage (needs the user's local clip):
  * whether the displayed clock excludes the 8 s transition (hold, jump or continuous), and
  * the rounding: this module assumes ``displayed = ceil(seconds remaining)``, i.e. the value
    changes from k+1 to k exactly k seconds before the end (``DISPLAY_OFFSET_S = 0.5`` is the
    mean bias of a sample under that assumption; -0.5 would be a floor display).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, NamedTuple

import numpy as np

from alea.video.frames import VideoReader
from alea.video.overlay.glyphs import GlyphSet
from alea.video.overlay.locate import find_overlay, read_roi_number
from alea.video.overlay.profile import OverlayProfile

CLOCK_START_S = 150
AUTO_END_CLOCK_S = 120
DISPLAY_OFFSET_S = 0.5  # mean of (t + clock_s) minus the true end time, for a ceil display
ASSUMED_TRANSITION_S = 8.0  # only used to complete a run that lacks AUTO or TELEOP samples
MIN_CONFIDENCE = 0.15

_CLOCK_RE = re.compile(r"^(\d):([0-5]\d)$")


class ClockSample(NamedTuple):
    frame: int
    t_pts_s: float
    clock_s: int | None
    confidence: float


def parse_clock(text: str) -> int | None:
    """``"2:30"`` -> 150; anything else (or a value above 2:30) -> ``None``."""
    m = _CLOCK_RE.match(text)
    if not m:
        return None
    value = int(m.group(1)) * 60 + int(m.group(2))
    return value if value <= CLOCK_START_S else None


def read_clock_frame(
    image_bgr: np.ndarray,
    profile: OverlayProfile,
    glyphs: GlyphSet,
    min_confidence: float = MIN_CONFIDENCE,
) -> tuple[int | None, float]:
    """Clock seconds and confidence in one frame; ``(None, 0)`` if no overlay or no clean read."""
    fix = None
    if profile.anchor is not None:
        fix = find_overlay(image_bgr, profile)
        if fix is None:
            return None, 0.0
    text, conf = read_roi_number(image_bgr, profile, glyphs, "clock", anchor=fix)
    value = parse_clock(text)
    if value is None or conf < min_confidence:
        return None, conf
    return value, conf


def read_clock_series(
    reader: VideoReader,
    profile: OverlayProfile,
    glyphs: GlyphSet,
    step_frames: int,
    start_frame: int = 0,
    stop_frame: int | None = None,
    min_confidence: float = MIN_CONFIDENCE,
) -> list[ClockSample]:
    """Read the clock every ``step_frames`` frames: ``(frame, t_pts_s, clock_s | None, conf)``."""
    if step_frames < 1:
        raise ValueError("step_frames must be >= 1")
    stop = reader.frame_count if stop_frame is None else min(stop_frame, reader.frame_count)
    out: list[ClockSample] = []
    for i in range(start_frame, stop, step_frames):
        frame = reader.read(i)
        clock, conf = read_clock_frame(frame.image_bgr, profile, glyphs, min_confidence)
        out.append(ClockSample(i, frame.t_pts_s, clock, conf))
    return out


@dataclass(frozen=True)
class ClockRun:
    """One countdown found in a series, with its robust-fit boundaries."""

    first_pts_s: float  # first reading in the run (includes the 2:30 hold)
    last_pts_s: float
    hold_start_pts_s: float | None  # first reading at 2:30, if the run began with a hold
    hold_end_pts_s: float | None  # last reading at 0:00, if the run ended with a hold
    play_start_pts_s: float  # the clock leaves 2:30
    play_end_pts_s: float  # the clock reaches 0:00
    transition_start_pts_s: float | None  # clock reaches 2:00 and holds (None: no hold seen)
    transition_end_pts_s: float | None
    fit_rms_s: float
    n_samples: int  # countdown readings used (0 < clock < 150)
    clock_max_s: int
    clock_min_s: int
    partial: bool
    flags: tuple[str, ...] = ()


def huber_location(values: np.ndarray, k: float = 1.345, n_iter: int = 20) -> tuple[float, float]:
    """Robust location (Huber IRLS from the median) and the rms residual of all points."""
    v = np.asarray(values, dtype=float)
    mu = float(np.median(v))
    scale = max(1.4826 * float(np.median(np.abs(v - mu))), 0.3)
    for _ in range(n_iter):
        r = v - mu
        w = np.where(np.abs(r) <= k * scale, 1.0, k * scale / np.maximum(np.abs(r), 1e-12))
        new = float(np.sum(w * v) / np.sum(w))
        if abs(new - mu) < 1e-6:
            mu = new
            break
        mu = new
    return mu, float(np.sqrt(np.mean((v - mu) ** 2)))


def _a_est(run: list[ClockSample]) -> tuple[float, float, float] | None:
    """Reference intercept and the accepted window (lo, hi) offsets for the next reading."""
    cd = [s for s in run if s.clock_s is not None and 0 < s.clock_s < CLOCK_START_S]
    if cd:
        u = [s.t_pts_s + (s.clock_s or 0) for s in cd[-15:]]
        return float(np.median(u)), -3.0, 12.0
    holds = [s for s in run if s.clock_s == CLOCK_START_S]
    if holds:
        return holds[-1].t_pts_s + CLOCK_START_S, -3.0, 15.0
    return None


def _joins(run: list[ClockSample], s: ClockSample) -> bool:
    last = run[-1]
    if s.clock_s is None or last.clock_s is None:
        return False
    if s.clock_s > last.clock_s:
        return False
    ref = _a_est(run)
    if s.clock_s == CLOCK_START_S:
        return True
    if s.clock_s == 0:
        return ref is None or s.t_pts_s >= ref[0] + ref[1]
    if ref is None:
        return True
    a, lo, hi = ref
    return a + lo <= s.t_pts_s + s.clock_s <= a + hi


def _split_runs(valid: list[ClockSample], lookahead: int = 2) -> list[list[ClockSample]]:
    runs: list[list[ClockSample]] = []
    cur: list[ClockSample] = []
    for i, s in enumerate(valid):
        if not cur:
            cur = [s]
        elif _joins(cur, s):
            cur.append(s)
        elif any(_joins(cur, y) for y in valid[i + 1 : i + 1 + lookahead]):
            continue  # isolated misread
        else:
            runs.append(cur)
            cur = [s]
    if cur:
        runs.append(cur)
    return runs


def _fit_run(
    run: list[ClockSample],
    min_samples: int,
    min_span_s: float,
    display_offset_s: float,
    hold_min_s: float,
) -> ClockRun | None:
    cd = [s for s in run if s.clock_s is not None and 0 < s.clock_s < CLOCK_START_S]
    if len(cd) < min_samples:
        return None
    clocks = [s.clock_s for s in cd if s.clock_s is not None]
    if max(clocks) - min(clocks) < min_span_s:
        return None
    flags: list[str] = []
    u_of = lambda ss: np.array([s.t_pts_s + (s.clock_s or 0) for s in ss])  # noqa: E731
    holds120 = [s for s in cd if s.clock_s == AUTO_END_CLOCK_S]
    hold_seen = len(holds120) >= 2 and holds120[-1].t_pts_s - holds120[0].t_pts_s >= hold_min_s
    auto = [s for s in cd if (s.clock_s or 0) > AUTO_END_CLOCK_S]
    teleop = [s for s in cd if (s.clock_s or 0) < AUTO_END_CLOCK_S]
    common = [] if hold_seen else holds120
    a1 = a2 = None
    if len(auto) + len(common) >= 3:
        a1, _ = huber_location(u_of(auto + common))
    if len(teleop) + len(common) >= 3:
        a2, _ = huber_location(u_of(teleop + common))
    piecewise = a1 is not None and a2 is not None and abs(a2 - a1) >= 2.0
    off = display_offset_s
    trans: tuple[float, float] | None = None
    if piecewise and a1 is not None and a2 is not None:
        end_auto, end_tele = a1 - off, a2 - off
        start = end_auto - CLOCK_START_S
        end = end_tele
        trans = (end_auto - AUTO_END_CLOCK_S, end_tele - AUTO_END_CLOCK_S)
        res = np.concatenate([u_of(auto + common) - a1, u_of(teleop + common) - a2])
        rms = float(np.sqrt(np.mean(res**2)))
        flags.append("piecewise_transition")
    else:
        a_all, rms = huber_location(u_of(auto + teleop + holds120))
        partial = not auto or not teleop
        if partial and a1 is None and a2 is not None:
            # TELEOP only: the AUTO part (and the transition) is unseen
            start = a2 - off - CLOCK_START_S - ASSUMED_TRANSITION_S
            end = a2 - off
            flags.append("auto_missing_start_assumes_8s_transition")
        elif partial and a2 is None and a1 is not None:
            start = a1 - off - CLOCK_START_S
            end = a1 - off + ASSUMED_TRANSITION_S
            flags.append("teleop_missing_end_assumes_8s_transition")
        else:
            start = a_all - off - CLOCK_START_S
            end = a_all - off
            if hold_seen:
                flags.append("hold_without_fit")
    holds150 = [s for s in run if s.clock_s == CLOCK_START_S]
    holds0 = [s for s in run if s.clock_s == 0]
    partial_run = (
        max(clocks) < CLOCK_START_S - 15 or min(clocks) > 15 or "missing" in "".join(flags)
    )
    if max(clocks) < CLOCK_START_S - 15:
        flags.append("starts_mid_match")
    if min(clocks) > 15:
        flags.append("ends_mid_match")
    return ClockRun(
        first_pts_s=run[0].t_pts_s,
        last_pts_s=run[-1].t_pts_s,
        hold_start_pts_s=holds150[0].t_pts_s if holds150 else None,
        hold_end_pts_s=holds0[-1].t_pts_s if holds0 else None,
        play_start_pts_s=float(start),
        play_end_pts_s=float(end),
        transition_start_pts_s=trans[0] if trans else None,
        transition_end_pts_s=trans[1] if trans else None,
        fit_rms_s=rms,
        n_samples=len(cd),
        clock_max_s=max(clocks),
        clock_min_s=min(clocks),
        partial=partial_run,
        flags=tuple(flags),
    )


def extract_runs(
    series: list[ClockSample],
    min_samples: int = 8,
    min_span_s: float = 45.0,
    display_offset_s: float = DISPLAY_OFFSET_S,
    hold_min_s: float = 3.0,
) -> list[ClockRun]:
    """Countdown runs in time order, each with robust boundaries; junk runs are dropped."""
    valid = [s for s in sorted(series, key=lambda s: s.t_pts_s) if s.clock_s is not None]
    runs: list[ClockRun] = []
    for chunk in _split_runs(valid):
        fitted = _fit_run(chunk, min_samples, min_span_s, display_offset_s, hold_min_s)
        if fitted is not None:
            runs.append(fitted)
    return runs


def _clock_at_frame(
    reader: VideoReader, profile: OverlayProfile, glyphs: GlyphSet, index: int
) -> int | None:
    for j in range(index, min(index + 3, reader.frame_count)):
        value, _ = read_clock_frame(reader.read(j).image_bgr, profile, glyphs)
        if value is not None:
            return value
    return None


def refine_edge(
    reader: VideoReader,
    profile: OverlayProfile,
    glyphs: GlyphSet,
    t_guess_pts_s: float,
    clock_at_or_below_s: int,
    window_s: float = 3.0,
) -> float | None:
    """Presentation time of the first frame whose clock reads ``<= clock_at_or_below_s``.

    Bisects at the native frame rate inside ``t_guess +- window_s``; ``None`` when the window
    does not bracket the change (already below at its start, or not yet below at its end).
    """
    ts = reader.timestamps_s()
    lo = reader.frame_at_time(t_guess_pts_s - window_s)
    hi = reader.frame_at_time(t_guess_pts_s + window_s)

    def below(i: int) -> bool | None:
        v = _clock_at_frame(reader, profile, glyphs, i)
        return None if v is None else v <= clock_at_or_below_s

    if below(lo) is True or below(hi) is not True:
        return None
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if below(mid):
            hi = mid
        else:
            lo = mid
    return ts[hi]


def refine_run(
    reader: VideoReader,
    profile: OverlayProfile,
    glyphs: GlyphSet,
    run: ClockRun,
    window_s: float = 3.0,
    display_offset_s: float = DISPLAY_OFFSET_S,
) -> ClockRun:
    """Replace the fitted start/end by frame-exact values where the window brackets them.

    Under the ceil display the clock first reads 2:29 exactly 149 s before the end, so
    ``start = t(first 2:29 frame) - 1`` and ``end = t(first 0:00 frame)`` (shifted by
    ``0.5 - display_offset_s`` for another rounding convention)."""
    shift = 0.5 - display_offset_s
    new_start, new_end = run.play_start_pts_s, run.play_end_pts_s
    flags = list(run.flags)
    t149 = refine_edge(
        reader, profile, glyphs, run.play_start_pts_s + 1.0, CLOCK_START_S - 1, window_s
    )
    if t149 is not None and "auto_missing_start_assumes_8s_transition" not in run.flags:
        new_start = t149 + (CLOCK_START_S - 1) + shift - CLOCK_START_S
        flags.append("start_refined")
    t0 = refine_edge(reader, profile, glyphs, run.play_end_pts_s, 0, window_s)
    if t0 is not None and "teleop_missing_end_assumes_8s_transition" not in run.flags:
        new_end = t0 + shift
        flags.append("end_refined")
    trans_s, trans_e = run.transition_start_pts_s, run.transition_end_pts_s
    if trans_s is not None and trans_e is not None:
        trans_s = new_start + (CLOCK_START_S - AUTO_END_CLOCK_S)
        trans_e = new_end - AUTO_END_CLOCK_S
    return replace(
        run,
        play_start_pts_s=new_start,
        play_end_pts_s=new_end,
        transition_start_pts_s=trans_s,
        transition_end_pts_s=trans_e,
        flags=tuple(flags),
    )


def runs_to_segments(
    runs: list[ClockRun],
    pad_end_s: float = 10.0,
    pre_roll_cap_s: float = 60.0,
    labels: list[str | None] | None = None,
) -> list[dict[str, Any]]:
    """Segment dicts in the match-segment schema v1 shape (plan section 4.2).

    Consumed by ``alea.video.segment`` on its branch (typed schema, schedule join). Teams,
    score and label are filled by later steps; times are presentation times of the file.
    """
    segs: list[dict[str, Any]] = []
    for n, run in enumerate(runs):
        first = run.hold_start_pts_s if run.hold_start_pts_s is not None else run.first_pts_s
        start = max(first, run.play_start_pts_s - pre_roll_cap_s)
        conf = (
            min(1.0, run.n_samples / 30.0)
            * max(0.0, 1.0 - run.fit_rms_s / 1.5)
            * (0.6 if run.partial else 1.0)
        )
        needs_review = run.partial or run.fit_rms_s > 1.0 or conf < 0.7
        segs.append(
            {
                "segment_id": f"clock-{n:03d}",
                "match_label": labels[n] if labels and n < len(labels) else None,
                "match_label_raw": None,
                "start_pts_s": round(start, 3),
                "play_start_pts_s": round(run.play_start_pts_s, 3),
                "play_end_pts_s": round(run.play_end_pts_s, 3),
                "end_pts_s": round(run.play_end_pts_s + pad_end_s, 3),
                "teams": {"red": [], "blue": []},
                "score": {"red_final": None, "blue_final": None},
                "confidence": round(conf, 3),
                "needs_review": bool(needs_review),
                "evidence": {
                    "clock": {
                        "present": True,
                        "fit_rms_s": round(run.fit_rms_s, 3),
                        "n_samples": run.n_samples,
                        "start_pts_s": round(run.play_start_pts_s, 3),
                        "end_pts_s": round(run.play_end_pts_s, 3),
                        "transition_start_pts_s": _r(run.transition_start_pts_s),
                        "transition_end_pts_s": _r(run.transition_end_pts_s),
                        "partial": run.partial,
                        "flags": list(run.flags),
                    }
                },
            }
        )
    return segs


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 3)
