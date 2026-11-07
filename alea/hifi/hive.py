"""Ported from dsim by genius0412, commit 62d2446e2ebdf416548fa1641847289bf47cdf36.

License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim). Not the license of the rest
of ALEA.

Port of dsim's pure hive logic, `src/games/biobuzz/hive.ts`: capture into the up CELL, the load
against the tip table, the swing timer, the release and spill, and the deflection of a miss. Like
dsim, a hive is an immutable `HiveState` and every step returns a NEW one; nothing reads a world.
The caller supplies the colour lookup (`kind_of`) and the RNG (`rng`, yields [0, 1)).

Distances are inches, speeds in/s, times seconds, in dsim's field-centred frame. Constants are
dsim's own (`hive_constants.py`), not alea/game's. Function names are dsim's in snake_case;
type, constant and field names keep dsim's, except `swingRate` which is `swing_rate`.

Arithmetic follows the TypeScript expression order so the results are bit-identical IEEE doubles.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from alea.hifi.hive_constants import (
    BB_CELL_OPEN,
    BB_HIVE_ACCEPT_MARGIN,
    BB_HIVE_BOTTOM_Z,
    BB_HIVE_CELL_DY,
    BB_HIVE_LEN,
    BB_HIVE_MISS_REST,
    BB_HIVE_MISS_TANGENT,
    BB_HIVE_OPEN_Z,
    BB_HIVE_W,
    BB_HIVE_X,
    BB_SPILL_FAN,
    BB_SPILL_KICK,
    BB_SPILL_SPEED,
    BB_TIP_POLLEN,
    BB_TIP_RATE_MAX,
    BB_TIP_RATE_PER_EXTRA,
    BB_TIP_RELEASE_S,
    BB_TIP_SWING_S,
)
from alea.hifi.hive_math import dcos, dsin

Alliance = Literal["red", "blue"]
BbCellSide = Literal["north", "south"]
BbElementKind = Literal["pollen", "red", "blue"]


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class HiveState:
    """dsim `BbHiveState`. `swing_rate` is dsim's optional `swingRate` (None = undefined)."""

    up: BbCellSide
    contents: tuple[int, ...]
    tips: int
    tipping: float
    released: bool
    swing_rate: float | None = None


@dataclass(frozen=True)
class HiveLoad:
    pollen: int
    nectar: int


@dataclass(frozen=True)
class HiveStepResult:
    hive: HiveState
    tipped: bool
    spilled: tuple[int, ...]


@dataclass(frozen=True)
class HiveTimerResult:
    hive: HiveState
    tipped: bool
    releasing: bool


@dataclass(frozen=True)
class SpillPose:
    pos: Vec3
    vel: Vec3


@dataclass(frozen=True)
class HiveDeflection:
    pos: Vec3
    vel: Vec3


def other_side(side: BbCellSide) -> BbCellSide:
    return "south" if side == "north" else "north"


def hive_pivot(alliance: Alliance) -> Vec2:
    """The hive's pivot on the tiles: red x = -BB_HIVE_X, blue +BB_HIVE_X, both on y = 0."""
    return Vec2(-BB_HIVE_X if alliance == "red" else BB_HIVE_X, 0)


def hive_cell_pos(alliance: Alliance, side: BbCellSide) -> Vec2:
    """Horizontal centre of one CELL's opening."""
    p = hive_pivot(alliance)
    return Vec2(p.x, p.y + (BB_HIVE_CELL_DY if side == "north" else -BB_HIVE_CELL_DY))


def hive_approach_sign(up: BbCellSide) -> Literal[1, -1]:
    """Which way along y an element must travel to enter the up CELL (inboard)."""
    return -1 if up == "north" else 1


def hive_taking_side(hive: HiveState) -> BbCellSide:
    """The CELL taking elements now: `up`, or the other one after the release."""
    return other_side(hive.up) if hive.tipping > 0 and hive.released else hive.up


def hive_accepts(
    hive: HiveState,
    alliance: Alliance,
    pos: Vec2,
    z: float,
    vel: Vec3,
    margin: float = BB_HIVE_ACCEPT_MARGIN,
) -> bool:
    """Capture test for one flight element (descending, inbound, inside the footprint)."""
    if vel.z >= 0:
        return False
    side = hive_taking_side(hive)
    if vel.y * hive_approach_sign(side) <= 0:
        return False
    c = hive_cell_pos(alliance, side)
    if abs(pos.x - c.x) > BB_CELL_OPEN.w / 2 or abs(pos.y - c.y) > BB_CELL_OPEN.d / 2:
        return False
    return BB_HIVE_OPEN_Z[0] <= z <= BB_HIVE_OPEN_Z[1] + margin


def hive_load(contents: Sequence[int], kind_of: Callable[[int], BbElementKind]) -> HiveLoad:
    pollen = 0
    nectar = 0
    for element_id in contents:
        if kind_of(element_id) == "pollen":
            pollen += 1
        else:
            nectar += 1
    return HiveLoad(pollen, nectar)


def hive_will_tip(load: HiveLoad) -> bool:
    """The tip table lookup; past the end of the table the last row (0 pollen) holds."""
    return load.pollen >= BB_TIP_POLLEN[min(load.nectar, len(BB_TIP_POLLEN) - 1)]


def hive_surplus(load: HiveLoad) -> int:
    """How many elements the load is OVER its tip threshold (0 at or under)."""
    row = min(load.nectar, len(BB_TIP_POLLEN) - 1)
    over_pollen = load.pollen - BB_TIP_POLLEN[row]
    over_nectar = load.nectar - row
    return max(0, over_pollen + over_nectar)


def hive_swing_rate(load: HiveLoad) -> float:
    """The swing's rate multiplier: 1 at threshold, rising with the surplus, capped."""
    return min(BB_TIP_RATE_MAX, 1 + BB_TIP_RATE_PER_EXTRA * hive_surplus(load))


def hive_timer_step(
    hive: HiveState, dt: float, kind_of: Callable[[int], BbElementKind]
) -> HiveTimerResult:
    """The timer/trigger core: `contents` is carried through untouched (the caller owns it)."""
    if hive.tipping > 0:
        released = hive.released
        if released:
            rate = hive.swing_rate if hive.swing_rate is not None else 1
        else:
            rate = hive_swing_rate(hive_load(hive.contents, kind_of))
        left = hive.tipping - dt * rate
        if left > 0:
            releasing = not released and left <= BB_TIP_RELEASE_S
            return HiveTimerResult(
                replace(hive, tipping=left, released=released or releasing, swing_rate=rate),
                False,
                releasing,
            )
        return HiveTimerResult(
            HiveState(other_side(hive.up), hive.contents, hive.tips + 1, 0, False),
            True,
            not released,
        )
    load = hive_load(hive.contents, kind_of)
    if hive_will_tip(load):
        return HiveTimerResult(
            replace(hive, tipping=BB_TIP_SWING_S, released=False, swing_rate=hive_swing_rate(load)),
            False,
            False,
        )
    return HiveTimerResult(replace(hive), False, False)


def hive_step(
    hive: HiveState, dt: float, kind_of: Callable[[int], BbElementKind]
) -> HiveStepResult:
    """One tick of hive mechanics: the timer core, plus emptying `contents` at the release."""
    r = hive_timer_step(hive, dt, kind_of)
    contents = () if r.releasing else tuple(hive.contents)
    spilled = tuple(hive.contents) if r.releasing else ()
    return HiveStepResult(replace(r.hive, contents=contents), r.tipped, spilled)


def spill_poses(
    hive: HiveState, alliance: Alliance, count: int, rng: Callable[[], float]
) -> list[SpillPose]:
    """Where spilled elements re-enter the world and how fast they go.

    `rng` is drawn SIX times per pose, in order: x, y, speed, fan angle, kick direction, kick
    magnitude.
    """
    emptying = hive.up if hive.tipping > 0 else other_side(hive.up)
    c = hive_cell_pos(alliance, emptying)
    sign = 1 if emptying == "north" else -1
    cy = c.y + sign * (BB_CELL_OPEN.d / 2)
    v_min, v_max = BB_SPILL_SPEED
    out: list[SpillPose] = []
    for _ in range(count):
        x = c.x + (rng() * 2 - 1) * (BB_CELL_OPEN.w / 2)
        y = cy + (rng() * 2 - 1) * (BB_CELL_OPEN.d / 2)
        speed = v_min + rng() * (v_max - v_min)
        a = (rng() * 2 - 1) * BB_SPILL_FAN * (math.pi / 180)
        ka = rng() * 2 * math.pi
        kv = rng() * BB_SPILL_KICK
        out.append(
            SpillPose(
                Vec3(x, y, BB_HIVE_BOTTOM_Z),
                Vec3(speed * dsin(a) + kv * dcos(ka), sign * speed * dcos(a) + kv * dsin(ka), 0),
            )
        )
    return out


def _sign(x: float) -> float:
    """JavaScript `Math.sign` for finite numbers."""
    return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)


def hive_deflect(
    hive: HiveState, alliance: Alliance, prev: Vec3, pos: Vec3, vel: Vec3
) -> HiveDeflection | None:
    """A miss bounces off the hive body box; None if no face was crossed."""
    p = hive_pivot(alliance)
    lo = (p.x - BB_HIVE_W / 2, p.y - BB_HIVE_LEN / 2, BB_HIVE_BOTTOM_Z)
    hi = (p.x + BB_HIVE_W / 2, p.y + BB_HIVE_LEN / 2, BB_HIVE_OPEN_Z[1])

    def inside(q: Vec3) -> bool:
        return lo[0] <= q.x <= hi[0] and lo[1] <= q.y <= hi[1] and lo[2] <= q.z <= hi[2]

    if not inside(pos):
        return None
    eps = 0.01
    mouth = 1 if hive_taking_side(hive) == "north" else -1

    # the pivot plane, for anything travelling through the box along its axis
    if prev.y != pos.y and _sign(prev.y - p.y) != _sign(pos.y - p.y) and prev.y != p.y:
        t = (p.y - prev.y) / (pos.y - prev.y)
        at_x = prev.x + (pos.x - prev.x) * t
        at_z = prev.z + (pos.z - prev.z) * t
        if lo[0] <= at_x <= hi[0] and lo[2] <= at_z <= hi[2]:
            from_ = _sign(prev.y - p.y)
            return HiveDeflection(
                Vec3(at_x, p.y + from_ * eps, at_z),
                Vec3(vel.x * BB_HIVE_MISS_TANGENT, from_ * abs(vel.y) * BB_HIVE_MISS_REST, vel.z),
            )

    if inside(prev):
        return None

    # the slab crossed LAST is the face hit
    prev_a = (prev.x, prev.y, prev.z)
    pos_a = (pos.x, pos.y, pos.z)
    t_hit = -1.0
    axis = -1
    sgn = 0
    for ax in range(3):
        a = prev_a[ax]
        d = pos_a[ax] - a
        if a < lo[ax] and d > 0:
            t = (lo[ax] - a) / d
            if t > t_hit:
                t_hit, axis, sgn = t, ax, -1
        elif a > hi[ax] and d < 0:
            t = (hi[ax] - a) / d
            if t > t_hit:
                t_hit, axis, sgn = t, ax, 1
    if axis < 0:
        return None
    if axis == 2 and sgn == 1:  # the open top
        return None
    if axis == 1 and sgn == mouth:  # the mouth
        return None

    t = max(0.0, min(1.0, t_hit))
    hit = [prev_a[i] + (pos_a[i] - prev_a[i]) * t for i in range(3)]
    hit[axis] = (lo[axis] if sgn < 0 else hi[axis]) + sgn * eps

    out = [vel.x, vel.y, vel.z]
    if axis == 2:  # the underside: reverse the climb, dump most of the run
        out[2] = -abs(vel.z) * BB_HIVE_MISS_REST
        out[0] = vel.x * BB_HIVE_MISS_TANGENT
        out[1] = vel.y * BB_HIVE_MISS_TANGENT
    else:
        other = 1 if axis == 0 else 0
        out[axis] = sgn * abs(out[axis]) * BB_HIVE_MISS_REST
        out[other] = out[other] * BB_HIVE_MISS_TANGENT
    return HiveDeflection(Vec3(hit[0], hit[1], hit[2]), Vec3(out[0], out[1], out[2]))
