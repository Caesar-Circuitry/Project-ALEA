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


def _fmt(value_in: float) -> str:
    """Compact coordinate for a name: 141.3 -> '141', 46 -> '46'."""
    return str(int(round(value_in)))


def _build() -> dict[str, Landmark]:
    out: dict[str, Landmark] = {}

    def add(lm: Landmark) -> None:
        if lm.name in out:  # pragma: no cover - guards against future constant edits
            raise ValueError(f"duplicate landmark name {lm.name}")
        out[lm.name] = lm

    size_in = g.FIELD_SIZE_IN
    for x_in, y_in in product((0.0, size_in), repeat=2):
        tag = f"x{_fmt(x_in)}_y{_fmt(y_in)}"
        add(Landmark(f"field_corner_{tag}_z0", x_in, y_in, 0.0, KIND_FIELD_CORNER))
    for x_in, y_in in product((0.0, size_in), repeat=2):
        tag = f"x{_fmt(x_in)}_y{_fmt(y_in)}"
        add(Landmark(f"wall_top_{tag}", x_in, y_in, g.WALL_HEIGHT_IN, KIND_WALL_TOP))
    for team, x_in in zip(("red", "blue"), g.HIVE_X_IN, strict=True):
        add(
            Landmark(
                f"hive_pivot_{team}", x_in, g.HIVE_Y_IN, g.HIVE_PIVOT_HEIGHT_IN, KIND_HIVE_PIVOT
            )
        )
    xs_in = (g.FRAME_X0_IN, g.FRAME_X0_IN + g.FRAME_NX)
    ys_in = (g.FRAME_Y0_IN, g.FRAME_Y0_IN + g.FRAME_NY)
    zs_in = (g.FRAME_Z0_IN, g.FRAME_Z0_IN + g.FRAME_NZ)
    for x_in, y_in, z_in in product(xs_in, ys_in, zs_in):
        name = f"hive_frame_x{_fmt(x_in)}_y{_fmt(y_in)}_z{_fmt(z_in)}"
        add(Landmark(name, float(x_in), float(y_in), float(z_in), KIND_HIVE_FRAME))
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


def floor_landmarks() -> list[Landmark]:
    return [lm for lm in _TABLE.values() if lm.on_floor]


def elevated_landmarks() -> list[Landmark]:
    return [lm for lm in _TABLE.values() if not lm.on_floor]


def landmarks_xyz_in(names: list[str]) -> NDArray[np.float64]:
    """World coordinates (N, 3) in inches for the given landmark names."""
    return np.array([get_landmark(n).xyz_in for n in names], dtype=np.float64).reshape(-1, 3)
