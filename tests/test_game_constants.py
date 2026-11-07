"""alea.game.biobuzz must equal the committed snapshot and the frozen shotsim.py values."""

import json
import math
from pathlib import Path

import pytest

from alea.game import biobuzz
from alea.sim import shotsim, study

SNAPSHOT = Path(__file__).parent / "golden" / "game_constants_snapshot.json"

# biobuzz name -> shotsim name
SHOTSIM_NAMES = {
    "FIELD_SIZE_IN": "FIELD",
    "WALL_HEIGHT_IN": "WALL_H",
    "GRAVITY_IN_S2": "G",
    "AIR_DRAG": "AIR_DRAG",
    "HIVE_RESTITUTION": "WALL_E",
    "POLLEN_RADIUS_IN": "R_BALL",
    "SIM_DT_S": "DT",
    "SIM_MAX_STEPS": "MAX_STEPS",
    "HIVE_PIVOT_HEIGHT_IN": "PIVOT_H",
    "CELL_WIDTH_IN": "CELL_W",
    "CELL_HEIGHT_IN": "CELL_H",
    "CELL_CENTER_UP_IN": "CELL_CENTER_UP",
    "CELL_BOX_ALONG_MIN_IN": "A0",
    "CELL_BOX_ALONG_MAX_IN": "A1",
    "HUB_HALF_WIDTH_IN": "HUB_HALF_W",
    "HUB_BOTTOM_IN": "HUB_BOT",
    "HUB_TOP_IN": "HUB_TOP",
    "INNER_WALL_IN": "INNER_WALL",
    "INNER_HALF_WIDTH_IN": "IN_HALF_W",
    "SIDE_TOP_IN": "SIDE_TOP",
    "FLOOR_TOP_IN": "FLOOR_TOP",
    "RIDGE_IN": "RIDGE",
    "ROOF_THICKNESS_IN": "ROOF_T",
    "HIVE_REST_ANGLE_RAD": "REST",
    "HIVE_X_IN": "HIVE_X",
    "HIVE_Y_IN": "HIVE_Y",
    "HIVE_UP": "HIVE_UP",
    "FRAME_X0_IN": "FX0",
    "FRAME_Y0_IN": "FY0",
    "FRAME_Z0_IN": "FZ0",
    "FRAME_NX": "FNX",
    "FRAME_NY": "FNY",
    "FRAME_NZ": "FNZ",
    "LAUNCH_PITCH_RAD": "LAUNCH_PITCH",
    "LAUNCH_EXIT_X_IN": "EXIT_X",
    "LAUNCH_EXIT_Z_IN": "EXIT_Z",
    "TICKS_TO_IN_S": "TICKS_TO_INPS",
}

# biobuzz name -> value in the frozen study.py (the robot-code copy it aims with)
STUDY_VALUES = {
    "HIVE_AUDIENCE_MOUTH_Y_IN": study.TARGET_Y,
    "AIM_MAX_OFF_AXIS_DEG": math.degrees(study.MAX_OFF_AXIS),
    "LUT_DISTANCE_IN": tuple(study.LUT_DISTANCE_IN),
    "LUT_TICKS_PER_SEC": tuple(study.LUT_TICKS_PER_SEC),
}
# Values with no copy in the sim, checked by their own test below.
DERIVED = {"HIVE_REAR_MOUTH_Y_IN"}


def _current() -> dict:
    return {
        n: list(v) if isinstance(v, tuple) else v for n, v in vars(biobuzz).items() if n.isupper()
    }


def test_snapshot_matches_biobuzz():
    assert json.loads(SNAPSHOT.read_text(encoding="utf-8")) == _current()


@pytest.mark.parametrize(("name", "sim_name"), SHOTSIM_NAMES.items())
def test_biobuzz_equals_shotsim(name, sim_name):
    assert getattr(biobuzz, name) == getattr(shotsim, sim_name)


@pytest.mark.parametrize(("name", "value"), STUDY_VALUES.items())
def test_biobuzz_equals_study(name, value):
    assert getattr(biobuzz, name) == pytest.approx(value, abs=1e-9)


def test_study_uses_biobuzz_geometry():
    assert study.TARGET_X == biobuzz.HIVE_X_IN[0]
    assert study.EXIT_BEHIND == -biobuzz.LAUNCH_EXIT_X_IN


def test_rear_mouth_mirrors_audience_mouth():
    mirrored = 2 * biobuzz.HIVE_Y_IN - biobuzz.HIVE_AUDIENCE_MOUTH_Y_IN
    assert biobuzz.HIVE_REAR_MOUTH_Y_IN == pytest.approx(mirrored, abs=1e-9)


def test_every_constant_is_mapped():
    assert set(_current()) == set(SHOTSIM_NAMES) | set(STUDY_VALUES) | DERIVED
