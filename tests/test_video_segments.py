"""Match-segment schema v1: round trip, invariants, CSV export, CLI (roadmap stage 2.2b)."""

import csv
import json
from dataclasses import replace
from typing import Any

import pytest

from alea.video.segment.__main__ import main
from alea.video.segment.segments import (
    SEGMENT_CSV_COLUMNS,
    EventRef,
    MatchSegment,
    ScheduleMatchRef,
    Score,
    SegmentError,
    SegmentFile,
    StreamClock,
    VideoRef,
    export_csv,
    read_json,
    segments_csv_rows,
    write_json,
)


def make_segment(n: int = 1, **kw) -> MatchSegment:
    base: dict[str, Any] = dict(
        segment_id=f"seg-{n}",
        match_label=f"Q{n}",
        match_label_raw=f"Qualification {n} of 14",
        tournament_level="Quals",
        series=0,
        match_number=n,
        start_pts_s=100.0 * n,
        play_start_pts_s=100.0 * n + 10,
        play_end_pts_s=100.0 * n + 40,
        end_pts_s=100.0 * n + 50,
        red_teams=(10001, 10002),
        blue_teams=(10003, 10004),
        score=Score(24, 28),
        schedule_match=ScheduleMatchRef(True, "2026-10-24T15:01:30Z"),
        confidence=0.9,
        needs_review=False,
        evidence={"clock": {"present": True, "fit_rms_s": 0.2}},
    )
    base.update(kw)
    return MatchSegment(**base)


def make_file(*segments: MatchSegment) -> SegmentFile:
    return SegmentFile(
        video=VideoRef("clip.mp4", "ab" * 32, 1920, 1080, 30.0, 600.0),
        event=EventRef("TESTEVT", 2026, "ftcscout", "cd" * 32),
        profile_id="test-profile",
        segments=segments or (make_segment(1), make_segment(2)),
        stream_clock=StreamClock("2026-10-24T15:00:00+00:00"),
    )


def test_json_round_trip(tmp_path) -> None:
    sf = make_file()
    path = tmp_path / "sub" / "segments.json"
    write_json(path, sf)
    assert read_json(path) == sf
    assert not path.with_name(path.name + ".tmp").exists()
    assert json.loads(path.read_text(encoding="utf-8"))["segments"][0]["teams"] == {
        "red": [10001, 10002],
        "blue": [10003, 10004],
    }


def test_schema_version_mismatch_raises(tmp_path) -> None:
    d = make_file().to_dict()
    d["schema_version"] = 2
    with pytest.raises(SegmentError, match="schema_version"):
        SegmentFile.from_dict(d)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(SegmentError, match=r"bad.json"):
        read_json(path)


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_pts_s": 500.0},  # start after play_start
        {"play_end_pts_s": 110.0},  # play_end == play_start
        {"end_pts_s": 120.0},  # end before play_end
        {"confidence": 1.5},
        {"confidence": -0.1},
        {"match_label": "Q9"},  # Quals label must match match_number
        {"match_label": "6 bad"},
        {"tournament_level": "Bogus"},
        {"start_pts_s": -1.0},
    ],
)
def test_invariants_raise(overrides) -> None:
    with pytest.raises(SegmentError):
        make_segment(1, **overrides)


def test_playoff_label_kept_raw() -> None:
    seg = make_segment(
        1,
        match_label="SF1-2",
        match_label_raw="Semifinal 1 Match 2",
        tournament_level="Semis",
        series=1,
        match_number=2,
    )
    assert read_json_roundtrip(seg).match_label == "SF1-2"


def read_json_roundtrip(seg: MatchSegment) -> MatchSegment:
    return MatchSegment.from_dict(json.loads(json.dumps(seg.to_dict())))


def test_duplicate_segment_ids_raise() -> None:
    with pytest.raises(SegmentError, match="duplicate"):
        make_file(make_segment(1), replace(make_segment(2), segment_id="seg-1"))


def test_bad_team_number_raises() -> None:
    d = make_segment(1).to_dict()
    d["teams"]["red"] = [0]
    with pytest.raises(SegmentError, match="team number"):
        MatchSegment.from_dict(d)


def test_csv_export_columns(tmp_path) -> None:
    sf = make_file(make_segment(1), make_segment(2, score=None, schedule_match=None))
    assert tuple(segments_csv_rows(sf)[0]) == SEGMENT_CSV_COLUMNS
    path = export_csv(sf, tmp_path / "segments.csv")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert tuple(rows[0]) == SEGMENT_CSV_COLUMNS
    assert rows[0]["red_teams"] == "10001;10002"
    assert rows[0]["play_start_pts_s"] == "110.0"
    assert rows[1]["red_final"] == "" and rows[1]["schedule_matched"] == ""
    assert all(c.endswith("_s") for c in SEGMENT_CSV_COLUMNS if "pts" in c)


def test_cli_list_validate(tmp_path, capsys) -> None:
    path = tmp_path / "segments.json"
    write_json(path, make_file())
    assert main(["validate", str(path)]) == 0
    assert "2 segments" in capsys.readouterr().out
    assert main(["list", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Q1" in out and "10001+10002 v 10003+10004" in out and "24-28" in out


def test_cli_validate_reports_error(tmp_path, capsys) -> None:
    path = tmp_path / "segments.json"
    path.write_text("{}", encoding="utf-8")
    assert main(["validate", str(path)]) == 2
    assert "error" in capsys.readouterr().err
