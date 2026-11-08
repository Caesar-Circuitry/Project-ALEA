import pytest

from alea.matchsim import rules
from alea.matchsim.rules import MatchPhase, phase_at, pollen_to_tip


def test_timeline_adds_to_158_s():
    assert rules.MATCH_END_S == 158.0
    assert rules.TELEOP_START_S == 38.0
    assert rules.ENDGAME_START_S == 128.0
    assert rules.NECTAR_RELEASE_ALL_AT_S == 98.0


@pytest.mark.parametrize(
    ("t_s", "phase"),
    [
        (0.0, MatchPhase.AUTO),
        (29.99, MatchPhase.AUTO),
        (30.0, MatchPhase.TRANSITION),
        (37.99, MatchPhase.TRANSITION),
        (38.0, MatchPhase.TELEOP),
        (127.99, MatchPhase.TELEOP),
        (128.0, MatchPhase.ENDGAME),
        (158.0, MatchPhase.ENDGAME),
    ],
)
def test_phase_lookup(t_s, phase):
    assert phase_at(t_s) is phase


@pytest.mark.parametrize("t_s", [-0.1, 158.1])
def test_phase_outside_match_raises(t_s):
    with pytest.raises(ValueError):
        phase_at(t_s)


def test_tip_table_is_monotone_and_clamped():
    assert [pollen_to_tip(n) for n in range(6)] == [8, 7, 6, 3, 1, 0]
    assert pollen_to_tip(9) == 0
    assert pollen_to_tip(-1) == 8
    assert list(rules.TIP_POLLEN_BY_NECTAR) == sorted(rules.TIP_POLLEN_BY_NECTAR, reverse=True)


def test_tip_points_and_ranking_points():
    assert rules.tip_points(MatchPhase.AUTO) == 20
    assert rules.tip_points(MatchPhase.ENDGAME) == 20
    assert rules.tip_points(MatchPhase.TRANSITION) == 0
    assert [rules.ranking_points_for_tips(n) for n in (0, 3, 4, 6, 7)] == [0, 0, 1, 1, 2]
