"""Uses the dsim port (commit 62d2446e2ebdf416548fa1641847289bf47cdf36, genius0412); ALEA glue.

License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim); lives under the hifi licence.

The hive SESSION model of fidelity "hifi": a seeded sequence of fired shots fed into one hive,
run through the ported dsim hive logic (`alea.hifi.hive`). It answers "how often and how fast
does the hive tip when this robot, with this condition's errors, keeps shooting at it?".

What is modelled
----------------
* A session is `shots_per_session` fired shots, one every `shot_interval_s`. Each shot scores
  with probability `p_score`, the score rate (hits / fired) that the UNCHANGED fast kernel
  (`alea.sim.study.Study.run`) measured for the same condition. Shots are independent.
* A scored ball is a pollen element offered to the hive as a descending ball at the centre of a
  cell opening, travelling inboard. `hive_accepts` decides whether it is captured. Which cell it
  is aimed at is the explicit parameter `retarget_after_tip` (below).
* The hive starts as the field is staged: the red hive, up cell `BB_HIVE_UP_STAGED`, with
  `initial_nectar` nectar in it (3, Event Field Setup Guide 11.1, PORTING.md evidence item 7).
* Every tick (`tick_s`) the hive is stepped with `hive_step`: tip table (`hive_will_tip`),
  4 s swing timer with the rate rising with surplus, release at 2 s left (`contents` spill, the
  spill poses come from `spill_poses` with a seeded RNG), flip of the up cell at the end.
* Reported per condition: tips per session, share of sessions with at least one tip, time from
  session start to the first swing start and to the first completed tip, elements captured,
  rejected (offered while the aimed cell was not the taking one) and spilled.

What is NOT modelled
--------------------
* No ball-to-ball or ball-to-hive contacts, no 3D hive, no robot contacts (not ported).
* The shot kernel still treats the hive as at rest (30 degrees). A ball that scores in the
  kernel is captured by the logic even if the hive is swinging; only the cell-side rule of
  `hive_accepts` can reject it. No physics of balls landing on a moving cell.
* Spilled elements are counted and given poses, then removed; a robot never catches them, and
  no spilled ball is re-shot. Nectar is not shot; the hive holds only the staged nectar.
* The robot's position is not tracked per shot; only the condition's aggregate score rate is
  used, so position-dependent scoring and fire-hold are inside `p_score`, not in the session.
* Restitution is not used by the hive logic here (`hive_deflect`, the only user of dsim's
  0.3 miss bounce, is not called). It enters only through the study's per-condition `bounce`
  axis, in the fast kernel. It is an OPEN number (PORTING.md evidence item 9); nothing is chosen.
* Cell width, height and opening height are dsim's (`hive_constants.py`); they are open too
  (PORTING.md items 4 to 6). Frame: see `alea.hifi.frame`; positions here are only used for the
  capture test.

Explicit parameters (no default is chosen for the first four; see `SessionParams`)
-----------------------------------------------------------------------------------
`n_sessions`, `shots_per_session`, `shot_interval_s` (how often the robot shoots, not measured),
`retarget_after_tip` (does the driver aim at whichever cell is taking elements now, or keep
aiming at the cell that was up at the start). `initial_nectar` defaults to the field-setup
evidence; `tick_s` is numerical resolution (1/60 s as in the dsim timer traces); `alliance` is red.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from alea.hifi.frame import alea_to_dsim, dsim_to_alea
from alea.hifi.hive import (
    Alliance,
    BbCellSide,
    BbElementKind,
    HiveState,
    SpillPose,
    Vec2,
    Vec3,
    hive_accepts,
    hive_approach_sign,
    hive_cell_pos,
    hive_step,
    hive_taking_side,
    spill_poses,
)
from alea.hifi.hive_constants import BB_HIVE_OPEN_Z, BB_HIVE_UP_STAGED

# hive_accepts only reads the signs of the velocity components, so the speed is a unit value.
_Z_MID_IN = (BB_HIVE_OPEN_Z[0] + BB_HIVE_OPEN_Z[1]) / 2

SUMMARY_KEYS = (
    "hive_sessions",
    "hive_shots_per_session",
    "hive_shot_interval_s",
    "hive_retarget_after_tip",
    "hive_initial_nectar",
    "hive_p_score_input",
    "hive_tips_mean",
    "hive_tips_sd",
    "hive_p_tip",
    "hive_first_swing_start_s_mean",
    "hive_first_tip_done_s_mean",
    "hive_captured_mean",
    "hive_rejected_mean",
    "hive_spilled_mean",
)


@dataclass(frozen=True)
class SessionParams:
    """The session parameters. The first four have no default on purpose: they are open."""

    n_sessions: int
    shots_per_session: int
    shot_interval_s: float
    retarget_after_tip: bool
    initial_nectar: int = 3
    tick_s: float = 1.0 / 60.0
    alliance: Alliance = "red"

    def __post_init__(self) -> None:
        if self.n_sessions < 1 or self.shots_per_session < 1:
            raise ValueError("n_sessions and shots_per_session must be at least 1")
        if self.shot_interval_s <= 0 or self.tick_s <= 0:
            raise ValueError("shot_interval_s and tick_s must be positive")
        if self.initial_nectar < 0:
            raise ValueError("initial_nectar must be >= 0")


@dataclass(frozen=True)
class SessionResult:
    tips: int
    first_swing_start_s: float | None
    first_tip_done_s: float | None
    scored: int
    captured: int
    rejected: int
    spilled: int
    spill_poses: tuple[SpillPose, ...]


def _kind_fn(n_nectar: int, alliance: Alliance) -> Callable[[int], BbElementKind]:
    def kind_of(element_id: int) -> BbElementKind:
        return alliance if element_id < n_nectar else "pollen"

    return kind_of


def offer_ball(hive: HiveState, alliance: Alliance, aimed_side: BbCellSide) -> bool:
    """Offer a scored ball aimed at one cell; True if `hive_accepts` captures it."""
    centre_alea = dsim_to_alea(hive_cell_pos(alliance, aimed_side))
    pos = alea_to_dsim(centre_alea)  # handed to the logic in dsim's frame
    sign = hive_approach_sign(aimed_side)
    return hive_accepts(hive, alliance, Vec2(pos.x, pos.y), _Z_MID_IN, Vec3(0.0, float(sign), -1.0))


def run_session(p_score: float, params: SessionParams, rng: np.random.Generator) -> SessionResult:
    """One session. `rng` draws the shot outcomes and the spill poses (deterministic per seed)."""
    alliance = params.alliance
    n_nectar = params.initial_nectar
    kind_of = _kind_fn(n_nectar, alliance)
    hive = HiveState(BB_HIVE_UP_STAGED[alliance], tuple(range(n_nectar)), 0, 0.0, False)  # type: ignore[arg-type]
    start_side = hive.up
    ticks_per_shot = max(1, round(params.shot_interval_s / params.tick_s))
    next_id = n_nectar
    tick = 0
    tips = scored = captured = rejected = spilled = 0
    poses: list[SpillPose] = []
    first_start: float | None = None
    first_done: float | None = None

    def step() -> None:
        nonlocal hive, tick, tips, spilled, first_start, first_done
        before = hive
        r = hive_step(hive, params.tick_s, kind_of)
        tick += 1
        t_s = tick * params.tick_s
        if r.spilled:
            poses.extend(spill_poses(before, alliance, len(r.spilled), rng.random))
            spilled += len(r.spilled)
        if before.tipping <= 0 < r.hive.tipping and first_start is None:
            first_start = t_s
        if r.tipped:
            tips += 1
            if first_done is None:
                first_done = t_s
        hive = r.hive

    for _ in range(params.shots_per_session):
        if rng.random() < p_score:
            scored += 1
            aimed = hive_taking_side(hive) if params.retarget_after_tip else start_side
            if offer_ball(hive, alliance, aimed):
                hive = HiveState(
                    hive.up,
                    (*hive.contents, next_id),
                    hive.tips,
                    hive.tipping,
                    hive.released,
                    hive.swing_rate,
                )
                next_id += 1
                captured += 1
            else:
                rejected += 1
        for _ in range(ticks_per_shot):
            step()
    while hive.tipping > 0:  # let a swing in progress finish
        step()
    return SessionResult(
        tips, first_start, first_done, scored, captured, rejected, spilled, tuple(poses)
    )


def _mean_or_nan(values: list[float | None]) -> float:
    got = [v for v in values if v is not None]
    return float(np.mean(got)) if got else float("nan")


def run_sessions(p_score: float, params: SessionParams, seed_key: list[int]) -> dict:
    """`n_sessions` sessions seeded by `seed_key`; returns the SUMMARY_KEYS row."""
    rng = np.random.default_rng(seed_key)
    res = [run_session(p_score, params, rng) for _ in range(params.n_sessions)]
    tips = np.array([r.tips for r in res], dtype=float)
    return {
        "hive_sessions": params.n_sessions,
        "hive_shots_per_session": params.shots_per_session,
        "hive_shot_interval_s": params.shot_interval_s,
        "hive_retarget_after_tip": int(params.retarget_after_tip),
        "hive_initial_nectar": params.initial_nectar,
        "hive_p_score_input": p_score,
        "hive_tips_mean": float(tips.mean()),
        "hive_tips_sd": float(tips.std()),
        "hive_p_tip": float((tips > 0).mean()),
        "hive_first_swing_start_s_mean": _mean_or_nan([r.first_swing_start_s for r in res]),
        "hive_first_tip_done_s_mean": _mean_or_nan([r.first_tip_done_s for r in res]),
        "hive_captured_mean": float(np.mean([r.captured for r in res])),
        "hive_rejected_mean": float(np.mean([r.rejected for r in res])),
        "hive_spilled_mean": float(np.mean([r.spilled for r in res])),
    }
