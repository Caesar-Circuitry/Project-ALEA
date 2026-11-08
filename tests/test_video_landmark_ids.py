"""Landmark ids match the click log's (feature/2-click-log) and custom ids are ignored."""

import pytest

from alea.game import biobuzz as g
from alea.video.landmarks import get_landmark, is_custom_id, landmark_table

# Copied from known_landmark_ids() in alea/video/landmark_ids.py on branch feature/2-click-log
# (commit bab85fe); keep in sync by hand because the branches do not import each other.
CLICK_LOG_IDS = (
    "field_floor_corner_xlo_ylo",
    "field_floor_corner_xlo_yhi",
    "field_floor_corner_xhi_ylo",
    "field_floor_corner_xhi_yhi",
    "field_wall_top_corner_xlo_ylo",
    "field_wall_top_corner_xlo_yhi",
    "field_wall_top_corner_xhi_ylo",
    "field_wall_top_corner_xhi_yhi",
    "hive_red_pivot",
    "hive_blue_pivot",
    "hive_frame_corner_xlo_ylo_zlo",
    "hive_frame_corner_xlo_ylo_zhi",
    "hive_frame_corner_xlo_yhi_zlo",
    "hive_frame_corner_xlo_yhi_zhi",
    "hive_frame_corner_xhi_ylo_zlo",
    "hive_frame_corner_xhi_ylo_zhi",
    "hive_frame_corner_xhi_yhi_zlo",
    "hive_frame_corner_xhi_yhi_zhi",
    "hive_red_mouth_audience",
    "hive_red_mouth_rear",
    "hive_blue_mouth_audience",
    "hive_blue_mouth_rear",
)


def test_every_click_log_id_resolves_and_no_extras() -> None:
    assert set(CLICK_LOG_IDS) == set(landmark_table())
    for name in CLICK_LOG_IDS:
        get_landmark(name)


def test_mouths_use_game_constants() -> None:
    lm = get_landmark("hive_blue_mouth_rear")
    assert lm.xyz_in == (g.HIVE_X_IN[1], g.HIVE_REAR_MOUTH_Y_IN, 0.0)
    assert lm.on_floor


def test_custom_ids_are_not_landmarks() -> None:
    assert is_custom_id("custom_tile_seam_a")
    with pytest.raises(KeyError):
        get_landmark("custom_tile_seam_a")
