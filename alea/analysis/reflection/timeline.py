"""Build a match timeline from a robot log and overlay events.

Clocks: the log clock starts when logging started; match time is `log time + offset_s`.
`align_log_to_match` finds the offset (see decision 0011). Every event carries `source`:
"measured" when it comes straight from the data, "inferred" when something was filled in.
"""

from __future__ import annotations

import itertools
from bisect import bisect_left
from dataclasses import dataclass, field, replace

import numpy as np

from alea.analysis.reflection.overlay_events import (
    AUTO_END_S,
    ENDGAME_START_S,
    MATCH_TOTAL_S,
    SCORE_LAG_S,
    TRANSITION_END_S,
    OverlayEvent,
)
from alea.data.contract import canonical_key
from alea.data.launches import LaunchConfig, detect_launches
from alea.data.logdata import LogData

# placeholder: Competition Manual Table 10-2; game point values belong in alea/game via a
# physics-reviewed PR. Phases: auto 0-30 s, transition 8 s, teleop to 120 s, endgame last 30 s.
PHASE_BOUNDS_S = (
    ("auto", 0.0, AUTO_END_S),
    ("transition", AUTO_END_S, TRANSITION_END_S),
    ("teleop", TRANSITION_END_S, ENDGAME_START_S),
    ("endgame", ENDGAME_START_S, MATCH_TOTAL_S),
)
IDLE_GAP_S = 8.0  # placeholder: no launch for longer than this counts as idle
BURST_GAP_S = 1.5  # placeholder: launches closer than this belong to one burst
UNDER_SPEED_FRACTION = 0.95  # placeholder: fired below this share of the LUT setpoint
ALIGN_TOLERANCE_S = 0.6  # a launch and a score step this close (after the lag) are a pair
ALIGN_MIN_PAIRS = 2

MEASURED = "measured"
INFERRED = "inferred"


@dataclass(frozen=True)
class LaunchEvent:
    t_s: float  # match time once built into a timeline, log time before
    distance_in: float | None = None
    off_axis_deg: float | None = None
    aimed: bool | None = None
    in_range: bool | None = None
    setpoint_ticks_per_sec: float | None = None
    flywheel_before_ticks_per_sec: float | None = None
    dip_ticks_per_sec: float | None = None
    source: str = MEASURED

    @property
    def speed_fraction(self) -> float | None:
        sp, before = self.setpoint_ticks_per_sec, self.flywheel_before_ticks_per_sec
        if sp is None or before is None or sp <= 0:
            return None
        return before / sp


@dataclass(frozen=True)
class IdleGap:
    start_s: float
    length_s: float


@dataclass(frozen=True)
class TimelineEvent:
    t_s: float
    kind: str
    detail: str
    source: str


@dataclass
class MatchTimeline:
    launches: list[LaunchEvent] = field(default_factory=list)
    score_steps: list[OverlayEvent] = field(default_factory=list)  # alliance score changes
    tip_events: list[OverlayEvent] = field(default_factory=list)
    score_times_s: list[float] = field(default_factory=list)  # match time of score_steps
    tip_times_s: list[float] = field(default_factory=list)
    final_score_pts: float | None = None
    alliance: str | None = None
    offset_s: float = 0.0
    offset_source: str = INFERRED
    log_present: bool = False
    overlay_present: bool = False
    phases_source: str = INFERRED
    note: str = ""

    @property
    def phases(self) -> list[tuple[str, float, float]]:
        return list(PHASE_BOUNDS_S)

    @property
    def launch_times_s(self) -> list[float]:
        return [launch.t_s for launch in self.launches]

    @property
    def idle_gaps(self) -> list[IdleGap]:
        return idle_gaps(self.launch_times_s)

    @property
    def cycle_times_s(self) -> list[float]:
        return cycle_times(self.launch_times_s)

    @property
    def burst_sizes(self) -> list[int]:
        return burst_sizes(self.launch_times_s)

    def events(self) -> list[TimelineEvent]:
        out = [
            TimelineEvent(a, f"phase_{name}", f"{name} starts", self.phases_source)
            for name, a, _ in self.phases
        ]
        for launch in self.launches:
            parts = []
            if launch.distance_in is not None:
                parts.append(f"{launch.distance_in:.0f} in")
            if launch.aimed is not None:
                parts.append("aimed" if launch.aimed else "not aimed")
            frac = launch.speed_fraction
            if frac is not None:
                parts.append(f"{100 * frac:.0f}% of setpoint")
            out.append(
                TimelineEvent(launch.t_s, "launch", ", ".join(parts) or "launch", launch.source)
            )
        for ev, t in zip(self.score_steps, self.score_times_s, strict=True):
            out.append(
                TimelineEvent(
                    t, "score_step", f"{ev.alliance} +{ev.delta:g} to {ev.new:g}", MEASURED
                )
            )
        for ev, t in zip(self.tip_events, self.tip_times_s, strict=True):
            out.append(TimelineEvent(t, "tip", f"{ev.alliance} tip", MEASURED))
        for gap in self.idle_gaps:
            out.append(
                TimelineEvent(
                    gap.start_s,
                    "idle_gap",
                    f"{gap.length_s:.1f} s without a launch",
                    self.offset_source,
                )
            )
        return sorted(out, key=lambda e: e.t_s)


def idle_gaps(launch_times_s: list[float], threshold_s: float = IDLE_GAP_S) -> list[IdleGap]:
    ts = sorted(launch_times_s)
    return [IdleGap(a, b - a) for a, b in itertools.pairwise(ts) if b - a > threshold_s]


def cycle_times(launch_times_s: list[float], threshold_s: float = IDLE_GAP_S) -> list[float]:
    """Intervals between consecutive launches, idle gaps excluded."""
    ts = sorted(launch_times_s)
    return [b - a for a, b in itertools.pairwise(ts) if b - a <= threshold_s]


def burst_sizes(launch_times_s: list[float], gap_s: float = BURST_GAP_S) -> list[int]:
    """Sizes of runs of 2+ launches each closer than `gap_s` to the previous one."""
    ts = sorted(launch_times_s)
    sizes, run = [], 1
    for a, b in itertools.pairwise(ts):
        if b - a <= gap_s:
            run += 1
        else:
            if run > 1:
                sizes.append(run)
            run = 1
    if run > 1:
        sizes.append(run)
    return sizes


def overlay_match_times_s(events: list[OverlayEvent]) -> tuple[list[float], str]:
    """Match time of each event and its source.

    From the on-screen clock when every event has it (measured). Otherwise video time minus the
    video time of the first `auto` event (else the earliest event), which assumes that event is
    at match time 0 (inferred).
    """
    if all(e.clock_s_remaining is not None for e in events):
        return [MATCH_TOTAL_S - float(e.clock_s_remaining or 0.0) for e in events], MEASURED
    autos = [e.t_new_pts_s for e in events if e.phase == "auto"]
    origin = min(autos) if autos else min((e.t_new_pts_s for e in events), default=0.0)
    return [e.t_new_pts_s - origin for e in events], INFERRED


def align_log_to_match(
    launch_times_s: list[float], overlay_events: list[OverlayEvent]
) -> tuple[float, str]:
    """Offset such that match time = log time + offset, and its source.

    Heuristic: a ball that scores raises the alliance score `SCORE_LAG_S` after its launch. For
    every (launch, score step) pair the offset that would line them up is a candidate; the one
    that pairs the most score steps with a launch within `ALIGN_TOLERANCE_S` wins (ties: the
    smaller offset), refined by the mean residual. At least `ALIGN_MIN_PAIRS` pairs give
    "measured". With fewer, the first launch is lined up with the first score step ("inferred").
    Without score steps or launches the log is assumed to start with the match: (0.0, "inferred").
    Pass events of one alliance only.
    """
    steps = [e for e in overlay_events if e.field == "score" and e.delta > 0]
    launches = np.sort(np.asarray(launch_times_s, dtype=float))
    if not steps or launches.size == 0:
        return 0.0, INFERRED
    times, time_source = overlay_match_times_s(steps)
    ev = np.sort(np.asarray(times, dtype=float))
    best: tuple[int, float, float] | None = None  # (pairs, -|offset|, offset)
    cands = np.unique(np.round((ev[:, None] - SCORE_LAG_S - launches[None, :]).ravel(), 3))
    for c in cands:
        target = ev - SCORE_LAG_S - c  # where each step's launch would sit in log time
        near = np.abs(target[:, None] - launches[None, :]).min(axis=1)
        pairs = int((near <= ALIGN_TOLERANCE_S).sum())
        key = (pairs, -abs(float(c)), float(c))
        if best is None or key > best:
            best = key
    if best is None:
        return 0.0, INFERRED
    pairs, _, offset = best
    if pairs >= ALIGN_MIN_PAIRS:
        target = ev - SCORE_LAG_S - offset
        resid = []
        for tg in target:
            j = int(np.argmin(np.abs(launches - tg)))
            if abs(launches[j] - tg) <= ALIGN_TOLERANCE_S:
                resid.append(tg - launches[j])
        return offset - (float(np.mean(resid)) if resid else 0.0), time_source
    return float(ev[0] - SCORE_LAG_S - launches[0]), INFERRED


def launches_from_log(
    data: LogData, config: LaunchConfig | None = None
) -> tuple[list[LaunchEvent], str]:
    """Detected launches with the nearest Aim sample (log time), plus the detector's note."""
    result = detect_launches(data, config)
    aim: dict[str, tuple[list[float], list]] = {}
    for key, samples in data.entries.items():
        canon = canonical_key(key)
        if canon is not None and canon.startswith("Alea/Aim/"):
            ordered = sorted(samples, key=lambda s: s[0])
            aim[canon] = ([t for t, _ in ordered], [v for _, v in ordered])

    def nearest(name: str, t_s: float):
        times_values = aim.get("Alea/Aim/" + name)
        if not times_values or not times_values[0]:
            return None
        times, values = times_values
        i = bisect_left(times, t_s)
        cands = [j for j in (i - 1, i) if 0 <= j < len(times)]
        return values[min(cands, key=lambda j: abs(times[j] - t_s))]

    def num(x) -> float | None:
        return float(x) if isinstance(x, int | float) and not isinstance(x, bool) else None

    def flag(x) -> bool | None:
        return bool(x) if isinstance(x, bool | int) else None

    out = []
    for found in result.launches:
        out.append(
            LaunchEvent(
                t_s=found.t_s,
                distance_in=num(nearest("DistanceIn", found.t_s)),
                off_axis_deg=num(nearest("OffAxisDeg", found.t_s)),
                aimed=flag(nearest("Aimed", found.t_s)),
                in_range=flag(nearest("InRange", found.t_s)),
                setpoint_ticks_per_sec=num(nearest("LutTicksPerSec", found.t_s)),
                flywheel_before_ticks_per_sec=found.ticks_per_sec_before,
                dip_ticks_per_sec=found.dip_ticks_per_sec,
            )
        )
    return out, result.note


def build_timeline(
    launches: list[LaunchEvent],
    overlay_events: list[OverlayEvent] | None = None,
    alliance: str | None = None,
    *,
    log_present: bool = True,
) -> MatchTimeline:
    """Combine log launches (log time) with overlay events into one timeline in match time."""
    events = list(overlay_events or [])
    if alliance is not None:
        events = [e for e in events if e.alliance == alliance]
    log_times = [launch.t_s for launch in launches]
    offset, source = align_log_to_match(log_times, events) if events else (0.0, INFERRED)

    shifted = [replace(launch, t_s=launch.t_s + offset, source=source) for launch in launches]
    tl = MatchTimeline(
        launches=shifted,
        alliance=alliance,
        offset_s=offset,
        offset_source=source,
        log_present=log_present,
        overlay_present=bool(events),
        phases_source=MEASURED if events else INFERRED,
    )
    if events:
        times, _ = overlay_match_times_s(events)
        order = sorted(range(len(events)), key=lambda i: times[i])
        events = [events[i] for i in order]
        times = [times[i] for i in order]
        score_idx = [i for i, e in enumerate(events) if e.field == "score" and e.delta != 0]
        tl.score_steps = [events[i] for i in score_idx]
        tl.score_times_s = [times[i] for i in score_idx]
        tip_idx = [i for i, e in enumerate(events) if e.field == "tips" and e.delta > 0]
        if not tip_idx:
            tip_idx = [i for i in score_idx if events[i].kind_guess == "tip"]
        tl.tip_events = [events[i] for i in tip_idx]
        tl.tip_times_s = [times[i] for i in tip_idx]
        if alliance is not None and score_idx:
            tl.final_score_pts = events[score_idx[-1]].new
    return tl
