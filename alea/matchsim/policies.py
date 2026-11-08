"""Simple parameterised partner and opponent policies (no shot model needed).

Same interface as `RobotProfile`: `run(ctx)` is a generator yielding waits in seconds. A policy
launches balls at a fixed cadence and make rate instead of driving and aiming. Defaults are
PLACEHOLDERS until opponent profiles are built from FTCScout data.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from alea.matchsim.rules import AUTO_DURATION_S, MATCH_END_S, TELEOP_START_S

if TYPE_CHECKING:
    from collections.abc import Iterator

    from alea.matchsim.match import MatchContext


@dataclass
class NoOpPolicy:
    """A robot that does not shoot. Optionally takes the passive leave and park points."""

    name: str = "noop"
    leave: bool = False
    park: bool = False

    def run(self, ctx: "MatchContext") -> "Iterator[float]":
        if self.leave:
            yield 1.0
            ctx.award_leave()
        if self.park:
            yield MATCH_END_S - 1.0 - ctx.t_s
            ctx.award_park(auto=False)


@dataclass
class ConstantCyclePolicy:
    """Every `cycle_time_s` it launches `balls_per_cycle` balls, each scoring with `make_rate`.

    Balls come from the shared pollen pool, so the field can run dry. Active in teleop from
    `start_s` until `park_time_s` before the end; `leave` and `park` add the passive points.
    """

    cycle_time_s: float = 20.0  # placeholder
    balls_per_cycle: int = 3  # placeholder
    make_rate: float = 0.5  # placeholder
    shot_gap_s: float = 0.5
    start_s: float = TELEOP_START_S
    park_time_s: float = 0.0  # 0 = never parks
    leave: bool = False
    name: str = "cycle"

    def __post_init__(self):
        if self.cycle_time_s <= 0 or self.balls_per_cycle < 0:
            raise ValueError("cycle_time_s must be > 0 and balls_per_cycle >= 0")
        if self.cycle_time_s < self.balls_per_cycle * self.shot_gap_s:
            raise ValueError("cycle_time_s is shorter than the shots in it")
        if not 0.0 <= self.make_rate <= 1.0:
            raise ValueError("make_rate must be in [0, 1]")

    def run(self, ctx: "MatchContext") -> "Iterator[float]":
        end_s = MATCH_END_S - self.park_time_s
        if self.leave:
            yield 1.0
            ctx.award_leave()
        if self.start_s > ctx.t_s:
            yield self.start_s - ctx.t_s
        while ctx.t_s + self.cycle_time_s <= end_s:
            cycle_start_s = ctx.t_s
            if AUTO_DURATION_S < ctx.t_s < TELEOP_START_S:
                yield TELEOP_START_S - ctx.t_s
                continue
            got = ctx.take_pollen(self.balls_per_cycle)
            for _ in range(got):
                made = bool(ctx.rng.random() < self.make_rate)
                ctx.launch(made, "pollen")
                if not made:
                    ctx.return_pollen(1)
                yield self.shot_gap_s
            yield max(cycle_start_s + self.cycle_time_s - ctx.t_s, 0.0) or 1e-9
        if self.park_time_s > 0:
            if ctx.t_s < end_s:
                yield end_s - ctx.t_s
            ctx.award_park(auto=False)
