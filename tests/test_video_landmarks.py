"""Field landmarks come from alea.game only (roadmap phase 2, stage 2.1)."""

import pytest

from alea.game import biobuzz as g
from alea.video.landmarks import (
    elevated_landmarks,
    floor_landmarks,
    get_landmark,
    landmark_table,
    landmarks_xyz_in,
)


def test_counts_and_names_unique() -> None:
    table = landmark_table()
    kinds = [lm.kind for lm in table.values()]
    assert kinds.count("field_corner") == 4
    assert kinds.count("wall_top") == 4
    assert kinds.count("hive_pivot") == 2
    assert kinds.count("hive_frame") == 8
    assert kinds.count("hive_mouth") == 4
    assert kinds.count("hive_mouth") == 4
    assert all(k == lm.name for k, lm in table.items())


def test_values_derive_from_game_constants() -> None:
    assert get_landmark("field_floor_corner_xhi_yhi").xyz_in == (g.FIELD_SIZE_IN,) * 2 + (0.0,)
    assert get_landmark("field_wall_top_corner_xlo_ylo").z_in == g.WALL_HEIGHT_IN
    assert get_landmark("hive_red_pivot").xyz_in == (
        g.HIVE_X_IN[0],
        g.HIVE_Y_IN,
        g.HIVE_PIVOT_HEIGHT_IN,
    )
    top = get_landmark("hive_frame_corner_xhi_yhi_zhi")
    assert top.xyz_in == (
        g.FRAME_X0_IN + g.FRAME_NX,
        g.FRAME_Y0_IN + g.FRAME_NY,
        g.FRAME_Z0_IN + g.FRAME_NZ,
    )


def test_floor_split() -> None:
    assert all(lm.z_in == 0 for lm in floor_landmarks())
    assert all(lm.z_in > 0 for lm in elevated_landmarks())
    assert len(floor_landmarks()) + len(elevated_landmarks()) == len(landmark_table())


def test_unknown_name_and_array() -> None:
    with pytest.raises(KeyError, match="unknown landmark"):
        get_landmark("nope")
    assert landmarks_xyz_in(["field_wall_top_corner_xlo_ylo"]).shape == (1, 3)
