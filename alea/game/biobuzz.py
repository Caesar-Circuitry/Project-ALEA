"""BIOBUZZ 2026-27 game constants: field, hive and the StarterBot launcher.

Every value is a copy of a number in the frozen, Java-validated `alea/sim/shotsim.py`
(authoritative; it does NOT import this module). `tests/test_game_constants.py` checks that
this file, `tests/golden/game_constants_snapshot.json` and shotsim.py all agree.
Units are inches, seconds, radians (field frame = Pedro / sim frame) unless a name says more.
"""

import math

# --- field and physics (BioBuzzConfig)
FIELD_SIZE_IN = 141.3  # source: alea/sim/shotsim.py:29 FIELD
WALL_HEIGHT_IN = 11.64  # source: alea/sim/shotsim.py:30 WALL_H
GRAVITY_IN_S2 = 386.09  # source: alea/sim/shotsim.py:31 G
AIR_DRAG = 0.05  # source: alea/sim/shotsim.py:32 AIR_DRAG
HIVE_RESTITUTION = 0.45  # source: alea/sim/shotsim.py:33 WALL_E (off the hive and its frame)
POLLEN_RADIUS_IN = 1.4  # source: alea/sim/shotsim.py:34 R_BALL
SIM_DT_S = 0.002  # source: alea/sim/shotsim.py:35 DT
SIM_MAX_STEPS = 1000  # source: alea/sim/shotsim.py:36 MAX_STEPS

# --- hive geometry, hive frame
HIVE_PIVOT_HEIGHT_IN = 43.95  # source: alea/sim/shotsim.py:38 PIVOT_H
CELL_WIDTH_IN = 21.06  # source: alea/sim/shotsim.py:39 CELL_W
CELL_HEIGHT_IN = 15.79  # source: alea/sim/shotsim.py:40 CELL_H
CELL_CENTER_UP_IN = 5.18  # source: alea/sim/shotsim.py:41 CELL_CENTER_UP
CELL_BOX_ALONG_MIN_IN = 9.38  # source: alea/sim/shotsim.py:42 A0 (cellBoxAlongMin)
CELL_BOX_ALONG_MAX_IN = 21.46  # source: alea/sim/shotsim.py:42 A1 (cellBoxAlongMax)
HUB_HALF_WIDTH_IN = 0.9  # source: alea/sim/shotsim.py:43 HUB_HALF_W
HUB_BOTTOM_IN = -2.71  # source: alea/sim/shotsim.py:43 HUB_BOT
HUB_TOP_IN = 0.87  # source: alea/sim/shotsim.py:43 HUB_TOP
INNER_WALL_IN = 9.44  # source: alea/sim/shotsim.py:44 INNER_WALL
INNER_HALF_WIDTH_IN = 10.0  # source: alea/sim/shotsim.py:45 IN_HALF_W
SIDE_TOP_IN = 6.4  # source: alea/sim/shotsim.py:46 SIDE_TOP
FLOOR_TOP_IN = -1.47  # source: alea/sim/shotsim.py:47 FLOOR_TOP
RIDGE_IN = 12.7  # source: alea/sim/shotsim.py:48 RIDGE
ROOF_THICKNESS_IN = 0.3  # source: alea/sim/shotsim.py:49 ROOF_T
HIVE_REST_ANGLE_RAD = math.radians(30)  # source: alea/sim/shotsim.py:50 REST

# --- hive placement: pivot x, y; tip direction +y; raised side (red: audience -1, blue: rear +1)
HIVE_X_IN = (58.0, 83.5)  # source: alea/sim/shotsim.py:53 HIVE_X (red, blue)
HIVE_Y_IN = 70.75  # source: alea/sim/shotsim.py:54 HIVE_Y
HIVE_UP = (-1, 1)  # source: alea/sim/shotsim.py:55 HIVE_UP (red, blue)

# --- hive support frame (HiveFrame.java, 1-inch cubes from the field CAD)
FRAME_X0_IN = 46  # source: alea/sim/shotsim.py:89 FX0
FRAME_Y0_IN = 51  # source: alea/sim/shotsim.py:89 FY0
FRAME_Z0_IN = 0  # source: alea/sim/shotsim.py:89 FZ0
FRAME_NX = 50  # source: alea/sim/shotsim.py:89 FNX
FRAME_NY = 40  # source: alea/sim/shotsim.py:89 FNY
FRAME_NZ = 45  # source: alea/sim/shotsim.py:89 FNZ

# --- StarterBot launcher (SimLauncherConfig)
LAUNCH_PITCH_RAD = math.radians(72.2)  # source: alea/sim/shotsim.py:60 LAUNCH_PITCH
LAUNCH_EXIT_X_IN = -6.1  # source: alea/sim/shotsim.py:61 EXIT_X (robot frame, out the back)
LAUNCH_EXIT_Z_IN = 8.5  # source: alea/sim/shotsim.py:61 EXIT_Z
# flywheel ticks/s -> ball in/s
TICKS_TO_IN_S = 1.0 / 28 * 2 * math.pi * 1.89 * 0.45  # source: alea/sim/shotsim.py:62

# --- robot aim (StarterBot constants.java / aimAssist.java, copied into the frozen study.py)
# Raised-cell mouth y: audience-side cell up (red hive's target), rear cell up (the mirror of the
# audience mouth about HIVE_Y_IN). robot/.../Constants.java carries the same values.
HIVE_AUDIENCE_MOUTH_Y_IN = 54.47  # source: alea/sim/study.py:22 TARGET_Y
HIVE_REAR_MOUTH_Y_IN = 87.03  # source: Constants.java:30 (= 2 * HIVE_Y_IN - audience mouth)
AIM_MAX_OFF_AXIS_DEG = 80.0  # source: alea/sim/study.py:24 MAX_OFF_AXIS (in degrees)
# The launch LUT: launcher-exit-to-mouth distance -> flywheel ticks/s (unverified on the robot)
# source: alea/sim/study.py:25 LUT_DISTANCE_IN
LUT_DISTANCE_IN = (24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80)
# source: alea/sim/study.py:26 LUT_TICKS_PER_SEC
LUT_TICKS_PER_SEC = (
    1180, 1110, 1100, 1100, 1120, 1140, 1160, 1180, 1200, 1230, 1260, 1290, 1310, 1340, 1360,
)  # fmt: skip
