import csv
import json

import pytest

from alea.analysis.reflection import __main__ as cli
from alea.analysis.reflection.baseline import Baseline, expected_points
from alea.analysis.reflection.overlay_events import (
    read_overlay_events,
    synth_overlay_events,
    write_overlay_events,
)
from alea.analysis.reflection.prompt import build_prompt, estimate_tokens
from alea.analysis.reflection.report import build_report, validate_report, write_report
from alea.analysis.reflection.timeline import (
    LaunchEvent,
    align_log_to_match,
    build_timeline,
    idle_gaps,
    launches_from_log,
)
from alea.data import rlog
from alea.data.synthetic import synth_match


def _good_launches():
    return [
        LaunchEvent(
            t_s=5.0 + 3.0 * i,
            distance_in=40.0,
            aimed=True,
            setpoint_ticks_per_sec=1000.0,
            flywheel_before_ticks_per_sec=1000.0,
        )
        for i in range(30)
    ]


def _bad_launches():
    ts = [5.0 + 3.0 * i for i in range(5)] + [37.0 + 3.0 * i for i in range(5)]  # 20 s gap
    return [
        LaunchEvent(
            t_s=t,
            distance_in=72.0,
            aimed=True,
            setpoint_ticks_per_sec=1000.0,
            flywheel_before_ticks_per_sec=800.0,
        )
        for t in ts
    ]


def _titles(report):
    return {f["title"] for f in report["findings"]}


def test_timeline_launch_count_matches_synthetic():
    synth = synth_match(1)
    launches, _ = launches_from_log(rlog.decode(synth.data))
    assert abs(len(launches) - len(synth.launch_times_s)) <= 1
    first = launches[0]
    assert first.distance_in is not None and first.setpoint_ticks_per_sec is not None
    assert first.aimed is not None


def test_idle_gap_detection():
    gaps = idle_gaps([0.0, 3.0, 6.0, 26.0, 29.0])
    assert len(gaps) == 1 and gaps[0].start_s == 6.0 and gaps[0].length_s == 20.0
    tl = build_timeline(_bad_launches())
    assert max(g.length_s for g in tl.idle_gaps) == pytest.approx(20.0)


def test_overlay_round_trip_and_tips(tmp_path):
    synth = synth_match(2)
    events = synth_overlay_events(synth.launch_times_s, 2, tip_times_match_s=(100.0,))
    assert events == synth_overlay_events(synth.launch_times_s, 2, tip_times_match_s=(100.0,))
    path = tmp_path / "ev.jsonl"
    write_overlay_events(events, path)
    assert read_overlay_events(path) == events
    launches, _ = launches_from_log(rlog.decode(synth.data))
    tl = build_timeline(launches, events, "red")
    tips = [e for e in tl.events() if e.kind == "tip"]
    assert len(tips) == 1 and tips[0].source == "measured"
    assert tl.final_score_pts is not None


def test_overlay_reader_rejects_bad_schema(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"schema_version": 2}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        read_overlay_events(path)


def test_alignment_recovers_offset():
    synth = synth_match(4)
    for shift in (7.5, 0.0, 12.0):
        events = synth_overlay_events(synth.launch_times_s, 4, offset_s=shift, make_prob=0.6)
        reds = [e for e in events if e.alliance == "red"]
        offset, source = align_log_to_match(synth.launch_times_s, reds)
        assert source == "measured"
        assert offset == pytest.approx(shift, abs=0.5)


def test_no_overlay_means_inferred():
    tl = build_timeline(_good_launches())
    assert tl.offset_source == "inferred" and tl.phases_source == "inferred"
    assert all(e.source == "inferred" for e in tl.events())
    report = build_report(tl, Baseline.placeholder(), {})
    assert any(g["what"] == "overlay events" for g in report["gaps"])


def test_report_valid_and_serialisable(tmp_path):
    synth = synth_match(5)
    launches, _ = launches_from_log(rlog.decode(synth.data))
    events = synth_overlay_events(synth.launch_times_s, 5, tip_times_match_s=(90.0,))
    tl = build_timeline(launches, events, "red")
    meta = {"event_code": None, "match_label": "Q7", "alliance": "red", "team_number": 24331}
    report = build_report(tl, Baseline.placeholder(), meta)
    assert validate_report(report) == []
    json.dumps(report)
    for name in (
        "launch_count",
        "cycle_time_mean_s",
        "cycle_time_p90_s",
        "longest_idle_gap_s",
        "fraction_launches_under_setpoint",
        "fraction_aimed",
        "mean_distance_in",
        "expected_made_balls",
        "tips_observed",
        "points_vs_expected_pts",
    ):
        assert report["metrics"][name]["source"] in ("measured", "inferred")
    assert report["metrics"]["expected_made_balls"]["source"] == "inferred"
    write_report(report, tmp_path / "r.json")
    broken = dict(report, schema_version=2)
    assert validate_report(broken)


def test_findings_bad_vs_good():
    base = Baseline.placeholder()
    bad = build_report(build_timeline(_bad_launches()), base, {})
    titles = _titles(bad)
    assert "Long gap without a launch" in titles
    assert "Firing before the flywheel is up to speed" in titles
    assert "Many shots from far away" in titles
    assert next(f for f in bad["findings"] if f["title"].startswith("Long"))["severity"] == "high"
    good = build_report(build_timeline(_good_launches()), base, {})
    assert good["findings"] == []


def test_no_tip_finding():
    synth = synth_match(6)
    launches, _ = launches_from_log(rlog.decode(synth.data))
    events = synth_overlay_events(synth.launch_times_s, 6)
    report = build_report(build_timeline(launches, events, "red"), Baseline.placeholder(), {})
    assert "No tip although the alliance was scoring balls" in _titles(report)


def test_no_log_report():
    tl = build_timeline([], None, None, log_present=False)
    report = build_report(tl, Baseline.placeholder(), {})
    assert validate_report(report) == []
    assert "launch_count" not in report["metrics"]
    assert any(g["what"] == "robot log" and g["filled_by"] == "none" for g in report["gaps"])


def test_prompt_contents():
    report = build_report(build_timeline(_bad_launches()), Baseline.placeholder(), {})
    prompt = build_prompt(report)
    assert json.dumps(report, indent=2) in prompt
    assert "inferred" in prompt and "exactly 3 concrete" in prompt
    for bad in ("/home", "\\", ".rlog", ".jsonl", "C:"):
        assert bad not in prompt
    assert estimate_tokens("a" * 40) == 10


def _write_summary(path, rows):
    keys = [
        "id",
        "aim_deg",
        "speed_pct",
        "robot_ips",
        "ball_in",
        "bounce",
        "shots",
        "fired",
        "scored",
        "pct_fired",
        "pct_scored_of_fired",
        "plus_minus_95",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_baseline_from_summary(tmp_path):
    def row(i, pct):
        return dict(
            id=i,
            aim_deg=1,
            speed_pct=2,
            robot_ips=0,
            ball_in=2.8,
            bounce=0.45,
            shots=100,
            fired=90,
            scored=45,
            pct_fired=90,
            pct_scored_of_fired=pct,
            plus_minus_95=1,
        )

    _write_summary(tmp_path / "summary.csv", [row(0, 60.0), row(1, 20.0)])
    for src in (tmp_path, tmp_path / "summary.csv"):
        b = Baseline.from_summary(src)
        assert b.source == "inferred"
        assert b.mean_p_make == pytest.approx(0.6, abs=0.02)
        assert b.make_probability(24) > b.make_probability(80)
    tl = build_timeline(_good_launches())
    exp = expected_points(tl, Baseline.placeholder())
    assert exp.expected_total_pts == pytest.approx(exp.expected_made_balls * 2)
    assert exp.points_vs_expected_pts is None


def test_cli_synthetic(tmp_path):
    assert cli.main(["--synthetic", "3", "--out", str(tmp_path)]) == 0
    for name in ("report.json", "report.md", "prompt.txt"):
        assert (tmp_path / name).stat().st_size > 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert validate_report(report) == []
    assert report["metrics"]["log_to_match_offset_s"]["value"] == pytest.approx(2.5, abs=0.5)
