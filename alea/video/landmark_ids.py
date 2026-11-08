"""Landmark id strings shared by the click log and the camera geometry code (phase 2).

An id names a known point on the BIOBUZZ field; it is never a coordinate. The point's world
position comes from ``alea.game.biobuzz`` and is looked up by the camera-fitting code, so a
change in game values never invalidates stored clicks. The naming convention (documented in
``alea/video/README.md``) is::

    field_floor_corner_{xlo|xhi}_{ylo|yhi}              z = 0, x/y at 0 or FIELD_SIZE_IN
    field_wall_top_corner_{xlo|xhi}_{ylo|yhi}           z = WALL_HEIGHT_IN
    hive_{red|blue}_pivot                               (HIVE_X_IN, HIVE_Y_IN, HIVE_PIVOT_HEIGHT_IN)
    hive_frame_corner_{xlo|xhi}_{ylo|yhi}_{zlo|zhi}     FRAME_X0/Y0/Z0 and + FRAME_NX/NY/NZ
    hive_{red|blue}_mouth_{audience|rear}               floor-plane use only
    edge_{floor|wall_top}_{xlo|xhi|ylo|yhi}             ONE clicked point somewhere along that
                                                        straight field edge (not a corner)
    custom_<name>                                       a mark not in alea.game (tile seam,
                                                        tape line); lowercase letters, digits, _

Anything else is rejected, so a typo cannot silently become a landmark.
"""

from __future__ import annotations

import re
from functools import cache
from itertools import product

from alea.game.biobuzz import (
    FIELD_SIZE_IN,
    FRAME_NX,
    FRAME_NY,
    FRAME_NZ,
    HIVE_AUDIENCE_MOUTH_Y_IN,
    HIVE_PIVOT_HEIGHT_IN,
    HIVE_REAR_MOUTH_Y_IN,
    HIVE_X_IN,
    HIVE_Y_IN,
    WALL_HEIGHT_IN,
)

CUSTOM_PREFIX = "custom_"
_CUSTOM_RE = re.compile(r"^custom_[a-z0-9][a-z0-9_]*$")
ALLIANCES = ("red", "blue")  # order of HIVE_X_IN
EDGE_TAGS = ("floor", "wall_top")
EDGE_SIDES = ("xlo", "xhi", "ylo", "yhi")
_LO_HI = (("xlo", "xhi"), ("ylo", "yhi"), ("zlo", "zhi"))


@cache
def known_landmark_ids() -> tuple[str, ...]:
    """Every landmark id derived from the game constants, in a stable order."""
    if len(HIVE_X_IN) != len(ALLIANCES):
        raise RuntimeError("alea.game HIVE_X_IN no longer has one entry per alliance")
    if min(FIELD_SIZE_IN, WALL_HEIGHT_IN, HIVE_PIVOT_HEIGHT_IN, HIVE_Y_IN) <= 0:
        raise RuntimeError("alea.game field constants must be positive")
    if min(FRAME_NX, FRAME_NY, FRAME_NZ) <= 0 or HIVE_AUDIENCE_MOUTH_Y_IN == HIVE_REAR_MOUTH_Y_IN:
        raise RuntimeError("alea.game hive frame or mouth constants are degenerate")

    ids: list[str] = []
    for x, y in product(_LO_HI[0], _LO_HI[1]):
        ids.append(f"field_floor_corner_{x}_{y}")
    for x, y in product(_LO_HI[0], _LO_HI[1]):
        ids.append(f"field_wall_top_corner_{x}_{y}")
    for alliance in ALLIANCES:
        ids.append(f"hive_{alliance}_pivot")
    for x, y, z in product(*_LO_HI):
        ids.append(f"hive_frame_corner_{x}_{y}_{z}")
    for alliance in ALLIANCES:
        for mouth in ("audience", "rear"):
            ids.append(f"hive_{alliance}_mouth_{mouth}")
    for tag in EDGE_TAGS:
        for side in EDGE_SIDES:
            ids.append(f"edge_{tag}_{side}")
    return tuple(ids)


def is_edge_id(landmark_id: str) -> bool:
    """True for the straight-edge ids; a click on one is a point anywhere along that edge."""
    return landmark_id.startswith("edge_") and landmark_id in known_landmark_ids()


def is_valid_landmark_id(landmark_id: str) -> bool:
    return landmark_id in known_landmark_ids() or bool(_CUSTOM_RE.match(landmark_id))
