"""Ported from dsim by genius0412, commit 62d2446e2ebdf416548fa1641847289bf47cdf36.

License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim). Not the license of the rest
of ALEA.

THE CONSTANTS THE 3D HIVE (`src/games/biobuzz/sim3d/hive3d.ts`) READS. THESE ARE DSIM'S NUMBERS,
NOT alea/game's. Each was copied from tests/hifi_traces/sim3d/constants3d.json, which was recorded
by running dsim's own code at the pinned commit; the comment on each names the dsim source line.
Nothing here is read from or compared with alea/game, and no value was chosen over another.
Inches, seconds, radians, pounds (dsim's mass unit), field-centred frame.

Names that `hive_constants.py` already holds (the `BB3_HIVE_*` block, `BB_HIVE_TILT_DEG`,
`BB_POLLEN_R`, `BB_NECTAR_R`, `BB_TIP_POLLEN`, `BB_TIP_SWING_S`) are re-exported from there, so
there is one definition of each. What is new here is `BB3_CELL_SEAT_DEPTH`, the element masses,
`BB3_TRAY_OUTER_SKIN`, `BB3_REST_SPEED`, `GRAVITY`, `SIM_DT` and the CAD-measured cell boxes.

Several are calibration outputs that dsim fitted to its own Rapier engine, not measurements:
`BB3_HIVE_DETENT` (3041), `BB3_HIVE_DAMPING` (4.466) and `BB3_HIVE_BALLAST` (6). They are only
meaningful together with that engine; see alea/hifi/PORTING.md.
"""

from dataclasses import dataclass
from typing import Final

from alea.hifi.hive_constants import (
    BB3_HIVE_ARM as BB3_HIVE_ARM,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_BALLAST as BB3_HIVE_BALLAST,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_BALLAST_AT as BB3_HIVE_BALLAST_AT,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_CELL as BB3_HIVE_CELL,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_CELL_LEN as BB3_HIVE_CELL_LEN,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_CELL_WALL as BB3_HIVE_CELL_WALL,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_DAMPING as BB3_HIVE_DAMPING,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_DETENT as BB3_HIVE_DETENT,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_DYNAMIC as BB3_HIVE_DYNAMIC,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_LEN as BB3_HIVE_LEN,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_PIVOT_Z as BB3_HIVE_PIVOT_Z,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_REST_W as BB3_HIVE_REST_W,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_SHED_AFTER as BB3_HIVE_SHED_AFTER,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_SHED_MAX as BB3_HIVE_SHED_MAX,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_SHED_MIN_Z as BB3_HIVE_SHED_MIN_Z,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_SHED_REGION_X as BB3_HIVE_SHED_REGION_X,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_SHED_REGION_Y as BB3_HIVE_SHED_REGION_Y,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_SHED_SPEED as BB3_HIVE_SHED_SPEED,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_SHED_VZ as BB3_HIVE_SHED_VZ,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_STOP_DEG as BB3_HIVE_STOP_DEG,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_TIP_CREEP_W as BB3_HIVE_TIP_CREEP_W,
)
from alea.hifi.hive_constants import (
    BB3_HIVE_TRAY_MASS as BB3_HIVE_TRAY_MASS,
)
from alea.hifi.hive_constants import (
    BB_HIVE_TILT_DEG as BB_HIVE_TILT_DEG,
)
from alea.hifi.hive_constants import (
    BB_HIVE_X as BB_HIVE_X,
)
from alea.hifi.hive_constants import (
    BB_NECTAR_R as BB_NECTAR_R,
)
from alea.hifi.hive_constants import (
    BB_POLLEN_R as BB_POLLEN_R,
)
from alea.hifi.hive_constants import (
    BB_TIP_POLLEN as BB_TIP_POLLEN,
)
from alea.hifi.hive_constants import (
    BB_TIP_SWING_S as BB_TIP_SWING_S,
)

# --- config.ts, 3D block (not in hive_constants.py) --------------------------
BB3_CELL_SEAT_DEPTH: Final = 3.5  # dsim value, config.ts:3545
BB3_ELEMENT_MASS: Final = 0.2  # dsim value, config.ts:3414
BB3_NECTAR_MASS_RATIO: Final = 1.6  # dsim value, config.ts:3418
BB3_REST_SPEED: Final = 2  # dsim value, config.ts:3506
BB3_TRAY_OUTER_SKIN: Final = 0.5  # dsim value, config.ts:3376

# --- src/config.ts (the engine-wide block) -----------------------------------
GRAVITY: Final = 386  # dsim value, src/config.ts:736 (in/s^2)
SIM_DT: Final = 1 / 60  # dsim value, src/config.ts:2969 (s); also the recorded fixtures' dt


@dataclass(frozen=True)
class HiveLocalBox:
    """An axis-aligned CELL interior in the tray's own local (v, w) plane (dsim `HiveLocalBox`).

    `v` runs along the bar from the pivot, `w` is height above the tray's floor, `x_half` is the
    half width across. `ref_theta` is dsim's `refTheta`, 0 on both paths.
    """

    x_half: float
    v_min: float
    v_max: float
    w_min: float
    w_max: float
    ref_theta: float


# CAD-measured cell interiors, `trays.<alliance>.cells.<north|south>` in the generated
# `src/games/biobuzz/sim3d/fieldColliders.gen.ts:3` (one long JSON line), read through
# `cadCellBox` (`fieldColliders.ts:615`) and `hiveCellLocalBox` (`bodies.ts:503`, used because
# `BB3_FIELD_COLLIDERS` is true, `config.ts:3330`). `refTheta` is 0 (`tilt.ts:68`). The two
# alliances differ in the fourth decimal on the pivot-side edge (9.644 vs 9.6441).
# Checked against constants3d.json `cell_local_box` by tests/test_hifi_hive3d_statics.py.
HIVE_CELL_BOXES: Final = {
    "red": {
        "north": HiveLocalBox(10.0706, 9.644, 21.3941, -1.4682, 12.5287, 0),
        "south": HiveLocalBox(10.0706, -21.3941, -9.6441, -1.4682, 12.5287, 0),
    },
    "blue": {
        "north": HiveLocalBox(10.0706, 9.6441, 21.3941, -1.4682, 12.5287, 0),
        "south": HiveLocalBox(10.0706, -21.3941, -9.644, -1.4682, 12.5287, 0),
    },
}
