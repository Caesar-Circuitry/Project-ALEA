"""dsim <-> ALEA frame conversion: from the field centre (70.65 in), never 70.75."""

import math

from alea.game.biobuzz import FIELD_SIZE_IN, HIVE_X_IN, HIVE_Y_IN
from alea.hifi.frame import FIELD_CENTRE_IN, alea_to_dsim, dsim_to_alea
from alea.hifi.hive import Vec2, hive_pivot


def test_shift_is_field_centre():
    assert FIELD_CENTRE_IN == FIELD_SIZE_IN / 2
    assert math.isclose(FIELD_CENTRE_IN, 70.65)


def test_round_trip():
    for p in (Vec2(0, 0), Vec2(-12.75, 13.44), Vec2(60.1, -3.3)):
        q = alea_to_dsim(dsim_to_alea(p))
        assert math.isclose(q.x, p.x, abs_tol=1e-12)
        assert math.isclose(q.y, p.y, abs_tol=1e-12)


def test_hive_pivots_vs_alea_game():
    red = dsim_to_alea(hive_pivot("red"))
    blue = dsim_to_alea(hive_pivot("blue"))
    # pair spacing agrees exactly with alea.game: 25.5 in
    assert math.isclose(blue.x - red.x, HIVE_X_IN[1] - HIVE_X_IN[0])
    assert math.isclose(blue.x - red.x, 25.5)
    # the known, UNRESOLVED 0.10 in offset (PORTING.md evidence item 1): dsim's hive is on the
    # field centre, ALEA's HIVE_X_IN / HIVE_Y_IN sit 0.10 in away. Reported, not absorbed.
    assert math.isclose(HIVE_X_IN[0] - red.x, 0.10, abs_tol=1e-9)
    assert math.isclose(HIVE_X_IN[1] - blue.x, 0.10, abs_tol=1e-9)
    assert math.isclose(HIVE_Y_IN - red.y, 0.10, abs_tol=1e-9)
    assert math.isclose(red.y, 70.65) and math.isclose(blue.y, 70.65)
