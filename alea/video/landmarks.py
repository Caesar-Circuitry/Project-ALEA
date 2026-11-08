"""Named 3D field landmarks for camera calibration (roadmap phase 2, stage 2.1).

Every coordinate is derived from `alea.game.biobuzz` constants; this module adds no game value.
Field frame = Pedro / sim frame: x and y along the field edges, z up, inches, origin at a
field corner on the floor.

The hive frame box is the 1-inch-voxel envelope of the support frame. A corner of the box is a
real post only where the CAD has a cube; the operator should click only corners they can see.
Tile seams and tape lines are not here: their coordinates are not game values (later PR).
"""

from dataclasses import dataclass
from itertools import product

import numpy as np
from numpy.typing import NDArray

from alea.game import biobuzz as g

KIND_FIELD_CORNER = "field_corner"
KIND_WALL_TOP = "wall_top"
KIND_HIVE_PIVOT = "hive_pivot"
KIND_HIVE_FRAME = "hive_frame"
KIND_HIVE_MOUTH = "hive_mouth"  # floor-plane use only (z unknown without CAD)

_FLOOR_TOL_IN = 1e-9


@dataclass(frozen=True)
class Landmark:
    """One named point on the field."""

    name: str
    x_in: float
    y_in: float
    z_in: float
    kind: str

    @property
    def xyz_in(self) -> tuple[float, float, float]:
        return (self.x_in, self.y_in, self.z_in)

    @property
    def on_floor(self) -> bool:
        return abs(self.z_in) <= _FLOOR_TOL_IN


def _build() -> dict[str, Landmark]:
    """Ids follow the click log's convention (alea/video/landmark_ids.py on feature/2-click-log)."""
    out: dict[str, Landmark] = {}
    size_in = g.FIELD_SIZE_IN
    corners = (
        ("xlo", "ylo", 0.0, 0.0),
        ("xlo", "yhi", 0.0, size_in),
        ("xhi", "ylo", size_in, 0.0),
        ("xhi", "yhi", size_in, size_in),
    )

    def add(lm: Landmark) -> None:
        out[lm.name] = lm

    for xs, ys, x_in, y_in in corners:
        add(Landmark(f"field_floor_corner_{xs}_{ys}", x_in, y_in, 0.0, KIND_FIELD_CORNER))
    for xs, ys, x_in, y_in in corners:
        name = f"field_wall_top_corner_{xs}_{ys}"
        add(Landmark(name, x_in, y_in, g.WALL_HEIGHT_IN, KIND_WALL_TOP))
    for team, x_in in zip(("red", "blue"), g.HIVE_X_IN, strict=True):
        z_in = g.HIVE_PIVOT_HEIGHT_IN
        add(Landmark(f"hive_{team}_pivot", x_in, g.HIVE_Y_IN, z_in, KIND_HIVE_PIVOT))
    lo_hi = (
        (("xlo", g.FRAME_X0_IN), ("xhi", g.FRAME_X0_IN + g.FRAME_NX)),
        (("ylo", g.FRAME_Y0_IN), ("yhi", g.FRAME_Y0_IN + g.FRAME_NY)),
        (("zlo", g.FRAME_Z0_IN), ("zhi", g.FRAME_Z0_IN + g.FRAME_NZ)),
    )
    for (xs, x_in), (ys, y_in), (zs, z_in) in product(*lo_hi):
        name = f"hive_frame_corner_{xs}_{ys}_{zs}"
        add(Landmark(name, float(x_in), float(y_in), float(z_in), KIND_HIVE_FRAME))
    mouths = (("audience", g.HIVE_AUDIENCE_MOUTH_Y_IN), ("rear", g.HIVE_REAR_MOUTH_Y_IN))
    for team, x_in in zip(("red", "blue"), g.HIVE_X_IN, strict=True):
        for mouth, y_in in mouths:
            add(Landmark(f"hive_{team}_mouth_{mouth}", x_in, y_in, 0.0, KIND_HIVE_MOUTH))
    return out


_TABLE: dict[str, Landmark] = _build()


def landmark_table() -> dict[str, Landmark]:
    """All landmarks by name (a copy; insertion order is stable)."""
    return dict(_TABLE)


def get_landmark(name: str) -> Landmark:
    try:
        return _TABLE[name]
    except KeyError:
        raise KeyError(f"unknown landmark {name!r}; known: {', '.join(_TABLE)}") from None


def is_custom_id(name: str) -> bool:
    """`custom_<name>` marks (tile seams, tape) have no coordinates in alea.game yet."""
    return name.startswith("custom_")


def floor_landmarks() -> list[Landmark]:
    return [lm for lm in _TABLE.values() if lm.on_floor]


def elevated_landmarks() -> list[Landmark]:
    return [lm for lm in _TABLE.values() if not lm.on_floor]


def landmarks_xyz_in(names: list[str]) -> NDArray[np.float64]:
    """World coordinates (N, 3) in inches for the given landmark names."""
    return np.array([get_landmark(n).xyz_in for n in names], dtype=np.float64).reshape(-1, 3)
