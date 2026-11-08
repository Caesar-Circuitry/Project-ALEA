"""Click-log schema: JSONL round trip, validation, versioning, CSV export (phase 2)."""

import csv
import json

import pytest

from alea.video.clicklog import (
    LAUNCH_CSV_COLUMNS,
    SCHEMA_VERSION,
    TRACK_CSV_COLUMNS,
    CalibrationRef,
    ClickLogError,
    Landing,
    LandmarkClick,
    LaunchMark,
    Outcome,
    RobotClick,
    ShotObservation,
    TrackPoint,
    VideoMeta,
    append_jsonl,
    dumps_record,
    export_csv,
    latest_landmark_clicks,
    loads_record,
    read_jsonl,
    read_landmarks_jsonl,
    read_video_meta,
    write_jsonl,
    write_landmarks_jsonl,
    write_video_meta,
)


def make_obs(n: int = 0) -> ShotObservation:
    return ShotObservation(
        observation_id=f"obs-{n}",
        video_sha256="ab" * 32,
        robot=RobotClick(1234, 877.0, 640.0, "top_plate_centre", 16.0),
        launch=LaunchMark(1240, 41.374, 1),
        ball_track=(
            TrackPoint(1241, 41.408, 880.0, 600.0),
            TrackPoint(1242, 41.441, 884.0, 552.0),
        ),
        landing=Landing(1262, 1010.0, 500.0, "hive_cell", 49.13),
        outcome=Outcome("made", "RED_AUDIENCE", "ok"),
        event_code="USALTX",
        match_label="Q12",
        alliance="red",
        team_number=24331,
        operator="ab",
        created_at="2026-11-08T20:05:00Z",
    )


def test_round_trip_in_memory():
    obs = make_obs()
    assert loads_record(dumps_record(obs)) == obs


def test_round_trip_file_and_append(tmp_path):
    path = tmp_path / "shots.jsonl"
    write_jsonl(path, [make_obs(0)])
    append_jsonl(path, make_obs(1))
    assert read_jsonl(path) == [make_obs(0), make_obs(1)]
    assert not path.with_name("shots.jsonl.tmp").exists()


def test_optional_parts_round_trip():
    obs = ShotObservation(
        observation_id="x",
        video_sha256="00",
        robot=RobotClick(0, 1.0, 2.0, "floor_contact", 0.0),
        launch=LaunchMark(3, 0.1),
    )
    assert loads_record(dumps_record(obs)) == obs


def test_schema_version_mismatch_rejected():
    d = make_obs().to_dict()
    d["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(ClickLogError, match="schema_version"):
        ShotObservation.from_dict(d)
    del d["schema_version"]
    with pytest.raises(ClickLogError, match="schema_version"):
        ShotObservation.from_dict(d)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("robot", "frame"), -1),
        (("robot", "frame"), True),
        (("robot", "u_px"), float("nan")),
        (("robot", "u_px"), "12"),
        (("robot", "click_kind"), "elbow"),
        (("launch", "t_pts_s"), -0.5),
        (("landing", "kind"), "moon"),
        (("outcome", "result"), "won"),
        (("alliance",), "green"),
        (("team_number",), 0),
    ],
)
def test_bad_values_rejected(path, value):
    d = make_obs().to_dict()
    target = d
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ClickLogError):
        ShotObservation.from_dict(d)


def test_floor_contact_needs_zero_height():
    d = make_obs().to_dict()
    d["robot"]["click_kind"] = "floor_contact"
    with pytest.raises(ClickLogError, match="floor_contact"):
        ShotObservation.from_dict(d)


def test_decreasing_track_frames_rejected():
    d = make_obs().to_dict()
    d["ball_track"].reverse()
    with pytest.raises(ClickLogError, match="decrease"):
        ShotObservation.from_dict(d)


def test_missing_robot_rejected():
    d = make_obs().to_dict()
    del d["robot"]
    with pytest.raises(ClickLogError, match="robot"):
        ShotObservation.from_dict(d)


def test_read_error_names_line(tmp_path):
    path = tmp_path / "bad.jsonl"
    good = dumps_record(make_obs())
    path.write_text(f"{good}\n\nnot json\n", encoding="utf-8")
    with pytest.raises(ClickLogError, match=r"bad\.jsonl:3"):
        read_jsonl(path)


def test_unknown_extra_keys_ignored():
    d = make_obs().to_dict()
    d["derived"] = {"exit_speed_in_s": 1.0}
    assert ShotObservation.from_dict(json.loads(json.dumps(d))) == make_obs()


def test_csv_export_columns_and_rows(tmp_path):
    launches, tracks = export_csv([make_obs(0), make_obs(1)], tmp_path / "out")
    with launches.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert tuple(rows[0]) == LAUNCH_CSV_COLUMNS
    assert [r["observation_id"] for r in rows] == ["obs-0", "obs-1"]
    assert rows[0]["n_track_points"] == "2"
    assert rows[0]["landing_kind"] == "hive_cell"
    with tracks.open(encoding="utf-8", newline="") as fh:
        trows = list(csv.DictReader(fh))
    assert tuple(trows[0]) == TRACK_CSV_COLUMNS
    assert len(trows) == 4


def test_shot_record_carries_no_calibration():
    d = make_obs().to_dict()
    assert not any("calib" in k for k in d)


def _lm(frame=10, lid="field_floor_corner_xlo_ylo", u=100.0, v=200.0):
    return LandmarkClick("ab" * 32, frame, frame / 30, lid, u, v, "ab", "2026-11-08T00:00:00Z")


def test_landmark_round_trip_and_pooling(tmp_path):
    path = tmp_path / "s.landmarks.jsonl"
    clicks = [_lm(10), _lm(500, "hive_red_pivot"), _lm(10, u=101.0), _lm(7, "custom_tile_seam_3")]
    write_landmarks_jsonl(path, clicks)
    assert read_landmarks_jsonl(path) == clicks
    pooled = latest_landmark_clicks(clicks)
    assert len(pooled) == 3  # the re-click on frame 10 replaced the first
    assert [c.frame for c in pooled] == [7, 10, 500]
    assert [c.u_px for c in pooled if c.frame == 10] == [101.0]


@pytest.mark.parametrize("lid", ["hive_green_pivot", "Custom_x", "custom_", "", "(0,0,0)"])
def test_landmark_id_must_be_known(lid):
    d = _lm().to_dict()
    d["landmark_id"] = lid
    with pytest.raises(ClickLogError, match="landmark_id"):
        LandmarkClick.from_dict(d)


def test_landmark_version_and_values():
    d = _lm().to_dict()
    d["schema_version"] = 99
    with pytest.raises(ClickLogError, match="schema_version"):
        LandmarkClick.from_dict(d)
    d = _lm().to_dict()
    d["u_px"] = float("inf")
    with pytest.raises(ClickLogError):
        LandmarkClick.from_dict(d)


def test_video_meta_single_calibration_round_trip(tmp_path):
    meta = VideoMeta(
        "ab" * 32, "Q12.mp4", 1920, 1080, 29.97, 270000,
        CalibrationRef("cal/event1.json", 1, "event1_cam_a"),
    )  # fmt: skip
    path = tmp_path / "v.video.json"
    write_video_meta(path, meta)
    assert read_video_meta(path) == meta
    bare = VideoMeta("00", "x.mp4", 64, 48, None, 30)
    write_video_meta(path, bare)
    assert read_video_meta(path) == bare
    d = meta.to_dict()
    d["schema_version"] = 2
    with pytest.raises(ClickLogError):
        VideoMeta.from_dict(d)


def test_known_landmark_ids_are_unique_and_derived():
    from alea.video.landmark_ids import is_valid_landmark_id, known_landmark_ids

    ids = known_landmark_ids()
    assert len(ids) == len(set(ids)) == 4 + 4 + 2 + 8 + 4
    assert all(is_valid_landmark_id(i) for i in ids)


def test_cli_validate_and_export(tmp_path, capsys):
    from alea.video.__main__ import main

    shots = tmp_path / "shots.jsonl"
    write_jsonl(shots, [make_obs()])
    assert main(["validate", str(shots)]) == 0
    assert "1 valid" in capsys.readouterr().out
    assert main(["export-csv", str(shots), "--out-dir", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "launches.csv").exists()
    shots.write_text("{}\n", encoding="utf-8")
    assert main(["validate", str(shots)]) == 2
    assert main(["review", str(tmp_path / "missing.mp4")]) == 2
