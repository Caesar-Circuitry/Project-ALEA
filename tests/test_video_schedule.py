"""FTCScout schedule loader, expected video times, joins and affine fit (stage 2.2b)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from alea.video.segment.__main__ import main
from alea.video.segment.schedule import (
    ScheduleError,
    expected_video_times,
    fit_affine_utc_to_video,
    label_for,
    load_ftcscout_matches,
    match_segments_to_schedule,
)
from alea.video.segment.segments import Score, write_json
from tests.test_video_segments import make_file, make_segment

FIXTURE = Path(__file__).resolve().parent / "data" / "ftcscout_sample_matches.json"
STREAM_START = datetime(2026, 10, 24, 15, 0, 0, tzinfo=UTC)


def test_fixture_loads_with_labels() -> None:
    matches = load_ftcscout_matches(FIXTURE)
    assert [m.label for m in matches] == ["Q1", "Q2", "Q3", "Q4", "F1"]
    q1 = matches[0]
    assert q1.red_teams == (10001, 10002) and q1.blue_teams == (10003, 10004)
    assert (q1.red_score, q1.blue_score) == (24, 28)
    assert q1.actual_start_utc == datetime(2026, 10, 24, 15, 1, 30, tzinfo=UTC)
    q4 = matches[3]
    assert q4.actual_start_utc is None and q4.red_score is None
    assert matches[4].match_number == 1 and matches[4].tournament_level == "Finals"


def test_label_for_defaults_and_override() -> None:
    assert label_for("Quals", 0, 6) == "Q6"
    assert label_for("Semis", 1, 2) == "SF1-2"
    assert label_for("Finals", 0, 1) == "F1"
    assert label_for("Finals", 0, 1, {"Finals": "Final-{number}"}) == "Final-1"
    assert label_for("Mystery", 3, 4) == "Mystery3-4"


def test_malformed_schedule_raises(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"nope": 1}', encoding="utf-8")
    with pytest.raises(ScheduleError):
        load_ftcscout_matches(bad)


def test_expected_video_times() -> None:
    matches = load_ftcscout_matches(FIXTURE)
    t = expected_video_times(matches, STREAM_START)
    assert t["Q1"] == 90.0 and t["Q2"] == 540.0
    assert t["Q4"] is None
    shifted = expected_video_times(matches, STREAM_START, affine=(1.0, -12.5))
    assert shifted["Q1"] == 77.5


def test_join_by_label_teams_scores_with_one_mismatch() -> None:
    matches = load_ftcscout_matches(FIXTURE)
    good = make_segment(1)  # Q1, teams and score agree
    wrong = make_segment(2, red_teams=(10005, 10099), score=Score(40, 30))
    stray = make_segment(7)  # not in schedule
    joins = match_segments_to_schedule([good, wrong, stray], matches)
    by_label = {j.label: j for j in joins}
    assert by_label["Q1"].matched
    assert not by_label["Q2"].matched
    text = " ".join(by_label["Q2"].disagreements)
    assert "red teams" in text and "blue score 30 != schedule 31" in text
    assert by_label["Q7"].scheduled is None
    # Q3 and F1 were played but have no segment; Q4 was never played so is not listed.
    assert by_label["Q3"].segment_id is None and by_label["F1"].segment_id is None
    assert "Q4" not in by_label


def test_affine_fit_recovers_known_values() -> None:
    a, b = 1.0002, -12.4
    pairs = [(t, a * t + b) for t in (90.0, 540.0, 1200.0, 3000.0, 5000.0)]
    fit = fit_affine_utc_to_video(pairs)
    assert fit.a == pytest.approx(a, abs=1e-9)
    assert fit.b == pytest.approx(b, abs=1e-6)
    assert fit.rms_s < 1e-6 and fit.flags == ()


def test_affine_fit_flags_jump() -> None:
    pairs = [(t, t - 10.0) for t in range(0, 5000, 500)]
    pairs += [(t, t - 10.0 + 120.0) for t in range(5000, 10000, 500)]
    fit = fit_affine_utc_to_video(pairs)
    assert fit.flags and fit.rms_s > 20


def test_affine_single_anchor_and_empty() -> None:
    fit = fit_affine_utc_to_video([(100.0, 90.0)])
    assert (fit.a, fit.b) == (1.0, -10.0)
    with pytest.raises(Exception, match="at least one"):
        fit_affine_utc_to_video([])


def test_cli_check_schedule(tmp_path, capsys) -> None:
    path = tmp_path / "segments.json"
    write_json(path, make_file(make_segment(1), make_segment(2, red_teams=(10005, 10099))))
    assert main(["check-schedule", str(path), str(FIXTURE)]) == 1
    out = capsys.readouterr().out
    assert "Q1       ok" in out and "Q2       DISAGREE" in out and "red teams" in out
    assert "no segment for played match" in out
