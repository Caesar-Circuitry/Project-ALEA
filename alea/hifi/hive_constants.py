"""Ported from dsim by genius0412, commit 62d2446e2ebdf416548fa1641847289bf47cdf36.

License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim). Not the license of the rest
of ALEA.

THESE ARE DSIM'S NUMBERS, NOT alea/game's. Each value was copied from
tests/hifi_traces/constants.json, which was recorded by running dsim's own code at the pinned
commit; the comment on each names the dsim source line. Nothing here is read from or compared
with alea/game, and no value was chosen over another. Distances are inches, speeds in/s, times
seconds, angles degrees, in dsim's field-centred frame (hive pivots at x = +-12.75 in, red at -x).

Differences from alea/game that are UNRESOLVED and left for the user (details in
alea/hifi/PORTING.md and tests/hifi_traces/README.md):

- frame: dsim is centred on the field; ALEA's hive midpoint is 0.10 in off the field centre.
- cell width: dsim CELL_W 20.141 in (BB_CELL_OPEN.w) against alea/game CELL_WIDTH_IN 21.06 in;
  depth along the bar 11.75 in (CELL_NEAR 9.644 to CELL_FAR 21.394) against 9.38 to 21.46 in.
- restitution: dsim has 0.35 (BB_POLLEN_WALL_REST, config.ts:710) and 0.55
  (BB3_ELEMENT_RESTITUTION, config.ts:3445), neither read by hive.ts and neither included here;
  the hive miss bounce below uses 0.3 (BB_HIVE_MISS_REST). alea/game has 0.45.
- every APPROX value (accept margin, swing rate, spill speed/fan/kick, miss bounce) is dsim's
  own feel ruling, not a measurement.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class CellOpen:
    """The accept footprint of one CELL opening, inches (dsim `BB_CELL_OPEN`)."""

    w: float
    d: float


@dataclass(frozen=True)
class Cell3:
    """A CELL's true size along its own bar, inches (dsim `BB3_HIVE_CELL`)."""

    w: float
    d: float
    h: float


@dataclass(frozen=True)
class HiveGeometry:
    """dsim's `HIVE` block (true lengths along the bar, inches). Field names are dsim's."""

    PIVOT_X: float
    PIVOT_Z: float
    TILT_DEG: float
    ARM: float
    LEN: float
    CELL_W: float
    CELL_D: float
    CELL_H: float
    CELL_NEAR: float
    CELL_FAR: float
    CELL_FLOOR_W: float
    CELL_TOP_W: float
    OPEN_Z: tuple[float, float]
    DOWN_FLOOR_Z: float
    LOWEST_Z: float
    UP_STAGED: dict[str, str]


# --- hive.ts own constants ---------------------------------------------------
BB_HIVE_ACCEPT_MARGIN: Final = 2.0  # dsim value, hive.ts:71
BB_HIVE_MISS_REST: Final = 0.3  # dsim value, hive.ts:471
BB_HIVE_MISS_TANGENT: Final = 0.5  # dsim value, hive.ts:472
BB_SPILL_FAN: Final = 40  # dsim value, hive.ts:340
BB_SPILL_KICK: Final = 12  # dsim value, hive.ts:360
BB_SPILL_SPEED: Final = (30, 62)  # dsim value, hive.ts:339
BB_TIP_RATE_MAX: Final = 3  # dsim value, hive.ts:210
BB_TIP_RATE_PER_EXTRA: Final = 0.35  # dsim value, hive.ts:209
BB_TIP_RELEASE_S: Final = 2.0  # dsim value, hive.ts:67
BB_TIP_SWING_S: Final = 4.0  # dsim value, hive.ts:56

# --- config.ts hive block ----------------------------------------------------
BB3_HIVE_ARM: Final = 15.519  # dsim value, config.ts:3340
BB3_HIVE_BALLAST: Final = 6  # dsim value, config.ts:4093
BB3_HIVE_BALLAST_AT: Final = (0, -9.5)  # dsim value, config.ts:4094
BB3_HIVE_CELL: Final = Cell3(w=20.141, d=11.75, h=13.997)  # dsim value, config.ts:3359
BB3_HIVE_CELL_LEN: Final = 11.75  # dsim value, config.ts:3344
BB3_HIVE_CELL_WALL: Final = 0.25  # dsim value, config.ts:3363
BB3_HIVE_DAMPING: Final = 4.466  # dsim value, config.ts:4096
BB3_HIVE_DETENT: Final = 3041  # dsim value, config.ts:4095
BB3_HIVE_DYNAMIC: Final = True  # dsim value, config.ts:3316
BB3_HIVE_LEN: Final = 42.788  # dsim value, config.ts:3348
BB3_HIVE_PIVOT_Z: Final = 43.95  # dsim value, config.ts:3334
BB3_HIVE_REST_W: Final = 0.15  # dsim value, config.ts:4033
BB3_HIVE_SHED_AFTER: Final = 4  # dsim value, config.ts:3398
BB3_HIVE_SHED_MAX: Final = 8  # dsim value, config.ts:3401
BB3_HIVE_SHED_MIN_Z: Final = 30  # dsim value, config.ts:3407
BB3_HIVE_SHED_REGION_X: Final = 26  # dsim value, config.ts:3402
BB3_HIVE_SHED_REGION_Y: Final = 22.5  # dsim value, config.ts:3403
BB3_HIVE_SHED_SPEED: Final = 14  # dsim value, config.ts:3399
BB3_HIVE_SHED_VZ: Final = 10  # dsim value, config.ts:3400
BB3_HIVE_STOP_DEG: Final = 29  # dsim value, config.ts:4032
BB3_HIVE_TIP_CREEP_W: Final = 0.12  # dsim value, config.ts:4064
BB3_HIVE_TRAY_MASS: Final = 13  # dsim value, config.ts:4027
BB_CELL_OPEN: Final = CellOpen(w=20.141, d=10.175798494467081)  # dsim value, config.ts:318
BB_HIVE_BOTTOM_Z: Final = 31.981  # dsim value, config.ts:306
BB_HIVE_CELL_DY: Final = 13.439848241330608  # dsim value, config.ts:279
BB_HIVE_CELL_LEN: Final = 10.175798494467081  # dsim value, config.ts:283
BB_HIVE_LEN: Final = 37.0554949771283  # dsim value, config.ts:329
BB_HIVE_LOWEST_Z: Final = 30.652  # dsim value, config.ts:311
BB_HIVE_OPEN_Z: Final = (53.375, 65.497)  # dsim value, config.ts:292
BB_HIVE_TAGS: Final = {
    "red": {"north": (30, 31, 32, 33), "south": (34, 35, 36, 37)},
    "blue": {"north": (42, 43, 44, 45), "south": (38, 39, 40, 41)},
}  # dsim value, config.ts:362
BB_HIVE_TILT_DEG: Final = 30  # dsim value, config.ts:266
BB_HIVE_UP_STAGED: Final = {"red": "south", "blue": "north"}  # dsim value, config.ts:369
BB_HIVE_W: Final = 20.141  # dsim value, config.ts:334
BB_HIVE_X: Final = 12.75  # dsim value, config.ts:251
BB_NECTAR_R: Final = 1.8  # dsim value, config.ts:675
BB_POLLEN_R: Final = 1.4  # dsim value, config.ts:667
BB_TIP_POLLEN: Final = (8, 7, 6, 3, 1, 0)  # dsim value, config.ts:609

# --- fieldDims.gen.ts HIVE block ---------------------------------------------
HIVE: Final = HiveGeometry(
    PIVOT_X=12.75,  # dsim value, fieldDims.gen.ts:149
    PIVOT_Z=43.95,  # dsim value, fieldDims.gen.ts:150
    TILT_DEG=30,  # dsim value, fieldDims.gen.ts:151
    ARM=15.519,  # dsim value, fieldDims.gen.ts:152
    LEN=42.788,  # dsim value, fieldDims.gen.ts:153
    CELL_W=20.141,  # dsim value, fieldDims.gen.ts:154
    CELL_D=11.75,  # dsim value, fieldDims.gen.ts:155
    CELL_H=13.997,  # dsim value, fieldDims.gen.ts:156
    CELL_NEAR=9.644,  # dsim value, fieldDims.gen.ts:157
    CELL_FAR=21.394,  # dsim value, fieldDims.gen.ts:158
    CELL_FLOOR_W=-1.468,  # dsim value, fieldDims.gen.ts:159
    CELL_TOP_W=12.529,  # dsim value, fieldDims.gen.ts:160
    OPEN_Z=(53.375, 65.497),  # dsim value, fieldDims.gen.ts:161
    DOWN_FLOOR_Z=31.981,  # dsim value, fieldDims.gen.ts:162
    LOWEST_Z=30.652,  # dsim value, fieldDims.gen.ts:163
    UP_STAGED={"red": "south", "blue": "north"},  # dsim value, fieldDims.gen.ts:164
)
