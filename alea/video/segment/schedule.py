"""Official match schedule (FTCScout REST shape) read from a LOCAL JSON file.

The schedule is a prior and a validator for the video segments, never a source of truth for
video times. Nothing here touches the network. To get the file once per event, run on a
machine you trust (one request, then keep the JSON)::

    curl -o ftcscout_<code>.json https://api.ftcscout.org/rest/v1/events/<season>/<code>/matches
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from alea.video.segment.segments import MatchSegment, SegmentError

# DECISION FOR THE USER: how playoff matches are labelled in ``Match.label``. This default is
# a proposal. FTCScout gives ``tournamentLevel`` in {Quals, Semis, Finals, DoubleElim}.
DEFAULT_LABEL_FORMATS: dict[str, str] = {
    "Quals": "Q{number}",
    "Semis": "SF{series}-{number}",
    "Finals": "F{number}",
    "DoubleElim": "M{series}",
}

# FTCScout match ids for playoffs are offset by level (Finals 20001, 20002 in the Athens data).
_ID_OFFSET = 10000
JUMP_THRESHOLD_S = 30.0


class ScheduleError(SegmentError):
    """The schedule JSON is malformed."""


def label_for(
    level: str,
    series: int,
    number: int,
    formats: Mapping[str, str] | None = None,
) -> str:
    """``Q6`` for quals; playoffs follow ``formats`` (default :data:`DEFAULT_LABEL_FORMATS`)."""
    fmt = (formats or DEFAULT_LABEL_FORMATS).get(level)
    if fmt is None:
        fmt = f"{level}{{series}}-{{number}}"
    return fmt.format(series=series, number=number)


@dataclass(frozen=True)
class ScheduledMatch:
    label: str
    tournament_level: str
    series: int
    match_number: int
    actual_start_utc: datetime | None
    post_result_utc: datetime | None
    red_teams: tuple[int, ...]
    blue_teams: tuple[int, ...]
    red_score: int | None
    blue_score: int | None
    extra: dict[str, Any] = field(default_factory=dict)


def _utc(raw: Any, what: str) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ScheduleError(f"{what} must be an ISO 8601 string or null, got {raw!r}")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        raise ScheduleError(f"{what}: bad timestamp {raw!r}") from None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _total(scores: Any, side: str) -> int | None:
    if not isinstance(scores, Mapping):
        return None
    block = scores.get(side)
    if not isinstance(block, Mapping):
        return None
    total = block.get("totalPoints")
    return total if isinstance(total, int) and not isinstance(total, bool) else None


def _match_number(raw: Mapping[str, Any]) -> int:
    if isinstance(raw.get("matchNum"), int):
        return int(raw["matchNum"])
    mid = raw.get("id")
    if isinstance(mid, bool) or not isinstance(mid, int):
        raise ScheduleError(f"match has no integer id or matchNum: {raw.get('id')!r}")
    return mid % _ID_OFFSET if mid >= _ID_OFFSET else mid


def parse_ftcscout_matches(
    raw: Any, formats: Mapping[str, str] | None = None
) -> list[ScheduledMatch]:
    if isinstance(raw, Mapping) and isinstance(raw.get("matches"), list):
        raw = raw["matches"]
    if not isinstance(raw, list):
        raise ScheduleError("expected a JSON list of matches")
    out: list[ScheduledMatch] = []
    for i, m in enumerate(raw):
        if not isinstance(m, Mapping):
            raise ScheduleError(f"match #{i} must be an object")
        level = m.get("tournamentLevel")
        if not isinstance(level, str):
            raise ScheduleError(f"match #{i}: tournamentLevel missing")
        series = m.get("series", 0)
        if isinstance(series, bool) or not isinstance(series, int):
            raise ScheduleError(f"match #{i}: series must be an integer")
        number = _match_number(m)
        red: list[int] = []
        blue: list[int] = []
        for t in m.get("teams") or []:
            if not isinstance(t, Mapping) or not isinstance(t.get("teamNumber"), int):
                raise ScheduleError(f"match #{i}: bad team entry {t!r}")
            side = str(t.get("alliance", "")).lower()
            if side == "red":
                red.append(t["teamNumber"])
            elif side == "blue":
                blue.append(t["teamNumber"])
            else:
                raise ScheduleError(f"match #{i}: unknown alliance {t.get('alliance')!r}")
        scores = m.get("scores")
        out.append(
            ScheduledMatch(
                label=label_for(level, series, number, formats),
                tournament_level=level,
                series=series,
                match_number=number,
                actual_start_utc=_utc(m.get("actualStartTime"), f"match #{i}.actualStartTime"),
                post_result_utc=_utc(m.get("postResultTime"), f"match #{i}.postResultTime"),
                red_teams=tuple(red),
                blue_teams=tuple(blue),
                red_score=_total(scores, "red"),
                blue_score=_total(scores, "blue"),
                extra={
                    "id": m.get("id"),
                    "scheduled_start_utc": m.get("scheduledStartTime"),
                    "has_been_played": m.get("hasBeenPlayed"),
                },
            )
        )
    labels = [s.label for s in out]
    if len(set(labels)) != len(labels):
        raise ScheduleError("duplicate match labels in schedule")
    return out


def load_ftcscout_matches(
    path: Path | str, formats: Mapping[str, str] | None = None
) -> list[ScheduledMatch]:
    """Read ``/rest/v1/events/{season}/{code}/matches`` JSON saved to a local file."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScheduleError(f"{path}: invalid JSON: {exc}") from exc
    try:
        return parse_ftcscout_matches(raw, formats)
    except ScheduleError as exc:
        raise ScheduleError(f"{path}: {exc}") from exc


def expected_video_times(
    matches: Sequence[ScheduledMatch],
    stream_start_utc: datetime,
    affine: tuple[float, float] = (1.0, 0.0),
) -> dict[str, float | None]:
    """Predicted video time (s) of each match start: ``a * (t_utc - stream_start) + b``.

    ``None`` for matches without an ``actual_start_utc``. This is a search-window prior only.
    """
    a, b = affine
    start = stream_start_utc if stream_start_utc.tzinfo else stream_start_utc.replace(tzinfo=UTC)
    out: dict[str, float | None] = {}
    for m in matches:
        if m.actual_start_utc is None:
            out[m.label] = None
        else:
            out[m.label] = a * (m.actual_start_utc - start).total_seconds() + b
    return out


@dataclass(frozen=True)
class Join:
    """One segment paired with its schedule row; either side may be missing."""

    label: str
    segment_id: str | None
    scheduled: ScheduledMatch | None
    disagreements: tuple[str, ...] = ()

    @property
    def matched(self) -> bool:
        return self.segment_id is not None and self.scheduled is not None and not self.disagreements


def match_segments_to_schedule(
    segments: Sequence[MatchSegment], matches: Sequence[ScheduledMatch]
) -> list[Join]:
    """Join by label, then compare the team sets and final scores.

    Segments with no schedule row and played schedule rows with no segment are both listed.
    """
    by_label = {m.label: m for m in matches}
    joins: list[Join] = []
    seen: set[str] = set()
    for seg in segments:
        sched = by_label.get(seg.match_label)
        if sched is None:
            joins.append(Join(seg.match_label, seg.segment_id, None, ("label not in schedule",)))
            continue
        seen.add(seg.match_label)
        bad: list[str] = []
        if seg.red_teams and set(seg.red_teams) != set(sched.red_teams):
            bad.append(f"red teams {sorted(seg.red_teams)} != schedule {sorted(sched.red_teams)}")
        if seg.blue_teams and set(seg.blue_teams) != set(sched.blue_teams):
            bad.append(
                f"blue teams {sorted(seg.blue_teams)} != schedule {sorted(sched.blue_teams)}"
            )
        score = seg.score
        if score is not None and sched.red_score is not None and score.red_final != sched.red_score:
            bad.append(f"red score {score.red_final} != schedule {sched.red_score}")
        if (
            score is not None
            and sched.blue_score is not None
            and score.blue_final != sched.blue_score
        ):
            bad.append(f"blue score {score.blue_final} != schedule {sched.blue_score}")
        joins.append(Join(seg.match_label, seg.segment_id, sched, tuple(bad)))
    for m in matches:
        if m.label not in seen and m.actual_start_utc is not None:
            joins.append(Join(m.label, None, m, ("no segment for played match",)))
    return joins


@dataclass(frozen=True)
class AffineFit:
    a: float
    b: float
    n: int
    residuals_s: tuple[float, ...]
    rms_s: float
    flags: tuple[str, ...]


def fit_affine_utc_to_video(
    pairs: Sequence[tuple[float, float]], jump_threshold_s: float = JUMP_THRESHOLD_S
) -> AffineFit:
    """Least-squares ``t_video = a * t_utc + b`` over ``(t_utc_s, t_video_s)`` anchors.

    With one anchor, ``a`` is fixed to 1. Flags a residual or a step between consecutive
    residuals (in time order) larger than ``jump_threshold_s``: a stream restart or a split VOD.
    """
    if not pairs:
        raise SegmentError("need at least one (t_utc_s, t_video_s) pair")
    ordered = sorted(pairs)
    x = np.array([p[0] for p in ordered], dtype=float)
    y = np.array([p[1] for p in ordered], dtype=float)
    if len(ordered) == 1:
        a, b = 1.0, float(y[0] - x[0])
    else:
        a, b = (float(v) for v in np.polyfit(x, y, 1))
    res = y - (a * x + b)
    flags: list[str] = []
    if np.any(np.abs(res) > jump_threshold_s):
        flags.append(f"residual above {jump_threshold_s:g} s")
    if len(res) > 1 and np.any(np.abs(np.diff(res)) > jump_threshold_s):
        flags.append(f"jump above {jump_threshold_s:g} s between neighbouring anchors")
    return AffineFit(
        a,
        b,
        len(ordered),
        tuple(float(r) for r in res),
        float(np.sqrt(np.mean(res**2))),
        tuple(flags),
    )
