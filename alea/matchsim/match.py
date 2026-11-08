"""Event-driven match simulation over robot cycles (no physics).

`simulate_match(red, blue, shot_model, seed)` runs the 158 s match. Each robot is a generator
(see `RobotProfile.run`, `policies.py`) that yields waiting times; a heap of wake times
interleaves them. They share one pollen pool; each alliance has one hive with a raised cell
that fills until the placeholder tip table (`rules.TIP_POLLEN_BY_NECTAR`) is met. A tip scores,
empties the cell, flips which cell is raised and releases nectar. Everything random comes from
one `numpy.random.default_rng(seed)`, so a seed fixes the whole match.
"""

import heapq
import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from alea.game.biobuzz import (
    HIVE_AUDIENCE_MOUTH_Y_IN,
    HIVE_REAR_MOUTH_Y_IN,
    HIVE_UP,
    HIVE_X_IN,
    LAUNCH_EXIT_X_IN,
)
from alea.matchsim.rules import (
    MATCH_END_S,
    NECTAR_RELEASE_ALL_AT_S,
    NECTAR_RELEASED_PER_TIP,
    NECTAR_STAGED_IN_ALLIANCE_AREA,
    NECTAR_STAGED_IN_RAISED_CELL,
    POINTS_BALL_IN_UP_CELL_END,
    POINTS_BOTTOM_NECTAR,
    POINTS_LEAVE,
    POINTS_PARK_AUTO,
    POINTS_PARK_TELEOP,
    POLLEN_ON_FIELD,
    MatchPhase,
    TipBehaviour,
    phase_at,
    pollen_to_tip,
    ranking_points_for_tips,
    tip_points,
)
from alea.matchsim.shots import LutSpeedModel, ShotSuccessModel

ALLIANCES = ("red", "blue")
BREAKDOWN_KEYS = (
    "tip_auto",
    "tip_teleop",
    "leave",
    "park_auto",
    "park_teleop",
    "cell_end",
    "nectar_bottom",
)
Event = tuple[float, str, str, dict[str, Any]]  # (t_s, robot, kind, detail)


class Policy(Protocol):
    """Anything that can drive a robot: a generator of waits in seconds."""

    name: str

    def run(self, ctx: "MatchContext") -> Iterator[float]: ...


@dataclass
class Hive:
    x_in: float
    up_side: int  # -1 audience cell raised, +1 rear cell raised
    cell_pollen: int = 0
    cell_nectar: int = NECTAR_STAGED_IN_RAISED_CELL  # the raised cell starts with nectar
    down_nectar: int = 0  # nectar left in the lowered cell (NECTAR_STAYS_DOWN only)
    tips_auto: int = 0
    tips_teleop: int = 0

    @property
    def mouth_y_in(self) -> float:
        return HIVE_AUDIENCE_MOUTH_Y_IN if self.up_side < 0 else HIVE_REAR_MOUTH_Y_IN


@dataclass
class AllianceState:
    name: str
    hive: Hive
    nectar_stock: int = NECTAR_STAGED_IN_ALLIANCE_AREA  # not yet released
    nectar_available: int = 0
    points: dict[str, int] = field(default_factory=lambda: dict.fromkeys(BREAKDOWN_KEYS, 0))


@dataclass
class MatchResult:
    seed: int
    breakdown: dict[str, dict[str, int]]  # per alliance: components plus "total"
    tips: dict[str, int]
    tips_auto: dict[str, int]
    ranking_points: dict[str, int]  # tip-count RPs only (placeholder thresholds)
    events: list[Event]
    pollen_left: int  # pollen in the shared pool at the end
    pollen_in_cells: int  # pollen sitting in raised cells at the end (pool + this = 40 - in flight)

    def score(self, alliance: str) -> int:
        return self.breakdown[alliance]["total"]

    @property
    def red_score(self) -> int:
        return self.score("red")

    @property
    def blue_score(self) -> int:
        return self.score("blue")


class _World:
    def __init__(
        self, shot_model: ShotSuccessModel, rng: np.random.Generator, tip_behaviour: TipBehaviour
    ):
        self.tip_behaviour = tip_behaviour
        self.shot_model = shot_model
        self.rng = rng
        self.t_s = 0.0
        self.pool = POLLEN_ON_FIELD
        self.alliances = {
            n: AllianceState(n, Hive(HIVE_X_IN[i], HIVE_UP[i])) for i, n in enumerate(ALLIANCES)
        }
        self.events: list[Event] = []
        self.nectar_all_released = False
        self.speed_models: dict[float, LutSpeedModel] = {}

    def release_check(self) -> None:
        if not self.nectar_all_released and self.t_s >= NECTAR_RELEASE_ALL_AT_S:
            self.nectar_all_released = True
            for a in self.alliances.values():
                a.nectar_available += a.nectar_stock
                a.nectar_stock = 0


class MatchContext:
    """What a robot routine may see and do. One per robot."""

    def __init__(self, world: _World, alliance: str, robot: str, target: str):
        self._w = world
        self.alliance = alliance
        self.robot = robot
        self.target = target  # alliance whose hive this robot shoots at
        self._left = False
        self._parked = False

    # --- read
    @property
    def t_s(self) -> float:
        return self._w.t_s

    @property
    def rng(self) -> np.random.Generator:
        return self._w.rng

    @property
    def phase(self) -> MatchPhase:
        return phase_at(self._w.t_s)

    @property
    def own_hive_x_in(self) -> float:
        return HIVE_X_IN[ALLIANCES.index(self.alliance)]

    @property
    def target_hive_x_in(self) -> float:
        return self._w.alliances[self.target].hive.x_in

    def target_up_side(self) -> int:
        return self._w.alliances[self.target].hive.up_side

    def target_nectar_in_cell(self) -> int:
        return self._w.alliances[self.target].hive.cell_nectar

    def pool_pollen(self) -> int:
        return self._w.pool

    def nectar_available(self) -> int:
        self._w.release_check()
        return self._w.alliances[self.alliance].nectar_available

    # --- act
    def take_pollen(self, n: int) -> int:
        got = min(max(n, 0), self._w.pool)
        self._w.pool -= got
        return got

    def return_pollen(self, n: int) -> None:
        self._w.pool += n

    def log(self, kind: str, detail: dict[str, Any] | None = None) -> None:
        self._w.events.append((self._w.t_s, self.robot, kind, detail or {}))

    def award_leave(self) -> None:
        if not self._left:
            self._left = True
            self._w.alliances[self.alliance].points["leave"] += POINTS_LEAVE
            self.log("leave")

    def award_park(self, auto: bool) -> None:
        if not self._parked:
            self._parked = True
            key, pts = (
                ("park_auto", POINTS_PARK_AUTO) if auto else ("park_teleop", POINTS_PARK_TELEOP)
            )
            self._w.alliances[self.alliance].points[key] += pts
            self.log("park", {"auto": auto})

    def shoot(
        self, pos_in: tuple[float, float], kind: str, flywheel_bias_frac: float = 0.0
    ) -> bool:
        """Shoot from `pos_in` (field frame) at the target hive's raised cell using the LUT
        speed and the shot model. A pollen ball that misses is NOT returned to the pool (the
        caller holds it); a nectar ball that misses goes back to the available nectar."""
        w = self._w
        hive = w.alliances[self.target].hive
        dx = hive.x_in - pos_in[0]
        dy = hive.mouth_y_in - pos_in[1]
        dist_in = max(math.hypot(dx, dy) - abs(LAUNCH_EXIT_X_IN), 0.0)
        off_axis_deg = math.degrees(math.atan2(abs(dx), abs(dy))) if dy else 90.0
        lut = w.speed_models.setdefault(flywheel_bias_frac, LutSpeedModel(flywheel_bias_frac))
        ticks = lut.ticks_per_s(dist_in)
        if kind == "nectar":
            a = w.alliances[self.alliance]
            if a.nectar_available <= 0:
                return False
            a.nectar_available -= 1
        p = w.shot_model.p_make(dist_in, off_axis_deg, ticks, w.rng)
        made = bool(w.rng.random() < p)
        if kind == "nectar" and not made:
            w.alliances[self.alliance].nectar_available += 1
        self.launch(
            made, kind, {"dist_in": round(dist_in, 2), "off_axis_deg": round(off_axis_deg, 2)}
        )
        return made

    def launch(self, made: bool, kind: str, detail: dict[str, Any] | None = None) -> None:
        """Resolve one launch whose outcome is already decided (used by policies)."""
        w = self._w
        d = dict(detail or {}, ball=kind)
        if self.phase is MatchPhase.TRANSITION:
            self.log("blocked", d)
            if kind == "nectar" and made:
                w.alliances[self.alliance].nectar_available += 1
            return
        self.log("shot_made" if made else "shot_miss", d)
        if made:
            self._score_in_hive(kind)

    def _score_in_hive(self, kind: str) -> None:
        w = self._w
        owner = w.alliances[self.target]
        hive = owner.hive
        if kind == "nectar":
            hive.cell_nectar += 1
        else:
            hive.cell_pollen += 1
        if hive.cell_pollen >= pollen_to_tip(hive.cell_nectar):
            phase = self.phase
            if phase is MatchPhase.AUTO:
                hive.tips_auto += 1
                owner.points["tip_auto"] += tip_points(phase)
            else:
                hive.tips_teleop += 1
                owner.points["tip_teleop"] += tip_points(phase)
            self.log(
                "tip", {"hive": owner.name, "pollen": hive.cell_pollen, "nectar": hive.cell_nectar}
            )
            # the pool never loses pollen: the cell's pollen always goes back to the field
            w.pool += hive.cell_pollen
            if w.tip_behaviour is TipBehaviour.NECTAR_STAYS_DOWN:
                hive.down_nectar += hive.cell_nectar
            else:
                owner.nectar_available += hive.cell_nectar
            hive.cell_pollen = hive.cell_nectar = 0
            hive.up_side = -hive.up_side
            rel = min(NECTAR_RELEASED_PER_TIP, owner.nectar_stock)
            owner.nectar_stock -= rel
            owner.nectar_available += rel


def _build_breakdown(world: _World) -> dict[str, dict[str, int]]:
    out = {}
    for name, a in world.alliances.items():
        pts = dict(a.points)
        pts["cell_end"] = POINTS_BALL_IN_UP_CELL_END * (a.hive.cell_pollen + a.hive.cell_nectar)
        pts["nectar_bottom"] = POINTS_BOTTOM_NECTAR * a.hive.down_nectar
        pts["total"] = sum(pts[k] for k in BREAKDOWN_KEYS)
        out[name] = pts
    return out


def simulate_match(
    red: list[Any],
    blue: list[Any],
    shot_model: ShotSuccessModel,
    seed: int = 0,
    tip_behaviour: TipBehaviour = TipBehaviour.SPILL_TO_FIELD,
) -> MatchResult:
    """Simulate one match. `red` and `blue` hold RobotProfile or policy objects (anything with
    `name` and `run(ctx)`). Deterministic for a given seed."""
    rng = np.random.default_rng(seed)
    world = _World(shot_model, rng, tip_behaviour)
    heap: list[tuple[float, int, Iterator[float], MatchContext]] = []
    seq = 0
    for alliance, robots in (("red", red), ("blue", blue)):
        for i, robot in enumerate(robots):
            target = alliance
            th = getattr(robot, "target_hive", "own")
            if th in ALLIANCES:
                target = th
            ctx = MatchContext(world, alliance, f"{alliance}{i}:{robot.name}", target)
            gen = robot.run(ctx)
            try:
                wait_s = next(gen)
            except StopIteration:
                continue
            heapq.heappush(heap, (max(wait_s, 0.0), seq, gen, ctx))
            seq += 1
    while heap:
        wake_s, _, gen, ctx = heapq.heappop(heap)
        if wake_s > MATCH_END_S:
            continue
        world.t_s = wake_s
        world.release_check()
        try:
            wait_s = next(gen)
        except StopIteration:
            continue
        heapq.heappush(heap, (wake_s + max(wait_s, 0.0), seq, gen, ctx))
        seq += 1
    world.t_s = MATCH_END_S
    breakdown = _build_breakdown(world)
    tips = {n: a.hive.tips_auto + a.hive.tips_teleop for n, a in world.alliances.items()}
    return MatchResult(
        seed=int(seed),
        breakdown=breakdown,
        tips=tips,
        tips_auto={n: a.hive.tips_auto for n, a in world.alliances.items()},
        ranking_points={n: ranking_points_for_tips(t) for n, t in tips.items()},
        events=world.events,
        pollen_left=world.pool,
        pollen_in_cells=sum(x.hive.cell_pollen for x in world.alliances.values()),
    )
