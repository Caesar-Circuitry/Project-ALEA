import numpy as np
import pytest

from alea.game.biobuzz import LUT_DISTANCE_IN, LUT_TICKS_PER_SEC
from alea.matchsim.shots import (
    SIM_ASSUMED_EFFICIENCY,
    LutSpeedModel,
    PlaceholderShotModel,
    TableShotModel,
    sample_make,
)

HEADER = (
    "id,aim_deg,speed_pct,robot_ips,ball_in,bounce,shots,fired,scored,"
    "pct_fired,pct_scored_of_fired,plus_minus_95\n"
)


def test_lut_reproduces_game_points_exactly():
    lut = LutSpeedModel()
    for d, t in zip(LUT_DISTANCE_IN, LUT_TICKS_PER_SEC, strict=True):
        assert lut.ticks_per_s(d) == t
    mid = lut.ticks_per_s(26.0)
    assert min(1180, 1110) <= mid <= max(1180, 1110)
    assert lut.ticks_per_s(10) == LUT_TICKS_PER_SEC[0]
    assert lut.ticks_per_s(500) == LUT_TICKS_PER_SEC[-1]


def test_placeholder_probability_bounds_and_noise_monotone():
    lut = LutSpeedModel()
    for d in (24, 40, 60, 80, 120):
        p = PlaceholderShotModel().p_make(d, 0.0, lut.ticks_per_s(d))
        assert 0.0 <= p <= 1.0
    t = lut.ticks_per_s(40)
    quiet = PlaceholderShotModel(speed_noise_frac=0.01, aim_noise_deg=0.5).p_make(40, 0, t)
    noisy = PlaceholderShotModel(speed_noise_frac=0.08, aim_noise_deg=5.0).p_make(40, 0, t)
    assert quiet > noisy


def test_placeholder_efficiency_mismatch_and_geometry():
    t = LutSpeedModel().ticks_per_s(40)
    ok = PlaceholderShotModel(efficiency=SIM_ASSUMED_EFFICIENCY).p_make(40, 0, t)
    assert PlaceholderShotModel(efficiency=0.35).p_make(40, 0, t) < ok
    assert PlaceholderShotModel().p_make(40, 70, t) < ok
    assert PlaceholderShotModel().p_make(150, 0, t) < 0.05 * ok


def test_sample_make_uses_rng_deterministically():
    m = PlaceholderShotModel()
    t = LutSpeedModel().ticks_per_s(40)
    a = [sample_make(m, 40, 0, t, np.random.default_rng(3)) for _ in range(5)]
    b = [sample_make(m, 40, 0, t, np.random.default_rng(3)) for _ in range(5)]
    assert a == b


def test_table_model_from_tiny_summary(tmp_path):
    rows = [
        # id, aim, speed, robot, ball, bounce, shots, fired, scored, pct_fired, pct, pm
        (0, 1.0, 2.0, 0.0, 2.8, 0.45, 100, 100, 80, 100.0, 80.0, 1.0),
        (1, 1.0, 2.0, 0.0, 2.9, 0.60, 100, 100, 60, 100.0, 60.0, 1.0),
        (2, 2.0, 2.0, 0.0, 2.8, 0.45, 100, 100, 40, 100.0, 40.0, 1.0),
        (3, 1.0, 2.0, 10.0, 2.8, 0.45, 100, 100, 5, 100.0, 5.0, 1.0),
    ]
    (tmp_path / "summary.csv").write_text(
        HEADER + "\n".join(",".join(str(v) for v in r) for r in rows) + "\n", encoding="utf-8"
    )
    m = TableShotModel.from_study_summary(tmp_path, aim_deg=1.0, speed_pct=2.0)
    assert m.base_rate == pytest.approx(0.70)  # mean of the two robot-still rows at aim 1
    mid = TableShotModel.from_study_summary(tmp_path / "summary.csv", aim_deg=1.5, speed_pct=2.0)
    assert mid.base_rate == pytest.approx(0.55)  # halfway between 0.70 and 0.40
    moving = TableShotModel.from_study_summary(tmp_path, robot_speed_in_s=10.0)
    assert moving.base_rate == pytest.approx(0.05)
    t = LutSpeedModel().ticks_per_s(40)
    assert 0 < m.p_make(40, 0, t) <= m.base_rate
    assert m.p_make(40, 0, t) > mid.p_make(40, 0, t)


def test_table_model_rejects_empty():
    with pytest.raises(ValueError):
        TableShotModel({}, 1.0, 2.0)
