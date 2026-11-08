"""Clock runs and overlay events on synthetic overlay streams written at test time (2.2b)."""

import json
import os

import numpy as np
import pytest

from alea.video.frames import VideoReader
from alea.video.overlay.__main__ import main as cli_main
from alea.video.overlay.clock import (
    ClockSample,
    extract_runs,
    read_clock_series,
    refine_run,
    runs_to_segments,
)
from alea.video.overlay.events import (
    EVENT_KEYS,
    EventsError,
    OverlayEvent,
    _Reading,
    _Tracker,
    extract_events,
    guess_kind,
    read_events_jsonl,
    write_events_jsonl,
    write_series_csv,
)
from alea.video.overlay.glyphs import GlyphSet
from alea.video.overlay.synth import (
    DeadAir,
    Flicker,
    MatchSpec,
    ScoreChange,
    make_synthetic_profile,
    synthetic_layout,
    tip,
    write_synthetic_stream,
)

pytest.importorskip("cv2")

FPS = 10.0


def _q1() -> MatchSpec:
    return MatchSpec(
        "Q1",
        transition_hold_s=8.0,
        changes=(
            ScoreChange(25.0, "red", "score", 3, "leave"),
            *tip(20.0, "red"),
            *tip(75.0, "blue"),
            ScoreChange(140.0, "red", "score", 5, "park"),
            *tip(100.0, "red"),
        ),
        flickers=(Flicker(50.0, "blue", 77),),
    )


def _q2() -> MatchSpec:
    return MatchSpec(
        "Q2",
        transition_hold_s=0.0,  # the clock does not hold at 2:00
        changes=(*tip(60.0, "blue"), ScoreChange(25.0, "blue", "score", 3, "leave")),
    )


@pytest.fixture(scope="module")
def top(tmp_path_factory):
    path = tmp_path_factory.mktemp("synth") / "top.avi"
    prof = make_synthetic_profile("top")
    try:
        truth = write_synthetic_stream(
            path, [DeadAir(10), _q1(), DeadAir(8), _q2(), DeadAir(6)], synthetic_layout("top"),
            fps=FPS, seed=1,
        )  # fmt: skip
    except RuntimeError as exc:
        pytest.skip(str(exc))
    return path, prof, truth


@pytest.fixture(scope="module")
def segments(top):
    path, prof, _ = top
    glyphs = GlyphSet.from_entries(prof.glyphs)
    with VideoReader(path) as r:
        series = read_clock_series(r, prof, glyphs, step_frames=7)
        raw_runs = extract_runs(series)
        runs = [refine_run(r, prof, glyphs, run) for run in raw_runs]
    return series, raw_runs, runs, runs_to_segments(runs)


def test_runs_match_truth_and_dead_air_gives_none(top, segments):
    _, _, truth = top
    _, raw_runs, runs, segs = segments
    assert len(runs) == 2 == len(segs) == len(truth.matches)
    errs = []
    for label, runs_ in (("coarse", raw_runs), ("refined", runs)):
        e = []
        for run, m in zip(runs_, truth.matches, strict=True):
            e += [abs(run.play_start_pts_s - m["play_start_pts_s"]),
                  abs(run.play_end_pts_s - m["play_end_pts_s"])]  # fmt: skip
        print(label, "boundary errors [s]:", [round(x, 3) for x in e])
        assert max(e) <= 1.5, label
        assert float(np.median(e)) <= 0.5, label
        errs += e
    # the first match has a transition hold: piecewise fit finds it, the second does not
    assert runs[0].transition_start_pts_s is not None
    assert runs[0].transition_end_pts_s - runs[0].transition_start_pts_s == pytest.approx(8, abs=1)
    assert runs[1].transition_start_pts_s is None
    for seg, m in zip(segs, truth.matches, strict=True):
        assert seg["start_pts_s"] >= m["start_pts_s"] - 1.0
        assert seg["start_pts_s"] <= m["play_start_pts_s"]
        assert not seg["needs_review"]
        assert set(seg) >= {"match_label", "start_pts_s", "play_start_pts_s", "play_end_pts_s",
                            "end_pts_s", "teams", "score", "confidence", "needs_review",
                            "evidence"}  # fmt: skip


def test_extract_runs_survives_misreads_and_gaps():
    # synthetic readings: true end at t=200, with misreads, gaps and a hold at 2:30 and 0:00
    t_end = 200.0
    series = []
    for t in np.arange(30.0, 230.0, 1.0):
        rem = t_end - t
        clock = 150 if rem > 150 else (0 if rem <= 0 else int(np.ceil(rem)))
        series.append(ClockSample(int(t), float(t), clock, 0.9))
    series[60] = ClockSample(60, 60.0, 17, 0.9)  # misread
    series[100] = ClockSample(100, 100.0, 149, 0.9)  # misread (increase)
    for i in range(120, 135):  # occlusion gap
        series[i] = ClockSample(i, float(i + 30), None, 0.0)
    runs = extract_runs(series)
    assert len(runs) == 1
    assert abs(runs[0].play_end_pts_s - t_end) < 0.7
    assert abs(runs[0].play_start_pts_s - (t_end - 150)) < 0.7


def test_second_layout_works_via_its_profile(tmp_path):
    prof = make_synthetic_profile("bottom")
    path = tmp_path / "bottom.avi"
    spec = MatchSpec("Q9", transition_hold_s=8.0, pre_hold_s=3.0, post_hold_s=2.0, results_s=1.0)
    truth = write_synthetic_stream(path, [DeadAir(4), spec], synthetic_layout("bottom"), fps=FPS)
    glyphs = GlyphSet.from_entries(prof.glyphs)
    with VideoReader(path) as r:
        runs = extract_runs(read_clock_series(r, prof, glyphs, step_frames=10))
    assert len(runs) == 1
    m = truth.matches[0]
    assert abs(runs[0].play_start_pts_s - m["play_start_pts_s"]) <= 1.5
    assert abs(runs[0].play_end_pts_s - m["play_end_pts_s"]) <= 1.5
    # without the banner anchor, the top profile's ROIs miss the bottom layout
    top_prof = make_synthetic_profile("top")
    top_prof.anchor = None
    with VideoReader(path) as r:
        series = read_clock_series(r, top_prof, GlyphSet.from_entries(top_prof.glyphs), 10)
    assert extract_runs(series) == []


@pytest.fixture(scope="module")
def events(top, segments):
    path, prof, _ = top
    glyphs = GlyphSet.from_entries(prof.glyphs)
    out = {}
    with VideoReader(path) as r:
        for seg in segments[3]:
            ev, rows = extract_events(r, prof, glyphs, seg)
            out[seg["segment_id"]] = (ev, rows)
    return out


def test_tip_events_recovered(top, events):
    _, _, truth = top
    all_ev = [e for ev, _ in events.values() for e in ev]
    for k, (ev, _) in enumerate(events.values()):
        label = truth.matches[k]["match_label"]
        want = [t for t in truth.events if t["match_label"] == label
                and t["field"] == "score" and t["delta"] == 20]  # fmt: skip
        assert want
        for t in want:
            hits = [
                e
                for e in ev
                if e.field == "score"
                and e.delta == 20
                and e.alliance == t["alliance"]
                and abs(e.t_new_pts_s - t["t_pts_s"]) <= 0.3
            ]
            assert len(hits) == 1, (t, ev)
            assert hits[0].kind_guess == "tip"
            assert hits[0].old == t["old"] and hits[0].new == t["new"]
            assert hits[0].confidence > 0.3
        # tips counter changes are found too, and corroborate
        tips_ev = [e for e in ev if e.field == "tips" and e.delta == 1]
        assert len(tips_ev) == len(want)
    assert {e.profile_id for e in all_ev} == {"synth-top-v1"}
    assert all(e.t_old_pts_s <= e.t_new_pts_s and e.t_new_pts_s - e.t_old_pts_s <= 0.21
               for e in all_ev)  # fmt: skip


def test_leave_in_auto_and_park_recovered(top, events):
    _, _, truth = top
    ev, _ = events["clock-000"]
    leave = [e for e in ev if e.field == "score" and e.delta == 3]
    assert len(leave) == 1 and leave[0].alliance == "red"
    assert leave[0].kind_guess == "leave" and leave[0].phase == "auto"
    t_true = next(
        t["t_pts_s"] for t in truth.events if t["kind"] == "leave" and t["match_label"] == "Q1"
    )
    assert abs(leave[0].t_new_pts_s - t_true) <= 0.3
    park = [e for e in ev if e.field == "score" and e.delta == 5]
    assert len(park) == 1 and park[0].kind_guess == "park" and park[0].phase == "endgame"
    # the second match (no transition hold) has its +3 in auto too
    ev2, _ = events["clock-001"]
    assert [e.kind_guess for e in ev2 if e.delta == 3] == ["leave"]


def test_flicker_does_not_make_an_event(events):
    ev, _ = events["clock-000"]
    assert not [e for e in ev if e.field == "score" and e.new == 77]
    blue_score = [e for e in ev if e.field == "score" and e.alliance == "blue"]
    assert [e.delta for e in blue_score] == [20]


def test_phase_and_clock_remaining(events):
    ev, _ = events["clock-000"]
    tip_auto = next(e for e in ev if e.field == "score" and e.alliance == "red" and e.delta == 20
                    and e.phase == "auto")  # fmt: skip
    assert 120 < tip_auto.clock_s_remaining <= 135
    teleop = next(e for e in ev if e.field == "score" and e.alliance == "blue" and e.delta == 20)
    assert teleop.phase == "teleop" and 80 < teleop.clock_s_remaining < 86


def test_series_csv_and_jsonl_round_trip(events, tmp_path):
    ev, rows = events["clock-000"]
    csv_path = tmp_path / "series.csv"
    write_series_csv(csv_path, rows)
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("frame,t_pts_s,phase,red_score")
    assert len(lines) == len(rows) + 1 and len(rows) > 500
    path = tmp_path / "ev.jsonl"
    write_events_jsonl(path, ev)
    again = read_events_jsonl(path)
    assert again == ev
    first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert tuple(first) == EVENT_KEYS
    assert first["schema_version"] == 1 and first["source"] == "overlay"
    assert len(first["video_sha256"]) == 64
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({**first, "extra": 1}) + "\n", encoding="utf-8")
    with pytest.raises(EventsError):
        read_events_jsonl(bad)
    bad.write_text(json.dumps({**first, "schema_version": 9}) + "\n", encoding="utf-8")
    with pytest.raises(EventsError):
        read_events_jsonl(bad)


# --- pure logic -------------------------------------------------------------------------------


def test_tracker_debounce():
    tr = _Tracker(3)
    seq = [5, 5, 5, 5, 9, 5, 5, 6, 6, None, 6, 6, 6, 5]
    got = []
    for i, v in enumerate(seq):
        ch = tr.push(i, _Reading(v, 0.5))
        if ch:
            got.append((ch["old"], ch["new"], ch["old_idx"], ch["new_idx"]))
    assert got == [(5, 6, 6, 7)]  # the lone 9 and the trailing lone 5 are rejected


@pytest.mark.parametrize(
    ("field", "old", "new", "phase", "rem", "kind"),
    [
        ("score", 0, 20, "teleop", 80, "tip"),
        ("score", 0, 3, "auto", 140, "leave"),
        ("score", 0, 3, "teleop", 80, "unknown"),
        ("score", 20, 25, "endgame", 10, "park"),
        ("score", 20, 22, "endgame", 40, "flower"),
        ("score", 20, 22, "teleop", 100, "unknown"),
        ("score", 20, 21, "post", 0, "garden"),
        ("score", 20, 60, "teleop", 80, "unknown"),  # two tips at once: composite
        ("score", 30, 20, "teleop", 80, "adjustment"),
        ("tips", 0, 1, "teleop", 80, "tip"),
        ("tips", 2, 1, "teleop", 80, "adjustment"),
        ("lock", 5, 4, "teleop", 80, "unknown"),
        ("lock", 3, 4, "teleop", 80, "adjustment"),
    ],
)
def test_guess_kind(field, old, new, phase, rem, kind):
    assert guess_kind(field, old, new, phase, rem) == kind


def test_event_dataclass_has_exactly_the_schema_keys():
    ev = OverlayEvent(1, "x" * 64, "Q1", "Q1-e000", "red", "score", 0, 20, 20, 1.0, 1.1, 90.0,
                      "teleop", "tip", 0.9, "p")  # fmt: skip
    assert tuple(ev.to_dict()) == EVENT_KEYS


# --- CLI --------------------------------------------------------------------------------------


def test_cli_end_to_end(top, tmp_path):
    path, prof, _ = top
    prof_path = tmp_path / "p.json"
    prof.write(prof_path)
    seg_path = tmp_path / "segments.json"
    assert cli_main(["clock", str(path), "--profile", str(prof_path), "--out", str(seg_path)]) == 0
    doc = json.loads(seg_path.read_text(encoding="utf-8"))
    assert doc["kind"] == "match_segments_draft" and doc["schema_version"] == 1
    assert len(doc["segments"]) == 2
    assert doc["segments"][0]["score"]["red_final"] is not None
    ev_path = tmp_path / "overlay_events.jsonl"
    assert cli_main(["events", str(path), "--profile", str(prof_path), "--segments",
                     str(seg_path), "--out", str(ev_path)]) == 0  # fmt: skip
    assert len(read_events_jsonl(ev_path)) > 4
    assert (tmp_path / "overlay_events.series.csv").is_file()


def test_cli_profile_init_and_learn_glyphs(top, tmp_path):
    path, _, _ = top
    out = tmp_path / "tpl.json"
    assert cli_main(["profile-init", str(path), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["glyphs"] == []


# --- opt-in smoke test on the user's local clip -----------------------------------------------


@pytest.mark.skipif(not os.environ.get("ALEA_LOCAL_CLIP"), reason="ALEA_LOCAL_CLIP not set")
def test_local_clip_smoke():  # pragma: no cover - needs the user's footage and a tuned profile
    clip = os.environ["ALEA_LOCAL_CLIP"]
    profile_path = os.environ.get("ALEA_LOCAL_PROFILE")
    if not profile_path:
        pytest.skip("set ALEA_LOCAL_PROFILE to a tuned profile JSON")
    from alea.video.overlay.profile import OverlayProfile

    prof = OverlayProfile.read(profile_path)
    glyphs = GlyphSet.from_entries(prof.glyphs)
    with VideoReader(clip) as r:
        series = read_clock_series(r, prof, glyphs, step_frames=max(1, round(r.info.fps_nominal)))
    runs = extract_runs(series)
    print(f"{len(series)} samples, {len(runs)} runs")
    assert runs, "no countdown found: tune the ROIs and glyphs on a frame first"
