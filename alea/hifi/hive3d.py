"""Ported from dsim by genius0412, commit 62d2446e2ebdf416548fa1641847289bf47cdf36.

License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim). Not the license of the rest
of ALEA.

The PURE part of dsim's 3D hive: `src/games/biobuzz/sim3d/hive3d.ts` plus the few helpers it
reads from `tilt.ts`, `bodies.ts` and `math3.ts`. There is NO rigid-body engine here. Dsim's tray
is a Rapier revolute body; its angle and angular velocity are results of a solve, and this module
never produces them. The caller supplies them (`body_theta_rad`, `Hive3dState.angle` /
`ang_vel`), exactly as dsim's functions read them from the engine or from the world JSON.

What is ported:

- `insideCell`, `hiveContentsTorque`, `hiveRestoringTorque`, `hiveHoldTorque`, `stopAngle`,
  `tippingFromAngle`;
- `hiveDynamicTick` (`hive3dJointTick`): swing bookkeeping from a given angle: tipping countdown,
  release and the SPILLS event, the TIP and its event, the failed-swing reset, spill tagging;
- the DECISION of `hiveDetentHold` (`detent_decision`): whether to creep, hold, wake, and what
  pose to pin, as a plain result the caller applies to its own body. Dsim's Rapier writes
  (`setAngvel`, `setRotation`, `wakeUp`) are returned as data, not performed;
- `hiveTiltAngle`, `hiveTrayRefTheta` (`tilt.ts`), `hivePivotX`, `hiveCellLocalBox` (CAD path),
  `hiveTrayComW`, `hiveTrayMassProps`, `elementMass` (`bodies.ts`).

Not ported (see alea/hifi/PORTING.md): the engine, `hiveContactPass`, `hive3dTick` (the
kinematic tray, off by default), the algebraic fallback of `hiveCellLocalBox`, the calibration
overrides, and `trayTilt` (needs dsim's `datan2`, which is only used to read the Rapier body).

Like dsim, state is immutable here: each tick returns new values and the caller keeps them.
Arithmetic follows the TypeScript expression order. Trig is dsim's `dsin` / `dcos`.
"""

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Literal

from alea.hifi.hive import (
    Alliance,
    BbCellSide,
    BbElementKind,
    hive_load,
    hive_will_tip,
    other_side,
)
from alea.hifi.hive3d_constants import (
    BB3_ELEMENT_MASS,
    BB3_HIVE_ARM,
    BB3_HIVE_BALLAST,
    BB3_HIVE_BALLAST_AT,
    BB3_HIVE_DETENT,
    BB3_HIVE_PIVOT_Z,
    BB3_HIVE_REST_W,
    BB3_HIVE_STOP_DEG,
    BB3_HIVE_TIP_CREEP_W,
    BB3_HIVE_TRAY_MASS,
    BB3_NECTAR_MASS_RATIO,
    BB_HIVE_TILT_DEG,
    BB_HIVE_X,
    BB_POLLEN_R,
    BB_TIP_SWING_S,
    GRAVITY,
    HIVE_CELL_BOXES,
    HiveLocalBox,
)
from alea.hifi.hive_math import dsin
from alea.hifi.math3 import rotate2, tilt_quat_x

ALLIANCES: tuple[Alliance, ...] = ("red", "blue")

# the rest tilt in radians (hive3d.ts:97) and the angle that counts as AT a stop (hive3d.ts:100)
REST_RAD = (BB_HIVE_TILT_DEG * math.pi) / 180
STOP_RAD = (BB3_HIVE_STOP_DEG * math.pi) / 180


@dataclass(frozen=True)
class Hive3dState:
    """dsim `BbHiveState` as the 3D hive sees it. `angle` / `ang_vel` are dsim's optional
    `angle` / `angVel` (rad, rad/s; None = undefined). dsim's world JSON holds them rounded to 4
    decimals; the caller decides which value to put here."""

    up: BbCellSide
    contents: tuple[int, ...]
    tips: int
    tipping: float
    released: bool
    angle: float | None = None
    ang_vel: float | None = None


@dataclass(frozen=True)
class Ball:
    """The fields of a dsim world ball the hive reads: id, plane position (x, y), height `z`
    (of the sphere's bottom, as dsim stores it), radius `r` (None = dsim's `undefined`, which
    means `BB_POLLEN_R`), `state_kind` ('held' / 'stock' are skipped) and `color`."""

    id: int
    x: float
    y: float
    z: float
    r: float | None = None
    state_kind: str = "ground"
    color: str = "yellow"


@dataclass(frozen=True)
class TrayBody:
    """The only facts the detent reads from dsim's Rapier tray body: its tilt about X (what
    `trayTilt(body)` returns, rad) and its angular velocity vector (rad/s). The caller supplies
    them; nothing here simulates the body."""

    theta_rad: float
    angvel: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class DetentDecision:
    """What dsim's `hiveDetentHold` would do to ONE tray this tick, as data.

    `creep_angvel_x_rad_s`: if not None, `body.setAngvel({x: v, y: 0, z: 0}, true)` is called.
    `held`: the new `engine.hiveHeld[a]`. `wake`: `body.wakeUp()` and wake every element in the
    hive's `contents`. `pin_angle_rad`: if not None, `body.setRotation(tiltQuatX(angle), false)`.
    `zero_angvel`: `body.setAngvel({0, 0, 0}, false)`. Order in dsim: creep, then (at a stop)
    wake or pin.
    """

    creep_angvel_x_rad_s: float | None
    held: bool
    wake: bool
    pin_angle_rad: float | None
    zero_angvel: bool


@dataclass(frozen=True)
class JointTickResult:
    """Outcome of one `hive_dynamic_tick` for one alliance. `nectar_due_inc` is what dsim adds to
    `bb.nectarDue[a]`; `events` are the strings it pushes to `world.events`; `spill` is the
    updated `bb.spill` map (ball id to alliance), None while dsim's `bb.spill` is undefined."""

    hive: Hive3dState
    nectar_due_inc: int
    events: tuple[str, ...]
    spill: dict[int, Alliance] | None


def _js_max(a: float, b: float) -> float:
    """JavaScript `Math.max` of two numbers: NaN if either is NaN (Python's `max` is not)."""
    if math.isnan(a) or math.isnan(b):
        return math.nan
    return b if b > a else a


def _js_min(a: float, b: float) -> float:
    """JavaScript `Math.min` of two numbers: NaN if either is NaN."""
    if math.isnan(a) or math.isnan(b):
        return math.nan
    return b if b < a else a


def _sign(x: float) -> float:
    """JavaScript `Math.sign`."""
    if x > 0:
        return 1.0
    if x < 0:
        return -1.0
    return x  # +-0 or NaN


# --- tilt.ts ------------------------------------------------------------------


def hive_tilt_angle(hive: Hive3dState | None) -> float:
    """The tray tilt right now, rad (dsim `hiveTiltAngle`, tilt.ts:40): the joint's own `angle`
    when present and finite, else the timer's formula."""
    if hive is None:
        return REST_RAD
    if hive.angle is not None and math.isfinite(hive.angle):
        return hive.angle
    sign = 1 if hive.up == "north" else -1
    if not (hive.tipping > 0):
        return sign * REST_RAD
    p = _js_min(1, _js_max(0, 1 - hive.tipping / BB_TIP_SWING_S))
    return sign * REST_RAD * (1 - 2 * p)


def hive_tray_ref_theta(alliance: Alliance) -> float:
    """dsim `hiveTrayRefTheta` (tilt.ts:68): 0 for both trays."""
    return 0


# --- bodies.ts ------------------------------------------------------------------


def hive_pivot_x(alliance: Alliance) -> float:
    """dsim `hivePivotX` (bodies.ts:467)."""
    return -BB_HIVE_X if alliance == "red" else BB_HIVE_X


def hive_cell_local_box(side_sign: Literal[1, -1], alliance: Alliance) -> HiveLocalBox:
    """dsim `hiveCellLocalBox` (bodies.ts:503), the CAD path only (`BB3_FIELD_COLLIDERS` true)."""
    return HIVE_CELL_BOXES[alliance]["north" if side_sign > 0 else "south"]


def hive_tray_com_w(alliance: Alliance) -> float:
    """dsim `hiveTrayComW` (bodies.ts:604): mid-height of a cell's interior."""
    north = hive_cell_local_box(1, alliance)
    south = hive_cell_local_box(-1, alliance)
    return (north.w_min + north.w_max + south.w_min + south.w_max) / 4


@dataclass(frozen=True)
class TrayMassProps:
    mass: float
    com_w: float
    inertia: float


def hive_tray_mass_props(alliance: Alliance) -> TrayMassProps:
    """dsim `hiveTrayMassProps` (bodies.ts:613), without the test-only ballast override."""
    ballast_mass = BB3_HIVE_BALLAST
    ballast_w = BB3_HIVE_BALLAST_AT[1]
    mass = BB3_HIVE_TRAY_MASS + ballast_mass
    com_w = (BB3_HIVE_TRAY_MASS * hive_tray_com_w(alliance) + ballast_mass * ballast_w) / mass
    inertia = mass * BB3_HIVE_ARM * BB3_HIVE_ARM
    return TrayMassProps(mass, com_w, inertia)


def element_mass(is_nectar: bool) -> float:
    """dsim `elementMass` (bodies.ts:1712), pounds."""
    return BB3_ELEMENT_MASS * (BB3_NECTAR_MASS_RATIO if is_nectar else 1)


# --- hive3d.ts ------------------------------------------------------------------


def inside_cell(
    px: float,
    py: float,
    pz: float,
    alliance: Alliance,
    side_sign: Literal[1, -1],
    theta: float,
    min_depth: float = 0,
) -> bool:
    """Is a point inside one CELL's interior in that cell's own tilted frame? (hive3d.ts:121)"""
    box = hive_cell_local_box(side_sign, alliance)
    dx = px - hive_pivot_x(alliance)
    if abs(dx) > box.x_half:
        return False
    v, w = rotate2(py, pz - BB3_HIVE_PIVOT_Z, -theta)
    return v >= box.v_min and v <= box.v_max and w >= box.w_min and w <= box.w_max - min_depth


def _in_either_cell(b: Ball, alliance: Alliance, theta: float) -> bool:
    z = b.z + (BB_POLLEN_R if b.r is None else b.r)
    return inside_cell(b.x, b.y, z, alliance, 1, theta) or inside_cell(
        b.x, b.y, z, alliance, -1, theta
    )


def hive_contents_torque(balls: Iterable[Ball], alliance: Alliance, theta: float) -> float:
    """Torque about the pivot's X axis from everything in either of this hive's cells
    (hive3d.ts:165). `balls` is dsim's `world.balls`."""
    tau = 0
    for b in balls:
        if b.state_kind in ("held", "stock"):
            continue
        if not _in_either_cell(b, alliance, theta):
            continue
        m = element_mass(b.color == "red" or b.color == "blue")
        tau += -m * GRAVITY * b.y
    return tau


def hive_restoring_torque(alliance: Alliance, theta: float) -> float:
    """The tray's own restoring torque at tilt `theta` (hive3d.ts:188)."""
    props = hive_tray_mass_props(alliance)
    return props.mass * GRAVITY * props.com_w * dsin(theta)


def hive_hold_torque(alliance: Alliance, theta: float) -> float:
    """What the tray's weight plus the detent would hold against (hive3d.ts:219), without the
    calibration override."""
    return abs(hive_restoring_torque(alliance, theta)) + BB3_HIVE_DETENT


def stop_angle(sign: float) -> float:
    """The angle a tray at `sign` should be pinned to (hive3d.ts:224)."""
    return REST_RAD if sign >= 0 else -REST_RAD


def tipping_from_angle(theta: float, up_sign: float) -> float:
    """The timer's countdown that matches a live angle (hive3d.ts:451)."""
    p = _js_min(1, _js_max(0, (1 - (up_sign * theta) / REST_RAD) / 2))
    return _js_max(1e-4, BB_TIP_SWING_S * (1 - p))


def detent_decision(
    body: TrayBody,
    hive: Hive3dState,
    kind_of: Callable[[int], BbElementKind],
    was_held: bool,
) -> DetentDecision:
    """The decision logic of dsim's `hiveDetentHold` (hive3d.ts:242) for ONE alliance.

    `body` is the tray's state before this tick's solve, `hive` the world's hive record,
    `was_held` the previous `engine.hiveHeld[a]`. Whether the pin actually holds the tray, and
    what the tray then does, is the engine's business and is not modelled.
    """
    theta = body.theta_rad
    sign = 1 if theta >= 0 else -1
    at_stop = abs(theta) >= STOP_RAD
    up_sign = -1 if hive.up == "south" else 1
    load = hive_load(hive.contents, kind_of)
    far = -up_sign
    owed = (not at_stop) and hive.tipping > 0
    creep: float | None = None
    if owed and body.angvel[0] * far < BB3_HIVE_TIP_CREEP_W:
        creep = far * BB3_HIVE_TIP_CREEP_W
    if not at_stop:
        return DetentDecision(creep, False, False, None, False)
    if hive_will_tip(load):
        return DetentDecision(creep, False, was_held, None, False)
    target = stop_angle(sign)
    pin = target if abs(theta - target) > 1e-6 else None
    zero = body.angvel[0] != 0 or body.angvel[1] != 0 or body.angvel[2] != 0
    return DetentDecision(creep, True, False, pin, zero)


def hive_dynamic_tick(
    alliance: Alliance,
    hive: Hive3dState,
    body_theta_rad: float,
    balls: Iterable[Ball],
    spill: Mapping[int, Alliance] | None,
) -> JointTickResult:
    """dsim `hiveDynamicTick` / `hive3dJointTick` (hive3d.ts:352) for ONE alliance.

    dsim's loop body over `ALLIANCES`; call it once per alliance. `body_theta_rad` stands for
    `trayTilt(engine.hiveTrays[a])`, used only when `hive.angle` is undefined. `spill` is
    `bb.spill` (None = undefined); the returned `spill` is a new dict, never the input.

    In dsim `bb.spill` is ONE object shared by the red then blue loop iterations, and events
    are pushed red first. To match, call red first, feed red's returned `spill` into blue's
    call, and concatenate the events in that order.
    """
    theta = hive.angle if hive.angle is not None else body_theta_rad
    omega = hive.ang_vel if hive.ang_vel is not None else 0
    up_sign = 1 if hive.up == "north" else -1
    settled_at_far_stop = (
        abs(theta) >= STOP_RAD and _sign(theta) == -up_sign and abs(omega) < BB3_HIVE_REST_W
    )
    new_spill = None if spill is None else dict(spill)

    if hive.tipping > 0:
        if abs(theta) >= STOP_RAD and _sign(theta) == up_sign and abs(omega) < BB3_HIVE_REST_W:
            return JointTickResult(replace(hive, tipping=0, released=False), 0, (), new_spill)
        if settled_at_far_stop:
            done = Hive3dState(
                up=other_side(hive.up),
                contents=hive.contents,
                tips=hive.tips + 1,
                tipping=0,
                released=False,
                angle=hive.angle,
                ang_vel=hive.ang_vel,
            )
            return JointTickResult(done, 1, (f"{alliance.upper()} HIVE TIP",), new_spill)
        was_released = hive.released
        released = was_released or _sign(theta) != up_sign
        events: tuple[str, ...] = ()
        if released and not was_released:
            n = sum(1 for x in (new_spill or {}).values() if x == alliance)
            events = (f"{alliance.upper()} HIVE SPILLS {n or len(hive.contents)}",)
        out = replace(hive, tipping=tipping_from_angle(theta, up_sign), released=released)
        return JointTickResult(out, 0, events, new_spill)

    # settled: has the detent broken? The tray leaving its stop is the only evidence there is.
    if abs(theta) < STOP_RAD:
        if new_spill is None:
            new_spill = {}
        for b in balls:
            if b.state_kind in ("held", "stock"):
                continue
            if _in_either_cell(b, alliance, theta):
                new_spill[b.id] = alliance
        out = replace(hive, tipping=tipping_from_angle(theta, up_sign), released=False)
        return JointTickResult(out, 0, (), new_spill)
    return JointTickResult(hive, 0, (), new_spill)


__all__ = [
    "ALLIANCES",
    "REST_RAD",
    "STOP_RAD",
    "Ball",
    "DetentDecision",
    "Hive3dState",
    "JointTickResult",
    "TrayBody",
    "TrayMassProps",
    "detent_decision",
    "element_mass",
    "hive_cell_local_box",
    "hive_contents_torque",
    "hive_dynamic_tick",
    "hive_hold_torque",
    "hive_pivot_x",
    "hive_restoring_torque",
    "hive_tilt_angle",
    "hive_tray_com_w",
    "hive_tray_mass_props",
    "hive_tray_ref_theta",
    "inside_cell",
    "stop_angle",
    "tilt_quat_x",
    "tipping_from_angle",
]
