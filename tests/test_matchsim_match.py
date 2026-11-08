import dataclasses

import numpy as np

from alea.matchsim import rules
from alea.matchsim.match import BREAKDOWN_KEYS, simulate_match
from alea.matchsim.policies import ConstantCyclePolicy, NoOpPolicy
from alea.matchsim.robot import RobotProfile
from alea.matchsim.rules import TipBehaviour
from alea.matchsim.shots import PlaceholderShotModel

MODEL = PlaceholderShotModel()


def _match(red, seed, blue=None):
    blue = blue if blue is not None else [NoOpPolicy()]
    return simulate_match(red, blue, MODEL, seed)


def test_same_seed_identical_different_seed_differs():
    red = [RobotProfile(), ConstantCyclePolicy()]
    a, b = _match(red, 11), _match(red, 11)
    assert a.events == b.events
    assert (a.breakdown, a.tips, a.pollen_left) == (b.breakdown, b.tips, b.pollen_left)
    scores = {_match(red, s).red_score for s in range(8)}
    assert len(scores) > 1


def test_score_components_within_rule_bounds():
    for seed in range(15):
        r = _match([RobotProfile(), ConstantCyclePolicy()], seed, [ConstantCyclePolicy()])
        for a in ("red", "blue"):
            b = r.breakdown[a]
            assert all(b[k] >= 0 for k in b)
            assert b["total"] == sum(b[k] for k in BREAKDOWN_KEYS)
            assert b["tip_auto"] + b["tip_teleop"] == rules.POINTS_TIP_TELEOP * r.tips[a]
            assert b["tip_auto"] == rules.POINTS_TIP_AUTO * r.tips_auto[a]
            assert b["leave"] <= rules.POINTS_LEAVE * 2
            assert b["park_teleop"] <= rules.POINTS_PARK_TELEOP * 2
        assert 0 <= r.pollen_left <= rules.POLLEN_ON_FIELD
        times = [t for t, *_ in r.events]
        assert times == sorted(times)
        assert all(0 <= t <= rules.MATCH_END_S for t in times)


def test_no_scoring_in_transition():
    r = _match([RobotProfile(), ConstantCyclePolicy(start_s=0.0)], 4)
    for t, _, kind, _ in r.events:
        if kind in ("tip", "shot_made"):
            assert not (rules.AUTO_DURATION_S < t < rules.TELEOP_START_S)


def test_faster_robot_scores_at_least_as_much():
    slow = RobotProfile(drive_speed_in_s=20, intake_s_per_ball=1.5, shot_interval_s=1.2)
    fast = dataclasses.replace(
        slow, drive_speed_in_s=60, intake_s_per_ball=0.4, shot_interval_s=0.4
    )
    slow_mean = np.mean([_match([slow], s).red_score for s in range(50)])
    fast_mean = np.mean([_match([fast], s).red_score for s in range(50)])
    assert fast_mean >= slow_mean


def test_more_accurate_shot_model_scores_at_least_as_much():
    robot = [RobotProfile()]
    good = PlaceholderShotModel(speed_noise_frac=0.01, aim_noise_deg=0.5)
    bad = PlaceholderShotModel(speed_noise_frac=0.08, aim_noise_deg=6.0)
    g = np.mean([simulate_match(robot, [NoOpPolicy()], good, s).red_score for s in range(50)])
    b = np.mean([simulate_match(robot, [NoOpPolicy()], bad, s).red_score for s in range(50)])
    assert g >= b


def test_noop_alliance_scores_only_passive_points():
    r = _match([NoOpPolicy(), NoOpPolicy()], 1)
    assert r.red_score == rules.POINTS_BALL_IN_UP_CELL_END * rules.NECTAR_STAGED_IN_RAISED_CELL
    assert r.tips["red"] == 0
    r = _match([NoOpPolicy(leave=True, park=True), NoOpPolicy(leave=True)], 1)
    b = r.breakdown["red"]
    assert b["leave"] == 2 * rules.POINTS_LEAVE
    assert b["park_teleop"] == rules.POINTS_PARK_TELEOP
    staged = rules.POINTS_BALL_IN_UP_CELL_END * rules.NECTAR_STAGED_IN_RAISED_CELL
    assert b["tip_auto"] == b["tip_teleop"] == 0
    assert b["cell_end"] == staged  # the nectar the raised cell starts with
    assert b["total"] == 2 * rules.POINTS_LEAVE + rules.POINTS_PARK_TELEOP + staged


def test_perfect_constant_policy_tips():
    p = ConstantCyclePolicy(cycle_time_s=10.0, balls_per_cycle=4, make_rate=1.0)
    r = _match([p, p], 0)
    assert r.tips["red"] >= 3
    assert r.breakdown["red"]["tip_teleop"] == 20 * r.tips["red"]
    assert any(k == "tip" for _, _, k, _ in r.events)


def test_pool_is_shared_and_bounded():
    p = ConstantCyclePolicy(cycle_time_s=4.0, balls_per_cycle=4, make_rate=1.0)
    r = _match([p, p], 0, [p, p])
    assert r.pollen_left >= 0
    assert r.pollen_left + r.pollen_in_cells <= rules.POLLEN_ON_FIELD


def test_nectar_staging_constants():
    assert rules.NECTAR_STAGED_IN_RAISED_CELL == 3
    assert rules.NECTAR_STAGED_IN_ALLIANCE_AREA == 5
    assert rules.NECTAR_PER_ALLIANCE == 8


def test_first_tip_needs_table_entry_for_three_nectar():
    p = ConstantCyclePolicy(cycle_time_s=10.0, balls_per_cycle=8, make_rate=1.0)
    r = _match([p], 0)
    first = next(d for _, _, k, d in r.events if k == "tip")
    assert first["nectar"] == rules.NECTAR_STAGED_IN_RAISED_CELL
    assert first["pollen"] == rules.TIP_POLLEN_BY_NECTAR[3]
    made_before = 0
    for _, _, k, d in r.events:
        if k == "tip":
            break
        made_before += k == "shot_made" and d["ball"] == "pollen"
    assert made_before == rules.TIP_POLLEN_BY_NECTAR[3]  # the tipping shot is logged first


def test_pollen_never_vanishes_in_either_tip_mode():
    p = ConstantCyclePolicy(cycle_time_s=5.0, balls_per_cycle=4, make_rate=1.0)
    for mode in TipBehaviour:
        r = simulate_match([p, p], [p, p], MODEL, 2, mode)
        assert r.tips["red"] >= 1
        assert r.pollen_left + r.pollen_in_cells == rules.POLLEN_ON_FIELD  # nothing in flight


def test_tip_behaviour_bottom_nectar_bonus():
    p = ConstantCyclePolicy(cycle_time_s=5.0, balls_per_cycle=4, make_rate=1.0)
    spill = simulate_match([p, p], [NoOpPolicy()], MODEL, 5, TipBehaviour.SPILL_TO_FIELD)
    stay = simulate_match([p, p], [NoOpPolicy()], MODEL, 5, TipBehaviour.NECTAR_STAYS_DOWN)
    assert spill.breakdown["red"]["nectar_bottom"] == 0
    assert stay.breakdown["red"]["nectar_bottom"] >= rules.POINTS_BOTTOM_NECTAR * 3
