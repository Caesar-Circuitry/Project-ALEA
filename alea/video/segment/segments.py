"""Match-segment schema v1: where each match sits in a local video file (roadmap stage 2.2b).

Times are presentation times of the file (``*_pts_s``), the same convention as ``t_pts_s`` in the
click log, and ``video.sha256``, ``event.event_code`` and ``match_label`` use the click-log
names. A segment says where a match is and who played; it never holds footage or thumbnails.
Every file carries ``schema_version``; a mismatch raises :class:`SegmentError`.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
KIND = "match_segments"

TOURNAMENT_LEVELS = ("Quals", "Semis", "Finals", "DoubleElim", "Unknown")
REVIEW_STATUSES = ("auto", "accepted", "edited")
ALLIANCES = ("red", "blue")

SEGMENT_CSV_COLUMNS: tuple[str, ...] = (
    "segment_id",
    "video_sha256",
    "event_code",
    "match_label",
    "match_label_raw",
    "tournament_level",
    "series",
    "match_number",
    "start_pts_s",
    "play_start_pts_s",
    "play_end_pts_s",
    "end_pts_s",
    "red_teams",
    "blue_teams",
    "red_final",
    "blue_final",
    "schedule_matched",
    "confidence",
    "needs_review",
    "review_status",
)

_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class SegmentError(ValueError):
    """A segment record or file is malformed, inconsistent or has the wrong schema version."""


# --- validation helpers ---------------------------------------------------------------------


def _mapping(value: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SegmentError(f"{what} must be an object")
    return value


def _int(d: Mapping[str, Any], key: str, what: str, minimum: int = 0) -> int:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int) or v < minimum:
        raise SegmentError(f"{what}.{key} must be an integer >= {minimum}, got {v!r}")
    return v


def _float(d: Mapping[str, Any], key: str, what: str, minimum: float | None = None) -> float:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise SegmentError(f"{what}.{key} must be a finite number, got {v!r}")
    if minimum is not None and v < minimum:
        raise SegmentError(f"{what}.{key} must be >= {minimum}, got {v!r}")
    return float(v)


def _str(d: Mapping[str, Any], key: str, what: str, default: str | None = None) -> str:
    v = d.get(key, default)
    if not isinstance(v, str):
        raise SegmentError(f"{what}.{key} must be a string, got {v!r}")
    return v


def _opt_str(d: Mapping[str, Any], key: str, what: str) -> str | None:
    return None if d.get(key) is None else _str(d, key, what)


def _bool(d: Mapping[str, Any], key: str, what: str) -> bool:
    v = d.get(key)
    if not isinstance(v, bool):
        raise SegmentError(f"{what}.{key} must be true or false, got {v!r}")
    return v


def _check_utc(value: str, what: str) -> None:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise SegmentError(f"{what} must be an ISO 8601 timestamp, got {value!r}") from None


def _team_list(raw: Any, what: str) -> tuple[int, ...]:
    if not isinstance(raw, list | tuple):
        raise SegmentError(f"{what} must be a list of team numbers")
    out: list[int] = []
    for t in raw:
        if isinstance(t, bool) or not isinstance(t, int) or t <= 0:
            raise SegmentError(f"{what} holds a bad team number: {t!r}")
        out.append(t)
    return tuple(out)


# --- records --------------------------------------------------------------------------------


@dataclass(frozen=True)
class VideoRef:
    file: str
    sha256: str
    width_px: int
    height_px: int
    fps_nominal: float
    duration_s: float
    pts_origin: str = "first_frame"

    def __post_init__(self) -> None:
        if self.width_px <= 0 or self.height_px <= 0:
            raise SegmentError("video width_px and height_px must be positive")
        if not (math.isfinite(self.fps_nominal) and self.fps_nominal > 0):
            raise SegmentError("video.fps_nominal must be positive")
        if not (math.isfinite(self.duration_s) and self.duration_s >= 0):
            raise SegmentError("video.duration_s must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "sha256": self.sha256,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "fps_nominal": self.fps_nominal,
            "duration_s": self.duration_s,
            "pts_origin": self.pts_origin,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> VideoRef:
        d = _mapping(raw, "video")
        return cls(
            _str(d, "file", "video"),
            _str(d, "sha256", "video"),
            _int(d, "width_px", "video", 1),
            _int(d, "height_px", "video", 1),
            _float(d, "fps_nominal", "video"),
            _float(d, "duration_s", "video", 0.0),
            _str(d, "pts_origin", "video", "first_frame"),
        )


@dataclass(frozen=True)
class EventRef:
    event_code: str
    season: int
    schedule_source: str | None = None
    schedule_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.event_code.strip():
            raise SegmentError("event.event_code must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_code": self.event_code,
            "season": self.season,
            "schedule_source": self.schedule_source,
            "schedule_sha256": self.schedule_sha256,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> EventRef:
        d = _mapping(raw, "event")
        return cls(
            _str(d, "event_code", "event"),
            _int(d, "season", "event", 2000),
            _opt_str(d, "schedule_source", "event"),
            _opt_str(d, "schedule_sha256", "event"),
        )


@dataclass(frozen=True)
class AffineUtcToVideo:
    """``t_video_s = a * t_utc_s + b`` with ``t_utc_s`` = seconds since ``stream_start_utc``."""

    a: float
    b: float
    n_anchors: int

    def to_dict(self) -> dict[str, Any]:
        return {"a": self.a, "b": self.b, "n_anchors": self.n_anchors}

    @classmethod
    def from_dict(cls, raw: Any) -> AffineUtcToVideo:
        d = _mapping(raw, "stream_clock.affine_utc_to_video")
        what = "affine_utc_to_video"
        return cls(_float(d, "a", what), _float(d, "b", what), _int(d, "n_anchors", what))


@dataclass(frozen=True)
class StreamClock:
    stream_start_utc: str
    affine_utc_to_video: AffineUtcToVideo | None = None

    def __post_init__(self) -> None:
        _check_utc(self.stream_start_utc, "stream_clock.stream_start_utc")

    def to_dict(self) -> dict[str, Any]:
        aff = self.affine_utc_to_video
        return {
            "stream_start_utc": self.stream_start_utc,
            "affine_utc_to_video": None if aff is None else aff.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> StreamClock:
        d = _mapping(raw, "stream_clock")
        aff = d.get("affine_utc_to_video")
        return cls(
            _str(d, "stream_start_utc", "stream_clock"),
            None if aff is None else AffineUtcToVideo.from_dict(aff),
        )


@dataclass(frozen=True)
class Score:
    red_final: int
    blue_final: int

    def __post_init__(self) -> None:
        if self.red_final < 0 or self.blue_final < 0:
            raise SegmentError("scores must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {"red_final": self.red_final, "blue_final": self.blue_final}

    @classmethod
    def from_dict(cls, raw: Any) -> Score:
        d = _mapping(raw, "score")
        return cls(_int(d, "red_final", "score"), _int(d, "blue_final", "score"))


@dataclass(frozen=True)
class ScheduleMatchRef:
    matched: bool
    official_actual_start_utc: str | None = None

    def __post_init__(self) -> None:
        if self.official_actual_start_utc is not None:
            _check_utc(self.official_actual_start_utc, "schedule_match.official_actual_start_utc")

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "official_actual_start_utc": self.official_actual_start_utc,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> ScheduleMatchRef:
        d = _mapping(raw, "schedule_match")
        return cls(
            _bool(d, "matched", "schedule_match"),
            _opt_str(d, "official_actual_start_utc", "schedule_match"),
        )


@dataclass(frozen=True)
class Review:
    status: str = "auto"
    operator: str | None = None
    changed_fields: tuple[str, ...] = ()
    original: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in REVIEW_STATUSES:
            raise SegmentError(f"review.status must be one of {', '.join(REVIEW_STATUSES)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "operator": self.operator,
            "changed_fields": list(self.changed_fields),
            "original": self.original,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Review:
        d = _mapping(raw, "review")
        changed = d.get("changed_fields", [])
        if not isinstance(changed, list) or not all(isinstance(c, str) for c in changed):
            raise SegmentError("review.changed_fields must be a list of strings")
        original = d.get("original")
        if original is not None:
            original = dict(_mapping(original, "review.original"))
        return cls(
            _str(d, "status", "review", "auto"),
            _opt_str(d, "operator", "review"),
            tuple(changed),
            original,
        )


@dataclass(frozen=True)
class MatchSegment:
    """One match in the video. ``match_label`` is ``Q6`` style; playoff labels stay as given."""

    segment_id: str
    match_label: str
    match_label_raw: str
    tournament_level: str
    series: int
    match_number: int
    start_pts_s: float
    play_start_pts_s: float
    play_end_pts_s: float
    end_pts_s: float
    red_teams: tuple[int, ...] = ()
    blue_teams: tuple[int, ...] = ()
    score: Score | None = None
    schedule_match: ScheduleMatchRef | None = None
    confidence: float = 0.0
    needs_review: bool = True
    review: Review = field(default_factory=Review)
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.segment_id:
            raise SegmentError("segment_id must not be empty")
        if not _LABEL_RE.match(self.match_label):
            raise SegmentError(f"bad match_label {self.match_label!r}")
        if self.tournament_level not in TOURNAMENT_LEVELS:
            raise SegmentError(f"tournament_level must be one of {', '.join(TOURNAMENT_LEVELS)}")
        if self.tournament_level == "Quals" and self.match_label != f"Q{self.match_number}":
            raise SegmentError(
                f"Quals label must be Q<match_number>, got {self.match_label!r} "
                f"for match_number {self.match_number}"
            )
        times = (self.start_pts_s, self.play_start_pts_s, self.play_end_pts_s, self.end_pts_s)
        if not all(math.isfinite(t) and t >= 0 for t in times):
            raise SegmentError(f"{self.match_label}: times must be finite and >= 0")
        if not (self.start_pts_s <= self.play_start_pts_s < self.play_end_pts_s <= self.end_pts_s):
            raise SegmentError(
                f"{self.match_label}: need start <= play_start < play_end <= end, got {times}"
            )
        if not (math.isfinite(self.confidence) and 0.0 <= self.confidence <= 1.0):
            raise SegmentError(f"{self.match_label}: confidence must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "match_label": self.match_label,
            "match_label_raw": self.match_label_raw,
            "tournament_level": self.tournament_level,
            "series": self.series,
            "match_number": self.match_number,
            "start_pts_s": self.start_pts_s,
            "play_start_pts_s": self.play_start_pts_s,
            "play_end_pts_s": self.play_end_pts_s,
            "end_pts_s": self.end_pts_s,
            "teams": {"red": list(self.red_teams), "blue": list(self.blue_teams)},
            "score": None if self.score is None else self.score.to_dict(),
            "schedule_match": None
            if self.schedule_match is None
            else self.schedule_match.to_dict(),
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "review": self.review.to_dict(),
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> MatchSegment:
        d = _mapping(raw, "segment")
        teams = _mapping(d.get("teams", {}), "segment.teams")
        score = d.get("score")
        sched = d.get("schedule_match")
        review = d.get("review")
        evidence = d.get("evidence", {})
        if not isinstance(evidence, dict):
            raise SegmentError("segment.evidence must be an object")
        return cls(
            segment_id=_str(d, "segment_id", "segment"),
            match_label=_str(d, "match_label", "segment"),
            match_label_raw=_str(d, "match_label_raw", "segment", ""),
            tournament_level=_str(d, "tournament_level", "segment"),
            series=_int(d, "series", "segment"),
            match_number=_int(d, "match_number", "segment"),
            start_pts_s=_float(d, "start_pts_s", "segment", 0.0),
            play_start_pts_s=_float(d, "play_start_pts_s", "segment", 0.0),
            play_end_pts_s=_float(d, "play_end_pts_s", "segment", 0.0),
            end_pts_s=_float(d, "end_pts_s", "segment", 0.0),
            red_teams=_team_list(teams.get("red", []), "teams.red"),
            blue_teams=_team_list(teams.get("blue", []), "teams.blue"),
            score=None if score is None else Score.from_dict(score),
            schedule_match=None if sched is None else ScheduleMatchRef.from_dict(sched),
            confidence=_float(d, "confidence", "segment", 0.0),
            needs_review=_bool(d, "needs_review", "segment"),
            review=Review() if review is None else Review.from_dict(review),
            evidence=evidence,
        )

    def has_team(self, team_number: int) -> bool:
        return team_number in self.red_teams or team_number in self.blue_teams


@dataclass(frozen=True)
class SegmentFile:
    video: VideoRef
    event: EventRef
    profile_id: str
    segments: tuple[MatchSegment, ...] = ()
    stream_clock: StreamClock | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    kind: str = KIND

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise SegmentError(
                f"unsupported schema_version {self.schema_version!r} "
                f"(this reader handles {SCHEMA_VERSION})"
            )
        if self.kind != KIND:
            raise SegmentError(f"kind must be {KIND!r}, got {self.kind!r}")
        ids = [s.segment_id for s in self.segments]
        if len(set(ids)) != len(ids):
            raise SegmentError("duplicate segment_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "video": self.video.to_dict(),
            "event": self.event.to_dict(),
            "profile_id": self.profile_id,
            "stream_clock": None if self.stream_clock is None else self.stream_clock.to_dict(),
            "segments": [s.to_dict() for s in self.segments],
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> SegmentFile:
        d = _mapping(raw, "segment file")
        version = d.get("schema_version")
        if version != SCHEMA_VERSION:
            raise SegmentError(
                f"unsupported schema_version {version!r} (this reader handles {SCHEMA_VERSION})"
            )
        clock = d.get("stream_clock")
        segs = d.get("segments", [])
        if not isinstance(segs, list):
            raise SegmentError("segments must be a list")
        diag = d.get("diagnostics", {})
        if not isinstance(diag, dict):
            raise SegmentError("diagnostics must be an object")
        return cls(
            video=VideoRef.from_dict(d.get("video")),
            event=EventRef.from_dict(d.get("event")),
            profile_id=_str(d, "profile_id", "segment file"),
            segments=tuple(MatchSegment.from_dict(s) for s in segs),
            stream_clock=None if clock is None else StreamClock.from_dict(clock),
            diagnostics=diag,
            schema_version=version,
            kind=_str(d, "kind", "segment file", KIND),
        )


# --- files ----------------------------------------------------------------------------------


def read_json(path: Path | str) -> SegmentFile:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SegmentError(f"{path}: invalid JSON: {exc}") from exc
    try:
        return SegmentFile.from_dict(raw)
    except SegmentError as exc:
        raise SegmentError(f"{path}: {exc}") from exc


def write_json(path: Path | str, segment_file: SegmentFile) -> None:
    """Atomic write: a temp file in the same folder, fsync, then replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(segment_file.to_dict(), fh, indent=2, sort_keys=False)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)


def segments_csv_rows(segment_file: SegmentFile) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for s in segment_file.segments:
        rows.append(
            {
                "segment_id": s.segment_id,
                "video_sha256": segment_file.video.sha256,
                "event_code": segment_file.event.event_code,
                "match_label": s.match_label,
                "match_label_raw": s.match_label_raw,
                "tournament_level": s.tournament_level,
                "series": s.series,
                "match_number": s.match_number,
                "start_pts_s": s.start_pts_s,
                "play_start_pts_s": s.play_start_pts_s,
                "play_end_pts_s": s.play_end_pts_s,
                "end_pts_s": s.end_pts_s,
                "red_teams": ";".join(str(t) for t in s.red_teams),
                "blue_teams": ";".join(str(t) for t in s.blue_teams),
                "red_final": "" if s.score is None else s.score.red_final,
                "blue_final": "" if s.score is None else s.score.blue_final,
                "schedule_matched": "" if s.schedule_match is None else s.schedule_match.matched,
                "confidence": s.confidence,
                "needs_review": s.needs_review,
                "review_status": s.review.status,
            }
        )
    return rows


def export_csv(segment_file: SegmentFile, path: Path | str) -> Path:
    """Write the flat ``segments.csv`` for spreadsheet review."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(SEGMENT_CSV_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(segments_csv_rows(segment_file))
    return path


def sorted_by_start(segments: Iterable[MatchSegment]) -> list[MatchSegment]:
    return sorted(segments, key=lambda s: s.play_start_pts_s)
