"""Review state machine (pure) and the matplotlib app on the Agg backend (phase 2)."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from alea.video.clicklog import read_jsonl, read_landmarks_jsonl
from alea.video.landmark_ids import known_landmark_ids
from alea.video.review import (
    HIVE_CELL_Z_IN,
    ReviewApp,
    ReviewContext,
    ReviewError,
    ReviewState,
    apply_click,
    apply_key,
    build_observation,
    calibration_ref,
    require_display,
    step_frame,
    undo,
)

CTX = ReviewContext(video_sha256="cd" * 32, frame_count=30, operator="ab")


def press(state: ReviewState, *keys: str) -> ReviewState:
    for key in keys:
        state, _ = apply_key(state, key, 30)
    return state


# --- pure state machine -----------------------------------------------------------------------


def test_frame_stepping_clamps():
    s = ReviewState()
    assert step_frame(s, -5, 30).frame == 0
    assert press(s, "up", "up", "up", "up").frame == 29
    assert press(s, "end").frame == 29
    assert press(s, "end", "home").frame == 0
    assert press(s, "right", "right", "left").frame == 1
    assert press(s, "pageup").frame == 29


def test_mode_keys_and_unknown_key():
    s = press(ReviewState(), "l")
    assert s.mode == "launch"
    assert apply_key(s, "F12", 30) == (s, None)


def test_clicks_go_to_the_current_mode():
    s = ReviewState(frame=3)
    s = apply_click(s, 10.0, 20.0, 0.1)  # robot mode
    s = press(s, "right", "l")
    s = apply_click(s, 11.0, 21.0, 0.13)
    s = press(s, "right", "b")
    s = apply_click(s, 12.0, 22.0, 0.17)
    s = apply_click(s, 13.0, 23.0, 0.17)
    s = press(s, "d")
    s = apply_click(s, 14.0, 24.0, 0.2)
    assert s.robot is not None and s.robot.frame == 3
    assert s.launch is not None and s.launch.frame == 4
    assert len(s.track) == 2
    assert s.landing is not None and s.landing.u_px == 14.0
    assert len(s.history) == 5


def test_outcome_mode_ignores_clicks():
    s = apply_click(press(ReviewState(), "o"), 1.0, 2.0, 0.0)
    assert not s.history


def test_undo_walks_back():
    s = press(ReviewState(), "b")
    s = apply_click(apply_click(s, 1.0, 1.0, 0.0), 2.0, 2.0, 0.0)
    s = undo(s)
    assert len(s.track) == 1
    s = undo(s)
    assert s.track == () and not s.has_draft
    assert undo(s).message == "nothing to undo"
    r = apply_click(ReviewState(), 5.0, 5.0, 0.0)
    assert undo(r).robot is None


def test_landmark_marks_are_separate_from_the_record():
    s = apply_click(press(ReviewState(), "c"), 5.0, 6.0, 0.0)
    assert len(s.landmark_marks) == 1 and s.robot is None
    assert s.landmark_marks[0].landmark_id == known_landmark_ids()[0]
    assert undo(s).landmark_marks == ()


def test_landmark_selection_cycles():
    ids = known_landmark_ids()
    s = press(ReviewState(), "c", "]")
    assert s.landmark_id == ids[1]
    assert press(s, "[", "[").landmark_id == ids[-1]
    s = apply_click(s, 1.0, 2.0, 0.0)
    assert s.landmark_marks[0].landmark_id == ids[1]


def test_calibration_ref_reads_only_version(tmp_path):
    p = tmp_path / "cal.json"
    p.write_text(json.dumps({"schema_version": 3, "camera": {}}), encoding="utf-8")
    ref = calibration_ref(p, "event1_cam_a")
    assert ref.calibration_version == 3 and ref.camera_setup_id == "event1_cam_a"
    with pytest.raises(ReviewError):
        calibration_ref(tmp_path / "missing.json")


def test_robot_click_kind_toggle_and_height():
    s = ReviewState(frame=1)
    s = apply_click(s, 1.0, 2.0, 0.0)
    s = press(s, "l")
    s = apply_click(s, 3.0, 4.0, 0.0)
    obs = build_observation(s, CTX, "id", "now")
    assert obs.robot.click_kind == "top_plate_centre" and obs.robot.click_z_in == CTX.click_z_in
    obs = build_observation(press(s, "t"), CTX, "id", "now")
    assert obs.robot.click_kind == "floor_contact" and obs.robot.click_z_in == 0.0


def test_build_requires_robot_and_launch():
    with pytest.raises(ReviewError, match="robot and launch"):
        build_observation(ReviewState(), CTX, "id", "now")
    s = apply_click(ReviewState(), 1.0, 1.0, 0.0)
    with pytest.raises(ReviewError, match="launch"):
        build_observation(s, CTX, "id", "now")


def test_landing_kind_sets_assumed_height():
    s = ReviewState()
    s = apply_click(s, 1.0, 1.0, 0.0)
    s = apply_click(press(s, "l"), 2.0, 2.0, 0.0)
    s = apply_click(press(s, "d", "2"), 3.0, 3.0, 0.0)  # key 2 = hive_cell
    landing = build_observation(s, CTX, "id", "now").landing
    assert landing is not None
    assert landing.kind == "hive_cell" and landing.z_in_assumed == HIVE_CELL_Z_IN
    landing = build_observation(press(s, "1"), CTX, "id", "now").landing
    assert landing is not None and landing.z_in_assumed == 0.0


def test_commands():
    s = ReviewState()
    assert apply_key(s, "enter", 30)[1] == "finish"
    assert apply_key(s, "q", 30)[1] == "quit"
    assert apply_key(s, "delete", 30)[1] == "delete_last"


@pytest.mark.parametrize(
    ("backend", "platform", "env", "ok"),
    [
        ("agg", "linux", {"DISPLAY": ":0"}, False),
        ("QtAgg", "linux", {}, False),
        ("QtAgg", "linux", {"WAYLAND_DISPLAY": "wayland-0"}, True),
        ("TkAgg", "win32", {}, True),
        ("MacOSX", "darwin", {}, True),
    ],
)
def test_require_display(backend, platform, env, ok):
    if ok:
        require_display(backend, platform, env)
    else:
        with pytest.raises(ReviewError):
            require_display(backend, platform, env)


# --- app on Agg with injected events ----------------------------------------------------------


class FakeReader:
    def __init__(self):
        self.reads: list[int] = []

    def read(self, index: int):
        self.reads.append(index)
        img = np.zeros((48, 64, 3), dtype=np.uint8)
        return SimpleNamespace(index=index, t_pts_s=index / 30.0, image_bgr=img)


def test_full_record_walk_writes_jsonl(tmp_path):
    pytest.importorskip("matplotlib")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure()
    FigureCanvasAgg(fig)
    fig.add_subplot()
    out = tmp_path / "shots.jsonl"
    reader = FakeReader()
    ids = iter(["a", "b"])
    app = ReviewApp(
        reader,  # type: ignore[arg-type]
        CTX,
        out,
        fig,
        new_id=lambda: next(ids),
        now=lambda: "2026-11-08T00:00:00Z",
    )

    def click(u, v, button=1, inaxes=True):
        app.on_click(
            SimpleNamespace(button=button, inaxes=app.ax if inaxes else None, xdata=u, ydata=v)
        )

    def key(k):
        app.on_key(SimpleNamespace(key=k))

    click(5.0, 5.0, inaxes=False)  # outside the axes: ignored
    click(5.0, 5.0, button=3)  # right button: ignored
    assert not app.state.history

    for _ in range(3):
        key("right")
    click(10.0, 20.0)  # robot at frame 3
    key("right")
    key("l")
    click(11.0, 21.0)  # launch at frame 4
    key("b")
    key("right")
    click(12.0, 22.0)
    key("right")
    click(13.0, 23.0)
    key("d")
    key("2")
    key("right")
    click(14.0, 24.0)
    key("m")
    key("enter")

    assert reader.reads[-1] == 7
    recs = read_jsonl(out)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.observation_id == "a"
    assert (rec.robot.frame, rec.robot.u_px, rec.robot.v_px) == (3, 10.0, 20.0)
    assert rec.launch.frame == 4 and rec.launch.t_pts_s == pytest.approx(4 / 30)
    assert [p.frame for p in rec.ball_track] == [5, 6]
    assert rec.landing is not None and rec.landing.kind == "hive_cell"
    assert rec.outcome.result == "made"
    assert not app.state.has_draft  # ready for the next shot

    # incomplete record is refused and nothing is written
    key("enter")
    assert "needs" in app.state.message
    assert len(read_jsonl(out)) == 1

    # delete removes the saved record, quit sets the flag
    key("delete")
    assert read_jsonl(out) == []
    key("q")
    assert app.quit_requested


def test_landmark_clicks_saved_undone_and_reloaded(tmp_path):
    pytest.importorskip("matplotlib")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    def make_app():
        fig = Figure()
        FigureCanvasAgg(fig)
        fig.add_subplot()
        return ReviewApp(FakeReader(), CTX, tmp_path / "s.jsonl", fig)  # type: ignore[arg-type]

    def click(app, u, v):
        app.on_click(SimpleNamespace(button=1, inaxes=app.ax, xdata=u, ydata=v))

    app = make_app()
    app.on_key(SimpleNamespace(key="c"))
    click(app, 1.0, 2.0)
    app.on_key(SimpleNamespace(key="]"))
    app.on_key(SimpleNamespace(key="right"))  # another frame of the same video is pooled
    click(app, 3.0, 4.0)
    saved = read_landmarks_jsonl(app.landmarks_path)
    assert [(c.frame, c.u_px) for c in saved] == [(0, 1.0), (1, 3.0)]
    assert saved[1].landmark_id == known_landmark_ids()[1]
    assert saved[0].video_sha256 == CTX.video_sha256

    app.on_key(SimpleNamespace(key="z"))
    assert len(read_landmarks_jsonl(app.landmarks_path)) == 1
    assert len(make_app().state.landmark_marks) == 1  # a new session reloads them

    app.on_key(SimpleNamespace(key="r"))
    click(app, 1.0, 2.0)
    app.on_key(SimpleNamespace(key="l"))
    click(app, 3.0, 2.0)
    app.on_key(SimpleNamespace(key="enter"))
    assert len(make_app().saved) == 1  # and the earlier shot record
