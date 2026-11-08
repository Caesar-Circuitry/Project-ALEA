"""Click-log schema for video review: one JSONL line per observed launch (roadmap phase 2).

Raw clicks (frame, u_px, v_px, presentation time) are the truth. Inches, speeds and
efficiencies are derived later and never stored here, so a better calibration never
invalidates the clicks. Every record carries ``schema_version``; a mismatch is rejected.
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alea.video.landmark_ids import is_valid_landmark_id

SCHEMA_VERSION = 1

CLICK_KINDS = ("top_plate_centre", "floor_contact")
LANDING_KINDS = ("floor", "hive_cell", "hive_frame", "wall", "out_of_field", "unknown")
RESULTS = ("made", "miss", "unknown")
TRACK_SOURCES = ("click", "sam2")
ALLIANCES = ("red", "blue")

LAUNCH_CSV_COLUMNS = (
    "observation_id",
    "video_sha256",
    "event_code",
    "match_label",
    "alliance",
    "team_number",
    "operator",
    "created_at",
    "robot_frame",
    "robot_u_px",
    "robot_v_px",
    "robot_click_kind",
    "robot_click_z_in",
    "launch_frame",
    "launch_t_pts_s",
    "launch_confidence_frames",
    "n_track_points",
    "landing_frame",
    "landing_u_px",
    "landing_v_px",
    "landing_kind",
    "landing_z_in_assumed",
    "result",
    "target",
    "notes",
)
TRACK_CSV_COLUMNS = ("observation_id", "frame", "t_pts_s", "u_px", "v_px", "source")


class ClickLogError(ValueError):
    """A click-log record or file is malformed or has the wrong schema version."""


# --- validation helpers ---------------------------------------------------------------------


def _mapping(value: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ClickLogError(f"{what} must be an object")
    return value


def _int(d: Mapping[str, Any], key: str, what: str, minimum: int = 0) -> int:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int) or v < minimum:
        raise ClickLogError(f"{what}.{key} must be an integer >= {minimum}, got {v!r}")
    return v


def _float(d: Mapping[str, Any], key: str, what: str, minimum: float | None = None) -> float:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise ClickLogError(f"{what}.{key} must be a finite number, got {v!r}")
    if minimum is not None and v < minimum:
        raise ClickLogError(f"{what}.{key} must be >= {minimum}, got {v!r}")
    return float(v)


def _opt_float(d: Mapping[str, Any], key: str, what: str) -> float | None:
    return None if d.get(key) is None else _float(d, key, what)


def _str(d: Mapping[str, Any], key: str, what: str, default: str | None = None) -> str:
    v = d.get(key, default)
    if not isinstance(v, str):
        raise ClickLogError(f"{what}.{key} must be a string, got {v!r}")
    return v


def _opt_str(d: Mapping[str, Any], key: str, what: str) -> str | None:
    return None if d.get(key) is None else _str(d, key, what)


def _choice(value: str, allowed: tuple[str, ...], what: str) -> str:
    if value not in allowed:
        raise ClickLogError(f"{what} must be one of {', '.join(allowed)}, got {value!r}")
    return value


def _check_version(d: Mapping[str, Any]) -> None:
    version = d.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ClickLogError(
            f"unsupported schema_version {version!r} (this reader handles {SCHEMA_VERSION})"
        )


# --- records --------------------------------------------------------------------------------


@dataclass(frozen=True)
class RobotClick:
    """Where the robot was at ``frame``; ``click_z_in`` is the height of the clicked point."""

    frame: int
    u_px: float
    v_px: float
    click_kind: str = "top_plate_centre"
    click_z_in: float = 0.0
    heading_hint_deg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "u_px": self.u_px,
            "v_px": self.v_px,
            "click_kind": self.click_kind,
            "click_z_in": self.click_z_in,
            "heading_hint_deg": self.heading_hint_deg,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> RobotClick:
        d = _mapping(raw, "robot")
        kind = _choice(_str(d, "click_kind", "robot"), CLICK_KINDS, "robot.click_kind")
        z_in = _float(d, "click_z_in", "robot", minimum=0.0)
        if kind == "floor_contact" and z_in != 0.0:
            raise ClickLogError("robot.click_z_in must be 0 for floor_contact")
        return cls(
            _int(d, "frame", "robot"),
            _float(d, "u_px", "robot"),
            _float(d, "v_px", "robot"),
            kind,
            z_in,
            _opt_float(d, "heading_hint_deg", "robot"),
        )


@dataclass(frozen=True)
class LaunchMark:
    """First frame in which the ball is clearly out of the robot (+- confidence_frames)."""

    frame: int
    t_pts_s: float
    confidence_frames: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "t_pts_s": self.t_pts_s,
            "confidence_frames": self.confidence_frames,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> LaunchMark:
        d = _mapping(raw, "launch")
        return cls(
            _int(d, "frame", "launch"),
            _float(d, "t_pts_s", "launch", minimum=0.0),
            _int(d, "confidence_frames", "launch"),
        )


@dataclass(frozen=True)
class TrackPoint:
    """One clicked (or tracked) ball position."""

    frame: int
    t_pts_s: float
    u_px: float
    v_px: float
    source: str = "click"

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "t_pts_s": self.t_pts_s,
            "u_px": self.u_px,
            "v_px": self.v_px,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> TrackPoint:
        d = _mapping(raw, "ball_track[]")
        return cls(
            _int(d, "frame", "ball_track[]"),
            _float(d, "t_pts_s", "ball_track[]", minimum=0.0),
            _float(d, "u_px", "ball_track[]"),
            _float(d, "v_px", "ball_track[]"),
            _choice(_str(d, "source", "ball_track[]", "click"), TRACK_SOURCES, "source"),
        )


@dataclass(frozen=True)
class Landing:
    """Where the ball came down; ``z_in_assumed`` is the surface height the analyzer uses."""

    frame: int
    u_px: float
    v_px: float
    kind: str = "unknown"
    z_in_assumed: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "u_px": self.u_px,
            "v_px": self.v_px,
            "kind": self.kind,
            "z_in_assumed": self.z_in_assumed,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Landing:
        d = _mapping(raw, "landing")
        return cls(
            _int(d, "frame", "landing"),
            _float(d, "u_px", "landing"),
            _float(d, "v_px", "landing"),
            _choice(_str(d, "kind", "landing", "unknown"), LANDING_KINDS, "landing.kind"),
            _opt_float(d, "z_in_assumed", "landing"),
        )


@dataclass(frozen=True)
class Outcome:
    """Made / miss / unknown; ``target`` uses the robot-contract enum names."""

    result: str = "unknown"
    target: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"result": self.result, "target": self.target, "notes": self.notes}

    @classmethod
    def from_dict(cls, raw: Any) -> Outcome:
        d = _mapping(raw, "outcome")
        return cls(
            _choice(_str(d, "result", "outcome", "unknown"), RESULTS, "outcome.result"),
            _opt_str(d, "target", "outcome"),
            _str(d, "notes", "outcome", ""),
        )


@dataclass(frozen=True)
class ShotObservation:
    """One observed launch: raw clicks on one video.

    No calibration is referenced: analysis resolves it from the calibration keyframes.
    """

    observation_id: str
    video_sha256: str
    robot: RobotClick
    launch: LaunchMark
    ball_track: tuple[TrackPoint, ...] = ()
    landing: Landing | None = None
    outcome: Outcome = field(default_factory=Outcome)
    event_code: str | None = None
    match_label: str | None = None
    alliance: str | None = None
    team_number: int | None = None
    operator: str = ""
    created_at: str = ""
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "video_sha256": self.video_sha256,
            "event_code": self.event_code,
            "match_label": self.match_label,
            "alliance": self.alliance,
            "team_number": self.team_number,
            "operator": self.operator,
            "created_at": self.created_at,
            "robot": self.robot.to_dict(),
            "launch": self.launch.to_dict(),
            "ball_track": [p.to_dict() for p in self.ball_track],
            "landing": None if self.landing is None else self.landing.to_dict(),
            "outcome": self.outcome.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> ShotObservation:
        d = _mapping(raw, "record")
        _check_version(d)
        track_raw = d.get("ball_track", [])
        if not isinstance(track_raw, list):
            raise ClickLogError("ball_track must be a list")
        track = tuple(TrackPoint.from_dict(p) for p in track_raw)
        if any(b.frame < a.frame for a, b in itertools.pairwise(track)):
            raise ClickLogError("ball_track frames must not decrease")
        alliance = _opt_str(d, "alliance", "record")
        if alliance is not None:
            _choice(alliance, ALLIANCES, "alliance")
        team = d.get("team_number")
        if team is not None:
            team = _int(d, "team_number", "record", minimum=1)
        return cls(
            observation_id=_str(d, "observation_id", "record"),
            video_sha256=_str(d, "video_sha256", "record"),
            robot=RobotClick.from_dict(d.get("robot")),
            launch=LaunchMark.from_dict(d.get("launch")),
            ball_track=track,
            landing=None if d.get("landing") is None else Landing.from_dict(d["landing"]),
            outcome=Outcome.from_dict(d.get("outcome", {})),
            event_code=_opt_str(d, "event_code", "record"),
            match_label=_opt_str(d, "match_label", "record"),
            alliance=alliance,
            team_number=team,
            operator=_str(d, "operator", "record", ""),
            created_at=_str(d, "created_at", "record", ""),
        )


# --- JSONL and CSV --------------------------------------------------------------------------


def dumps_record(obs: ShotObservation) -> str:
    """One JSONL line (no trailing newline)."""
    return json.dumps(obs.to_dict(), separators=(",", ":"), allow_nan=False)


def loads_record(line: str) -> ShotObservation:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ClickLogError(f"invalid JSON: {exc}") from exc
    return ShotObservation.from_dict(raw)


def read_jsonl(path: Path) -> list[ShotObservation]:
    """Read and validate every record; errors name the 1-based line number."""
    records: list[ShotObservation] = []
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                records.append(loads_record(line))
            except ClickLogError as exc:
                raise ClickLogError(f"{path}:{n}: {exc}") from exc
    return records


def _atomic_write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)


def write_jsonl(path: Path, records: Iterable[ShotObservation]) -> None:
    """Atomically replace ``path`` with ``records`` (temp file + rename)."""
    _atomic_write_lines(path, (dumps_record(r) for r in records))


def append_jsonl(path: Path, record: ShotObservation) -> None:
    """Append one record (autosave after every finished shot)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(dumps_record(record) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def launch_rows(records: Iterable[ShotObservation]) -> list[dict[str, Any]]:
    """Flat rows for ``launches.csv`` (raw click data only; derived columns come from analyze)."""
    rows: list[dict[str, Any]] = []
    for r in records:
        land = r.landing
        rows.append(
            {
                "observation_id": r.observation_id,
                "video_sha256": r.video_sha256,
                "event_code": r.event_code,
                "match_label": r.match_label,
                "alliance": r.alliance,
                "team_number": r.team_number,
                "operator": r.operator,
                "created_at": r.created_at,
                "robot_frame": r.robot.frame,
                "robot_u_px": r.robot.u_px,
                "robot_v_px": r.robot.v_px,
                "robot_click_kind": r.robot.click_kind,
                "robot_click_z_in": r.robot.click_z_in,
                "launch_frame": r.launch.frame,
                "launch_t_pts_s": r.launch.t_pts_s,
                "launch_confidence_frames": r.launch.confidence_frames,
                "n_track_points": len(r.ball_track),
                "landing_frame": None if land is None else land.frame,
                "landing_u_px": None if land is None else land.u_px,
                "landing_v_px": None if land is None else land.v_px,
                "landing_kind": None if land is None else land.kind,
                "landing_z_in_assumed": None if land is None else land.z_in_assumed,
                "result": r.outcome.result,
                "target": r.outcome.target,
                "notes": r.outcome.notes,
            }
        )
    return rows


def track_rows(records: Iterable[ShotObservation]) -> list[dict[str, Any]]:
    """Flat rows for ``track_points.csv``."""
    return [
        {"observation_id": r.observation_id, **p.to_dict()} for r in records for p in r.ball_track
    ]


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def export_csv(records: list[ShotObservation], out_dir: Path) -> tuple[Path, Path]:
    """Write ``launches.csv`` and ``track_points.csv`` into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    launches = out_dir / "launches.csv"
    tracks = out_dir / "track_points.csv"
    _write_csv(launches, LAUNCH_CSV_COLUMNS, launch_rows(records))
    _write_csv(tracks, TRACK_CSV_COLUMNS, track_rows(records))
    return launches, tracks


# --- landmark clicks and video metadata -----------------------------------------------------


@dataclass(frozen=True)
class LandmarkClick:
    """A click on a known field landmark: the raw input for fitting a calibration keyframe.

    ``landmark_id`` is an id string (see ``alea.video.landmark_ids``), never coordinates.
    Kept in its own JSONL file, separate from shot clicks. If the same landmark is clicked
    twice on one frame, the later line wins (``latest_landmark_clicks``). Clicks from any
    frame of the same video are pooled when the video's one calibration is fitted (the camera
    is static within a video).
    """

    video_sha256: str
    frame: int
    t_pts_s: float
    landmark_id: str
    u_px: float
    v_px: float
    operator: str = ""
    created_at: str = ""
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "video_sha256": self.video_sha256,
            "frame": self.frame,
            "t_pts_s": self.t_pts_s,
            "landmark_id": self.landmark_id,
            "u_px": self.u_px,
            "v_px": self.v_px,
            "operator": self.operator,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> LandmarkClick:
        d = _mapping(raw, "landmark_click")
        _check_version(d)
        lid = _str(d, "landmark_id", "landmark_click")
        if not is_valid_landmark_id(lid):
            raise ClickLogError(f"unknown landmark_id {lid!r}")
        return cls(
            _str(d, "video_sha256", "landmark_click"),
            _int(d, "frame", "landmark_click"),
            _float(d, "t_pts_s", "landmark_click", minimum=0.0),
            lid,
            _float(d, "u_px", "landmark_click"),
            _float(d, "v_px", "landmark_click"),
            _str(d, "operator", "landmark_click", ""),
            _str(d, "created_at", "landmark_click", ""),
        )


def latest_landmark_clicks(clicks: Iterable[LandmarkClick]) -> list[LandmarkClick]:
    """One click per (frame, landmark_id), the last written, ordered by frame then id."""
    latest = {(c.frame, c.landmark_id): c for c in clicks}
    return [latest[k] for k in sorted(latest)]


def read_landmarks_jsonl(path: Path) -> list[LandmarkClick]:
    clicks: list[LandmarkClick] = []
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                clicks.append(LandmarkClick.from_dict(json.loads(line)))
            except (ClickLogError, json.JSONDecodeError) as exc:
                raise ClickLogError(f"{path}:{n}: {exc}") from exc
    return clicks


def write_landmarks_jsonl(path: Path, clicks: Iterable[LandmarkClick]) -> None:
    _atomic_write_lines(path, (json.dumps(c.to_dict(), allow_nan=False) for c in clicks))


@dataclass(frozen=True)
class CalibrationRef:
    """Reference to the video's one calibration JSON (the file belongs to the camera geometry
    code). ``calibration_version`` is that file's own ``schema_version``; ``camera_setup_id``
    names the camera placement (one per event or video; the camera is static within a video)."""

    path: str
    calibration_version: int | None = None
    camera_setup_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "calibration_version": self.calibration_version,
            "camera_setup_id": self.camera_setup_id,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> CalibrationRef:
        d = _mapping(raw, "calibration")
        version = d.get("calibration_version")
        return cls(
            _str(d, "path", "calibration"),
            None if version is None else _int(d, "calibration_version", "calibration"),
            _opt_str(d, "camera_setup_id", "calibration"),
        )


@dataclass(frozen=True)
class VideoMeta:
    """Per-video metadata: identity plus a reference to its single calibration, if fitted.

    Shot and landmark clicks never carry calibration data; analysis resolves it from here.
    """

    video_sha256: str
    file_name: str
    width_px: int
    height_px: int
    fps_nominal: float | None
    frame_count: int
    calibration: CalibrationRef | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "video_sha256": self.video_sha256,
            "file_name": self.file_name,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "fps_nominal": self.fps_nominal,
            "frame_count": self.frame_count,
            "calibration": None if self.calibration is None else self.calibration.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> VideoMeta:
        d = _mapping(raw, "video")
        _check_version(d)
        return cls(
            _str(d, "video_sha256", "video"),
            _str(d, "file_name", "video"),
            _int(d, "width_px", "video"),
            _int(d, "height_px", "video"),
            _opt_float(d, "fps_nominal", "video"),
            _int(d, "frame_count", "video"),
            None if d.get("calibration") is None else CalibrationRef.from_dict(d["calibration"]),
        )


def read_video_meta(path: Path) -> VideoMeta:
    try:
        return VideoMeta.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise ClickLogError(f"{path}: invalid JSON: {exc}") from exc


def write_video_meta(path: Path, meta: VideoMeta) -> None:
    _atomic_write_lines(path, [json.dumps(meta.to_dict(), indent=2, allow_nan=False)])
