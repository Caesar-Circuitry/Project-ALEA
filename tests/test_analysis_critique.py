"""Driver-critique features on synthetic logs (roadmap phase 4)."""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from alea.analysis.critique.__main__ import main
from alea.analysis.critique.features import (
    AUTO_S,
    MATCH_END_S,
    compute_features,
    phase_of,
)
from alea.analysis.critique.signals import MatchSignals
from alea.data.synthetic import synth_match

SEED = 3
UNIT_SUFFIXES = ("_s", "_min", "_in", "_deg", "_fraction", "_count", "_ticks_per_sec")


@pytest.fixture(scope="module")
def truth() -> list[float]:
    return synth_match(SEED).launch_times_s


@pytest.fixture(scope="module")
def sig() -> MatchSignals:
    return MatchSignals.from_synthetic(SEED)


def test_launch_count_and_times_match_truth(sig, truth) -> None:
    assert len(sig.launch_t_s) == len(truth)
    assert sig.launch_t_s == pytest.approx(truth, abs=0.021)
    assert len(sig.t_s) > 1000 and len(sig.drive_t_s) > 1000


def test_signals_equal_via_file_path(tmp_path, truth) -> None:
    path = tmp_path / "m.rlog"
    path.write_bytes(synth_match(SEED).data)
    assert len(MatchSignals.from_log(path).launch_t_s) == len(truth)


def test_cycle_statistics_match_truth(sig, truth) -> None:
    f = compute_features(sig)
    gaps = np.diff(truth)
    cycles = gaps[gaps >= 1.0]
    assert f.launch_count == len(truth)
    assert f.cycle_count == len(cycles)
    assert f.cycle_mean_s == pytest.approx(float(cycles.mean()), abs=0.05)
    assert f.cycle_median_s == pytest.approx(float(np.median(cycles)), abs=0.05)
    assert f.cycle_p90_s == pytest.approx(float(np.percentile(cycles, 90)), abs=0.05)
    assert sum(f.burst_size_count) == len(truth)
    assert f.burst_count == len(cycles) + 1
    assert f.launches_per_min == pytest.approx(len(truth) / (150.0 / 60.0), rel=0.01)
    assert sum(f.interval_hist_count) == len(gaps)
    assert f.quick_follow_fraction == pytest.approx(float(np.mean(gaps < 1.0)), abs=0.03)


def test_phases_partition_launches(sig) -> None:
    f = compute_features(sig)
    assert f.launch_auto_count + f.launch_teleop_count + f.launch_endgame_count == f.launch_count
    assert phase_of(0.0) == "auto" and phase_of(AUTO_S) == "teleop"
    assert phase_of(MATCH_END_S - 1) == "endgame"
    assert f.launch_auto_count > 0 and f.launch_endgame_count > 0


def test_no_idle_in_normal_match_and_idle_found_with_silence(sig) -> None:
    assert compute_features(sig).idle_gaps == []
    keep = (sig.launch_t_s < 50.0) | (sig.launch_t_s >= 70.0)
    gap_sig = replace(
        sig,
        launch_t_s=sig.launch_t_s[keep],
        launch_before_ticks_per_sec=sig.launch_before_ticks_per_sec[keep],
    )
    f = compute_features(gap_sig)
    assert len(f.idle_gaps) == 1
    assert f.idle_longest_s >= 19.0
    assert f.idle_longest_start_t_s is not None
    assert 45.0 < f.idle_longest_start_t_s < 51.0
    assert f.idle_total_s == pytest.approx(f.idle_longest_s)
    assert f.idle_drive_idle_fraction is not None
    assert 0.0 <= f.idle_drive_idle_fraction <= 1.0


def test_idle_drive_overlap_uses_drive_signal() -> None:
    t = np.arange(0, 100, 0.02)
    s = MatchSignals(
        duration_s=100.0,
        launch_t_s=np.array([5.0, 40.0]),
        drive_t_s=t,
        drive_ticks_per_sec=np.where(t < 20.0, 0.0, 500.0),
    )
    f = compute_features(s)
    assert [round(g["start_t_s"]) for g in f.idle_gaps] == [5, 40]  # type: ignore[type-var]
    # gap 5-40: still 15 s of 35 s; gap 40-100: moving
    assert f.idle_gaps[0]["drive_idle_fraction"] == pytest.approx(15 / 35, abs=0.01)
    assert f.idle_gaps[1]["drive_idle_fraction"] == pytest.approx(0.0)


def test_flywheel_and_aim_in_plausible_ranges(sig) -> None:
    f = compute_features(sig)
    assert -0.05 <= f.flywheel_shortfall_mean_fraction <= 0.5  # type: ignore[operator]
    assert 0.0 <= f.flywheel_low_launch_fraction <= 1.0  # type: ignore[operator]
    assert f.flywheel_shortfall_max_fraction >= f.flywheel_shortfall_mean_fraction  # type: ignore[operator]
    assert f.spinup_wait_mean_s is None or 0.0 <= f.spinup_wait_mean_s < 10.0
    assert 0.0 <= f.aimed_and_in_range_fraction <= f.aimed_fraction <= 1.0  # type: ignore[operator]
    assert f.heading_error_abs_mean_deg >= 0.0  # type: ignore[operator]
    assert 25.0 <= f.distance_min_in <= f.distance_mean_in <= f.distance_max_in <= 80.0  # type: ignore[operator]
    assert f.distance_sd_in > 0.0  # type: ignore[operator]


def test_low_flywheel_flagged(sig) -> None:
    low = replace(sig, launch_before_ticks_per_sec=sig.launch_before_ticks_per_sec * 0.8)
    assert compute_features(low).flywheel_low_launch_fraction == pytest.approx(1.0)


def test_empty_signals_do_not_crash() -> None:
    f = compute_features(MatchSignals(duration_s=60.0))
    assert f.launch_count == 0 and f.cycle_mean_s is None
    assert len(f.idle_gaps) == 1
    json.dumps(f.to_dict())
    assert f.summary_lines()


def _numeric_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _numeric_keys(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _numeric_keys(v, path)
    elif isinstance(obj, int | float) and not isinstance(obj, bool):
        yield path


def test_to_dict_json_and_units(sig) -> None:
    d = compute_features(sig).to_dict()
    json.loads(json.dumps(d))
    names = set(_numeric_keys(d))
    assert names
    for name in names:
        assert name.endswith(UNIT_SUFFIXES) or name.endswith("_per_min"), name


def test_summary_lines_contain_numbers(sig) -> None:
    lines = compute_features(sig).summary_lines()
    assert any(f"{len(sig.launch_t_s)} launches" in ln for ln in lines)
    assert all(isinstance(ln, str) and ln for ln in lines)


def test_cli_synthetic_writes_json(tmp_path, capsys) -> None:
    out = tmp_path / "sub" / "f.json"
    assert main(["--synthetic", "3", "--json", str(out)]) == 0
    assert "launches" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["launch_count"] > 10


def test_cli_reads_log_file(tmp_path) -> None:
    path = tmp_path / "m.rlog"
    path.write_bytes(synth_match(1).data)
    out = tmp_path / "f.json"
    assert main([str(path), "--json", str(out)]) == 0
    assert out.exists()
