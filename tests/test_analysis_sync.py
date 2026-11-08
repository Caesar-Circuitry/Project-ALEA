import pytest

from alea.analysis.hivelab import HiveLabShot, LogLaunch, to_measurements
from alea.analysis.sync import join_launches, match_offset, offset_from_cue
from alea.data.synthetic import synth_match

SHIFT_S = 37.123


def _truth():
    return synth_match(3).launch_times_s


def test_recovers_offset_with_missed_and_spurious():
    log = _truth()
    video = [t + SHIFT_S for t in log]
    del video[7]
    video.append(video[3] + 0.9)  # spurious
    res = match_offset(video, log)
    assert res.offset_s == pytest.approx(-SHIFT_S, abs=0.02)
    assert not res.ambiguous
    assert res.n_pairs == len(log) - 1


def test_periodic_is_ambiguous():
    log = [float(k) for k in range(10)]
    video = [0.3 + k for k in range(5)]
    assert match_offset(video, log).ambiguous


def test_cue_exact():
    assert offset_from_cue(12.5, 100.25) == 87.75


def test_join_leaves_spurious_unmatched():
    log = _truth()
    launches = [LogLaunch(t, 1000.0, 800.0, 200.0, launch_id=i) for i, t in enumerate(log)]
    video = [t + SHIFT_S + 0.03 for t in log[:5]] + [log[5] + SHIFT_S + 1.0]
    shots = [
        HiveLabShot("v.mp4", i, None, None, t, 200.0, 45.0, None, None, None, "IN")
        for i, t in enumerate(video)
    ]
    rows = join_launches(to_measurements(shots), launches, -SHIFT_S)
    assert [r.launch_id for r in rows[:5]] == [0, 1, 2, 3, 4]
    assert rows[5].launch_id is None and "no launch" in rows[5].notes
    assert rows[0].efficiency is not None
