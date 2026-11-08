"""Matplotlib click-and-log review of match video (roadmap phase 2).

The logic lives in pure functions over an immutable ``ReviewState`` (frame stepping, mode
switching, click handling, undo, record building) so it is tested without a display.
``ReviewApp`` is the thin matplotlib glue; matplotlib is imported lazily and only
``run_review`` needs a real display.

Keys (all matplotlib ``keymap.*`` defaults are cleared while the review window is open)::

    left/right  step 1 frame        down/up        step 10 frames
    pagedown/pageup  step 100       home/end       first/last frame
    c landmarks  r robot  l launch  b ball track  d landing  o outcome   (modes)
    [ ] previous / next landmark id, including edge_* ids (landmarks mode; click the point, or
        for an edge any point along it; add several points per edge)
    t toggle robot click kind (top plate / floor contact)
    1..6 landing kind: floor, hive_cell, hive_frame, wall, out_of_field, unknown
    m made  x miss  u unknown       (outcome)
    z undo last click   enter finish and save the record   delete remove last saved record
    q quit
"""

from __future__ import annotations

import json
import math
import os
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from alea.game.biobuzz import CELL_CENTER_UP_IN, HIVE_PIVOT_HEIGHT_IN
from alea.video.clicklog import (
    CLICK_KINDS,
    LANDING_KINDS,
    CalibrationRef,
    Landing,
    LandmarkClick,
    LaunchMark,
    Outcome,
    RobotClick,
    ShotObservation,
    TrackPoint,
    VideoMeta,
    append_jsonl,
    read_jsonl,
    read_landmarks_jsonl,
    write_jsonl,
    write_landmarks_jsonl,
    write_video_meta,
)
from alea.video.frames import VideoError, VideoReader
from alea.video.landmark_ids import is_edge_id, known_landmark_ids

MODES = ("landmarks", "robot", "launch", "track", "landing", "outcome")
MODE_KEYS: Mapping[str, str] = {
    "c": "landmarks",
    "r": "robot",
    "l": "launch",
    "b": "track",
    "d": "landing",
    "o": "outcome",
}
LANDING_KEYS: Mapping[str, str] = {str(i + 1): kind for i, kind in enumerate(LANDING_KINDS)}
OUTCOME_KEYS: Mapping[str, str] = {"m": "made", "x": "miss", "u": "unknown"}
STEP_KEYS: Mapping[str, int] = {
    "right": 1,
    "left": -1,
    "up": 10,
    "down": -10,
    "pageup": 100,
    "pagedown": -100,
}
# Default surface height a hive_cell landing is projected onto (see decision record 0008).
HIVE_CELL_Z_IN = HIVE_PIVOT_HEIGHT_IN + CELL_CENTER_UP_IN
NON_INTERACTIVE_BACKENDS = frozenset({"agg", "pdf", "ps", "svg", "cairo", "template", "pgf"})


class ReviewError(RuntimeError):
    """The review UI cannot run (no display) or a record is incomplete."""


class LandmarkMark(NamedTuple):
    """A click on a named field landmark (raw input to the video's calibration)."""

    frame: int
    t_pts_s: float
    landmark_id: str
    u_px: float
    v_px: float


class Click(NamedTuple):
    """A raw click on a given frame."""

    frame: int
    t_pts_s: float
    u_px: float
    v_px: float


@dataclass(frozen=True)
class ReviewContext:
    """Per-session metadata copied into every record."""

    video_sha256: str
    frame_count: int
    operator: str = ""
    event_code: str | None = None
    match_label: str | None = None
    alliance: str | None = None
    team_number: int | None = None
    click_z_in: float = 16.0  # robot top-plate height; placeholder until measured


@dataclass(frozen=True)
class ReviewState:
    """Everything about the shot being annotated. Immutable; functions return a new state."""

    frame: int = 0
    mode: str = "robot"
    robot_click_kind: str = "top_plate_centre"
    robot: Click | None = None
    launch: Click | None = None
    track: tuple[Click, ...] = ()
    landing: Click | None = None
    landing_kind: str = "floor"
    result: str = "unknown"
    landmark_id: str = known_landmark_ids()[0]
    landmark_marks: tuple[LandmarkMark, ...] = ()
    history: tuple[str, ...] = ()  # one entry per undoable action, newest last
    message: str = ""

    @property
    def has_draft(self) -> bool:
        return bool(self.history)


def clamp_frame(frame: int, frame_count: int) -> int:
    return max(0, min(frame, max(frame_count - 1, 0)))


def step_frame(state: ReviewState, delta: int, frame_count: int) -> ReviewState:
    return replace(state, frame=clamp_frame(state.frame + delta, frame_count))


def set_mode(state: ReviewState, mode: str) -> ReviewState:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    return replace(state, mode=mode, message=f"mode: {mode}")


def apply_click(state: ReviewState, u_px: float, v_px: float, t_pts_s: float) -> ReviewState:
    """Record a click for the current mode on the current frame."""
    click = Click(state.frame, t_pts_s, u_px, v_px)
    mode = state.mode
    if mode == "landmarks":
        mark = LandmarkMark(click.frame, t_pts_s, state.landmark_id, u_px, v_px)
        return replace(
            state,
            landmark_marks=(*state.landmark_marks, mark),
            history=(*state.history, "landmarks"),
            message=f"{state.landmark_id} marked on frame {click.frame}"
            + (_edge_summary(state, mark) if is_edge_id(mark.landmark_id) else ""),
        )
    if mode == "robot":
        new = replace(state, robot=click)
    elif mode == "launch":
        new = replace(state, launch=click)
    elif mode == "track":
        new = replace(state, track=(*state.track, click))
    elif mode == "landing":
        new = replace(state, landing=click)
    else:  # outcome mode takes keys, not clicks
        return replace(state, message="outcome mode: press m, x or u")
    return replace(new, history=(*state.history, mode), message=f"{mode} click on {click.frame}")


def _edge_summary(state: ReviewState, mark: LandmarkMark) -> str:
    counts = edge_point_counts((*state.landmark_marks, mark))
    return " (edges: " + ", ".join(f"{k[5:]} {v}" for k, v in counts.items()) + ")"


def undo(state: ReviewState) -> ReviewState:
    """Remove the most recent click. A replaced robot/launch/landing click is cleared."""
    if not state.history:
        return replace(state, message="nothing to undo")
    kind = state.history[-1]
    rest = state.history[:-1]
    if kind == "landmarks":
        new = replace(state, landmark_marks=state.landmark_marks[:-1])
    elif kind == "track":
        new = replace(state, track=state.track[:-1])
    elif kind in ("robot", "launch", "landing"):
        new = replace(state, **{kind: None})
    else:
        new = state
    return replace(new, history=rest, message=f"undid {kind}")


def new_draft(state: ReviewState) -> ReviewState:
    """Start the next shot: keep the frame, landmark marks and robot click kind."""
    return ReviewState(
        frame=state.frame,
        mode="robot",
        robot_click_kind=state.robot_click_kind,
        landmark_id=state.landmark_id,
        landmark_marks=state.landmark_marks,
    )


def edge_point_counts(marks: tuple[LandmarkMark, ...]) -> dict[str, int]:
    """Number of clicked points per straight-edge id (all frames of the video)."""
    counts: dict[str, int] = {}
    for m in marks:
        if is_edge_id(m.landmark_id):
            counts[m.landmark_id] = counts.get(m.landmark_id, 0) + 1
    return counts


def cycle_landmark(state: ReviewState, step: int) -> ReviewState:
    """Select the next (+1) or previous (-1) landmark id, wrapping around."""
    ids = known_landmark_ids()
    i = ids.index(state.landmark_id) if state.landmark_id in ids else 0
    new_id = ids[(i + step) % len(ids)]
    return replace(state, landmark_id=new_id, message=f"landmark: {new_id}")


def missing_parts(state: ReviewState) -> list[str]:
    """Names of what a record still needs before it can be finished."""
    return [name for name in ("robot", "launch") if getattr(state, name) is None]


def build_observation(
    state: ReviewState, ctx: ReviewContext, observation_id: str, created_at: str
) -> ShotObservation:
    """Turn the draft into a record. Raises ReviewError when robot or launch is missing."""
    missing = missing_parts(state)
    if missing or state.robot is None or state.launch is None:
        raise ReviewError("record needs " + " and ".join(missing or ["robot", "launch"]))
    r = state.robot
    on_floor = state.robot_click_kind == "floor_contact"
    landing = None
    if state.landing is not None:
        z_in = HIVE_CELL_Z_IN if state.landing_kind == "hive_cell" else None
        if state.landing_kind == "floor":
            z_in = 0.0
        landing = Landing(
            state.landing.frame, state.landing.u_px, state.landing.v_px, state.landing_kind, z_in
        )
    track = sorted(state.track, key=lambda c: c.frame)
    return ShotObservation(
        observation_id=observation_id,
        video_sha256=ctx.video_sha256,
        robot=RobotClick(
            r.frame, r.u_px, r.v_px, state.robot_click_kind, 0.0 if on_floor else ctx.click_z_in
        ),
        launch=LaunchMark(state.launch.frame, state.launch.t_pts_s),
        ball_track=tuple(TrackPoint(c.frame, c.t_pts_s, c.u_px, c.v_px) for c in track),
        landing=landing,
        outcome=Outcome(result=state.result),
        event_code=ctx.event_code,
        match_label=ctx.match_label,
        alliance=ctx.alliance,
        team_number=ctx.team_number,
        operator=ctx.operator,
        created_at=created_at,
    )


def apply_key(state: ReviewState, key: str, frame_count: int) -> tuple[ReviewState, str | None]:
    """Handle one key. Returns the new state and a command for the app: finish, quit,
    delete_last or None."""
    if key in STEP_KEYS:
        return step_frame(state, STEP_KEYS[key], frame_count), None
    if key == "home":
        return replace(state, frame=0), None
    if key == "end":
        return replace(state, frame=clamp_frame(frame_count - 1, frame_count)), None
    if key in MODE_KEYS:
        return set_mode(state, MODE_KEYS[key]), None
    if key == "]":
        return cycle_landmark(state, 1), None
    if key == "[":
        return cycle_landmark(state, -1), None
    if key == "t":
        kind = CLICK_KINDS[(CLICK_KINDS.index(state.robot_click_kind) + 1) % len(CLICK_KINDS)]
        return replace(state, robot_click_kind=kind, message=f"robot click: {kind}"), None
    if key in LANDING_KEYS:
        kind = LANDING_KEYS[key]
        return replace(state, landing_kind=kind, message=f"landing kind: {kind}"), None
    if key in OUTCOME_KEYS:
        result = OUTCOME_KEYS[key]
        return replace(state, result=result, message=f"outcome: {result}"), None
    if key == "z":
        return undo(state), None
    if key == "enter":
        return state, "finish"
    if key == "delete":
        return state, "delete_last"
    if key == "q":
        return state, "quit"
    return state, None


def status_line(state: ReviewState, frame_count: int, n_saved: int) -> str:
    parts = [
        f"frame {state.frame}/{max(frame_count - 1, 0)}",
        f"mode {state.mode}" + (f" ({state.landmark_id})" if state.mode == "landmarks" else ""),
        f"landmarks {len(state.landmark_marks)}",
        *(
            [f"edge pts {edge_point_counts(state.landmark_marks).get(state.landmark_id, 0)}"]
            if state.mode == "landmarks" and is_edge_id(state.landmark_id)
            else []
        ),
        f"robot {'ok' if state.robot else '-'}",
        f"launch {'ok' if state.launch else '-'}",
        f"track {len(state.track)}",
        f"landing {state.landing_kind if state.landing else '-'}",
        f"result {state.result}",
        f"saved {n_saved}",
    ]
    line = " | ".join(parts)
    return f"{line}\n{state.message}" if state.message else line


# --- display check --------------------------------------------------------------------------


def require_display(
    backend: str, platform: str | None = None, environ: Mapping[str, str] | None = None
) -> None:
    """Raise ReviewError with a clear message when no interactive window can be opened."""
    platform = sys.platform if platform is None else platform
    env = os.environ if environ is None else environ
    if backend.lower() in NON_INTERACTIVE_BACKENDS:
        raise ReviewError(
            f"matplotlib backend {backend!r} is not interactive; install a GUI backend "
            "(e.g. PyQt6 or tkinter) and unset MPLBACKEND"
        )
    if platform.startswith("linux") and not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        raise ReviewError("no display found (DISPLAY/WAYLAND_DISPLAY unset); run on a desktop")


# --- app ------------------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ReviewApp:
    """Binds a ``VideoReader``, a matplotlib figure and the JSONL output to the state machine.

    ``on_key`` and ``on_click`` accept anything with matplotlib's event attributes
    (``key``, ``button``, ``inaxes``, ``xdata``, ``ydata``), so tests can inject events.
    """

    def __init__(
        self,
        reader: VideoReader,
        ctx: ReviewContext,
        out_path: Path,
        fig: Any,
        start_frame: int = 0,
        new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
        now: Callable[[], str] = _now_iso,
    ) -> None:
        self.reader = reader
        self.ctx = ctx
        self.out_path = out_path
        self.fig = fig
        self.ax = fig.gca()
        self._new_id = new_id
        self._now = now
        self.saved: list[ShotObservation] = read_jsonl(out_path) if out_path.exists() else []
        self.state = ReviewState(frame=clamp_frame(start_frame, ctx.frame_count))
        if self.landmarks_path.exists():
            marks = tuple(
                LandmarkMark(c.frame, c.t_pts_s, c.landmark_id, c.u_px, c.v_px)
                for c in read_landmarks_jsonl(self.landmarks_path)
                if c.video_sha256 == ctx.video_sha256
            )
            self.state = replace(self.state, landmark_marks=marks)
        self.quit_requested = False
        self._t_pts_s = 0.0
        self._image_artist: Any = None
        self._show_frame()

    @property
    def landmarks_path(self) -> Path:
        return self.out_path.with_name(self.out_path.stem + ".landmarks.jsonl")

    def _show_frame(self) -> None:
        frame = self.reader.read(self.state.frame)
        self._t_pts_s = frame.t_pts_s
        rgb = frame.image_bgr[..., ::-1]
        if self._image_artist is None:
            self._image_artist = self.ax.imshow(rgb)
        else:
            self._image_artist.set_data(rgb)
        self.redraw()

    def redraw(self) -> None:
        for line in list(self.ax.lines):
            line.remove()
        s = self.state
        here = s.frame

        def draw(clicks: list[Click], style: str) -> None:
            pts = [c for c in clicks if c.frame == here]
            if pts:
                self.ax.plot([c.u_px for c in pts], [c.v_px for c in pts], style)

        draw([c for c in (s.robot,) if c], "r+")
        draw([c for c in (s.launch,) if c], "yx")
        draw(list(s.track), "co")
        draw([c for c in (s.landing,) if c], "gs")
        marks = [m for m in s.landmark_marks if m.frame == here]
        if marks:
            self.ax.plot([m.u_px for m in marks], [m.v_px for m in marks], "m^")
            for m in marks:
                self.ax.annotate(m.landmark_id, (m.u_px, m.v_px), fontsize=6, color="m")
        self.ax.set_title(status_line(s, self.ctx.frame_count, len(self.saved)), fontsize=9)
        self.fig.canvas.draw_idle()

    def on_key(self, event: Any) -> None:
        key = getattr(event, "key", None)
        if not isinstance(key, str):
            return
        old_frame = self.state.frame
        n_marks = len(self.state.landmark_marks)
        self.state, command = apply_key(self.state, key, self.ctx.frame_count)
        if command == "quit":
            self.quit_requested = True
        elif command == "finish":
            self._finish()
        elif command == "delete_last":
            self._delete_last()
        if len(self.state.landmark_marks) < n_marks:  # undo of a landmark click
            self._rewrite_landmarks()
        if self.state.frame != old_frame:
            self._show_frame()
        else:
            self.redraw()

    def on_click(self, event: Any) -> None:
        if getattr(event, "button", None) != 1 or event.inaxes is not self.ax:
            return
        if event.xdata is None or event.ydata is None:
            return
        toolbar = getattr(self.fig.canvas, "toolbar", None)
        if toolbar is not None and getattr(toolbar, "mode", ""):
            return  # zoom or pan is active
        n_marks = len(self.state.landmark_marks)
        self.state = apply_click(self.state, float(event.xdata), float(event.ydata), self._t_pts_s)
        if len(self.state.landmark_marks) > n_marks:
            self._append_landmark(self.state.landmark_marks[-1])
        self.redraw()

    def _finish(self) -> None:
        try:
            obs = build_observation(self.state, self.ctx, self._new_id(), self._now())
        except ReviewError as exc:
            self.state = replace(self.state, message=str(exc))
            return
        append_jsonl(self.out_path, obs)
        self.saved.append(obs)
        self.state = replace(new_draft(self.state), message=f"saved {len(self.saved)} records")

    def _delete_last(self) -> None:
        if not self.saved:
            self.state = replace(self.state, message="no saved record to delete")
            return
        self.saved.pop()
        write_jsonl(self.out_path, self.saved)
        self.state = replace(self.state, message=f"deleted; {len(self.saved)} records remain")

    def _landmark_record(self, m: LandmarkMark, created_at: str) -> LandmarkClick:
        return LandmarkClick(
            self.ctx.video_sha256,
            m.frame,
            m.t_pts_s,
            m.landmark_id,
            m.u_px,
            m.v_px,
            self.ctx.operator,
            created_at,
        )

    def _append_landmark(self, mark: LandmarkMark) -> None:
        existing = read_landmarks_jsonl(self.landmarks_path) if self.landmarks_path.exists() else []
        existing.append(self._landmark_record(mark, self._now()))
        write_landmarks_jsonl(self.landmarks_path, existing)

    def _rewrite_landmarks(self) -> None:
        old = read_landmarks_jsonl(self.landmarks_path) if self.landmarks_path.exists() else []
        keep = old[: len(self.state.landmark_marks)]  # marks are appended in order
        write_landmarks_jsonl(self.landmarks_path, keep)


def calibration_ref(path: Path, camera_setup_id: str | None = None) -> CalibrationRef:
    """Reference to a calibration JSON. Only ``schema_version`` is read (2.1 owns the file)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read calibration {path}: {exc}") from exc
    version = data.get("schema_version") if isinstance(data, dict) else None
    return CalibrationRef(
        path.as_posix(), version if isinstance(version, int) else None, camera_setup_id
    )


def run_review(
    video: Path,
    out_path: Path,
    ctx_fields: Mapping[str, Any] | None = None,
    calibration: Path | None = None,
    camera_setup_id: str | None = None,
    start_frame: int = 0,
) -> int:
    """Open the review window and block until it is closed. Returns the saved record count."""
    import matplotlib

    require_display(matplotlib.get_backend())
    import matplotlib.pyplot as plt

    # check again: importing pyplot resolves the "auto" backend
    require_display(matplotlib.get_backend())
    for name in [k for k in plt.rcParams if k.startswith("keymap.")]:
        plt.rcParams[name] = []  # pyright: ignore[reportArgumentType]

    try:
        reader = VideoReader(video)
    except VideoError as exc:
        raise ReviewError(str(exc)) from exc
    with reader:
        ctx = ReviewContext(
            video_sha256=reader.sha256(),
            frame_count=reader.frame_count,
            **(ctx_fields or {}),
        )
        write_video_meta(
            out_path.with_name(out_path.stem + ".video.json"),
            VideoMeta(
                ctx.video_sha256,
                video.name,
                reader.info.width_px,
                reader.info.height_px,
                None if math.isnan(reader.info.fps_nominal) else reader.info.fps_nominal,
                reader.frame_count,
                None if calibration is None else calibration_ref(calibration, camera_setup_id),
            ),
        )
        fig = plt.figure(figsize=(12, 7))
        app = ReviewApp(reader, ctx, out_path, fig, start_frame=start_frame)
        fig.canvas.mpl_connect("key_press_event", app.on_key)
        fig.canvas.mpl_connect("button_press_event", app.on_click)
        fig.canvas.mpl_connect("close_event", lambda _e: setattr(app, "quit_requested", True))
        plt.show()
        return len(app.saved)
