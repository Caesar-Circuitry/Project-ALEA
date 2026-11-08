"""Robot cycle profile for the abstract match simulator.

A `RobotProfile` is data: how fast the robot drives, how long it takes to load, where it
stands to shoot. `run(ctx)` turns it into a generator that yields waiting times in seconds; the
match scheduler resumes it at each wake time. Positions are inches in the `alea.game` field
frame. Every default is a PLACEHOLDER guess until cycle times are measured from match video
(hive-shot-lab) or logs; none is a game rule.
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from alea.matchsim.rules import AUTO_DURATION_S, MATCH_END_S, TELEOP_START_S

if TYPE_CHECKING:
    from collections.abc import Iterator

    from alea.matchsim.match import MatchContext

TIP_POLICIES = ("shoot_until_tip",)
FIELD_CENTER_PICKUP_IN = (70.65, 35.0)  # placeholder pickup spot, field frame
SPOT_Y_AUDIENCE_UP_IN = 20.0  # placeholder shooting row when the audience cell is up
SPOT_Y_REAR_UP_IN = 120.0  # placeholder shooting row when the rear cell is up
START_Y_IN = 9.0  # placeholder start row


class OutOfTime(Exception):
    """Raised inside a robot routine when the next action would overrun the park window."""


@dataclass
class RobotProfile:
    name: str = "ours"
    drive_speed_in_s: float = 40.0  # placeholder
    intake_s_per_ball: float = 0.8  # placeholder
    balls_per_load: int = 3  # hopper size; placeholder
    shot_interval_s: float = 0.6  # placeholder
    spinup_s: float = 1.5  # flywheel spin-up before each load; placeholder
    # shooting spots in the field frame; None = in line with the target hive at the
    # placeholder rows above
    shoot_spot_audience_up_in: tuple[float, float] | None = None
    shoot_spot_rear_up_in: tuple[float, float] | None = None
    pickup_spot_in: tuple[float, float] = FIELD_CENTER_PICKUP_IN
    start_spot_in: tuple[float, float] | None = None
    target_hive: str = "own"  # "own", "red" or "blue"
    tip_policy: str = "shoot_until_tip"  # keep shooting the up cell until it tips
    nectar_target_per_cell: int = 0  # nectar to put in the up cell before pollen (0 = none)
    flywheel_bias_frac: float = 0.0  # LUT mis-calibration, fraction of commanded ticks/s
    park_time_s: float = 8.0  # endgame park takes this long; 0 = never parks
    auto_balls: int = 3  # preloaded balls shot in auto
    auto_leave: bool = True
    auto_park: bool = False
    leave_time_s: float = 1.5  # placeholder

    def __post_init__(self):
        if self.tip_policy not in TIP_POLICIES:
            raise ValueError(f"tip_policy must be one of {TIP_POLICIES}")
        if self.target_hive not in ("own", "red", "blue"):
            raise ValueError("target_hive must be 'own', 'red' or 'blue'")
        if self.drive_speed_in_s <= 0 or self.balls_per_load < 1:
            raise ValueError("drive_speed_in_s must be > 0 and balls_per_load >= 1")
        if min(self.intake_s_per_ball, self.spinup_s) < 0 or self.shot_interval_s <= 0:
            raise ValueError("times must be >= 0 and shot_interval_s > 0")

    def spot_for(self, hive_x_in: float, up_side: int) -> tuple[float, float]:
        """Shooting spot for the hive whose raised cell is on `up_side` (-1 audience, +1 rear)."""
        if up_side < 0:
            return self.shoot_spot_audience_up_in or (hive_x_in, SPOT_Y_AUDIENCE_UP_IN)
        return self.shoot_spot_rear_up_in or (hive_x_in, SPOT_Y_REAR_UP_IN)

    def run(self, ctx: "MatchContext") -> "Iterator[float]":
        """Generator for one match; yields seconds to wait, `ctx.t_s` is the wake time."""
        hive_x = ctx.target_hive_x_in
        pos = self.start_spot_in or (ctx.own_hive_x_in, START_Y_IN)
        park_s = self.park_time_s
        park_start_s = MATCH_END_S - park_s if park_s > 0 else MATCH_END_S
        held = 0

        def drive(to: tuple[float, float]) -> float:
            return math.dist(pos, to) / self.drive_speed_in_s

        def need(dt_s: float, limit_s: float) -> None:
            if ctx.t_s + dt_s > limit_s:
                raise OutOfTime

        def wants_nectar() -> bool:
            return (
                ctx.target_nectar_in_cell() < self.nectar_target_per_cell
                and ctx.nectar_available() > 0
            )

        def shoot_load(limit_s: float):
            """Shoot what is held (and wanted nectar); returns via nonlocal updates."""
            nonlocal pos, held
            while True:
                use_nectar = wants_nectar()
                if not use_nectar and held == 0:
                    return
                spot = self.spot_for(hive_x, ctx.target_up_side())
                if spot != pos:
                    dt_s = drive(spot)
                    need(dt_s + self.spinup_s, limit_s)
                    yield dt_s
                    pos = spot
                    yield self.spinup_s
                need(self.shot_interval_s, limit_s)
                kind = "nectar" if use_nectar else "pollen"
                made = ctx.shoot(pos, kind, self.flywheel_bias_frac)
                if kind == "pollen":
                    held -= 1
                    if not made:
                        ctx.return_pollen(1)
                yield self.shot_interval_s

        # --- auto: shoot the preload, then leave (and optionally park)
        auto_limit_s = AUTO_DURATION_S - (self.leave_time_s if self.auto_leave else 0.0)
        held = ctx.take_pollen(self.auto_balls)
        try:
            if held:
                spot = self.spot_for(hive_x, ctx.target_up_side())
                need(drive(spot) + self.spinup_s, auto_limit_s)
                yield drive(spot)
                pos = spot
                yield self.spinup_s
                yield from shoot_load(auto_limit_s)
        except OutOfTime:
            pass
        if self.auto_leave and ctx.t_s + self.leave_time_s <= AUTO_DURATION_S:
            yield self.leave_time_s
            ctx.award_leave()
            if self.auto_park:
                ctx.award_park(auto=True)
        if ctx.t_s < TELEOP_START_S:
            yield TELEOP_START_S - ctx.t_s

        # --- teleop: load, drive to the shooting spot, shoot until the hive tips, repeat
        try:
            while True:
                if held == 0 and not wants_nectar():
                    if ctx.pool_pollen() == 0:
                        need(1.0, park_start_s)
                        yield 1.0
                        continue
                    dt_s = drive(self.pickup_spot_in)
                    need(dt_s + self.intake_s_per_ball, park_start_s)
                    yield dt_s
                    pos = self.pickup_spot_in
                    n = min(self.balls_per_load, max(ctx.pool_pollen(), 1))
                    need(self.intake_s_per_ball * n, park_start_s)
                    yield self.intake_s_per_ball * n
                    held = ctx.take_pollen(self.balls_per_load)
                    ctx.log("intake", {"balls": held})
                yield from shoot_load(park_start_s)
        except OutOfTime:
            pass
        if park_s > 0 and ctx.t_s < park_start_s:
            yield park_start_s - ctx.t_s
        if park_s > 0:
            ctx.award_park(auto=False)
