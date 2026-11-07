"""Ported from dsim by genius0412, commit 62d2446e2ebdf416548fa1641847289bf47cdf36.

License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim). Not the license of the rest
of ALEA.

The two small helpers of dsim's `src/games/biobuzz/sim3d/math3.ts` that the 3D hive uses:
`rotate2` (math3.ts:87) and `tiltQuatX` (math3.ts:69). Both go through dsim's deterministic
`dsin` / `dcos` (`hive_math.py`), never `math.sin` / `math.cos`, so the results are bit-identical
to dsim's.
"""

from typing import NamedTuple

from alea.hifi.hive_math import dcos, dsin


class Quat(NamedTuple):
    """A quaternion in dsim's field order (x, y, z, w)."""

    x: float
    y: float
    z: float
    w: float


def tilt_quat_x(theta: float) -> Quat:
    """Rotation of `theta` radians about the X axis (dsim `tiltQuatX`)."""
    half = theta / 2
    return Quat(dsin(half), 0.0, 0.0, dcos(half))


def rotate2(a: float, b: float, theta: float) -> tuple[float, float]:
    """Rotate the 2-vector (a, b) by `theta` radians (dsim `rotate2`, returns dsim's `{a, b}`).

    Local (v, w) to world (y, z) is `rotate2(v, w, theta)`; world to local is `-theta`.
    """
    c = dcos(theta)
    s = dsin(theta)
    return a * c - b * s, a * s + b * c
