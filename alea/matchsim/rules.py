"""Match rules for the abstract match simulator: timing, point values and the hive tip table.

PLACEHOLDERS. None of these numbers are in `alea.game` yet. `alea/game/biobuzz.py` holds
geometry and launcher constants only, and adding rule values there is a game-values change that
needs physics-reviewer and the user's sign-off. Each value below is read from the Competition
Manual (sections 10.1, 10.3.1 B and Table 10-3, as read 2026-11-08) or is dsim's model, and must
move to `alea/game` via a physics-reviewed PR, after which this module should import them from
there. Geometry (hive positions, mouth y) is NOT duplicated here: import it from
`alea.game.biobuzz`.

Known gaps, so nobody trusts the numbers too far:
- The SWARM ranking point (16 leave + park points) is not modelled; ranking points here are the
  tip-count ones only.
- Per manual 10.5 a tip that completes during the transition counts as AUTO; this simulator
  instead blocks all launches during the transition (they do not score).
- What a tip does to the balls in the cell, and the trigger of the Bottom Nectar Bonus, are
  unverified: see `TipBehaviour`. That is an open decision for the user.
"""

# ruff: noqa: E501  (the source/placeholder tags make value lines long on purpose)
from enum import Enum

# fmt: off
# --- match timing, seconds
AUTO_DURATION_S = 30.0  # source: Competition Manual 10.1 (as read 2026-11-08); placeholder until moved to alea/game
TRANSITION_DURATION_S = 8.0  # source: Competition Manual 10.1 (as read 2026-11-08); placeholder until moved to alea/game
TELEOP_DURATION_S = 120.0  # source: Competition Manual 10.1 (as read 2026-11-08); placeholder until moved to alea/game
ENDGAME_DURATION_S = 30.0  # last part of teleop; UNVERIFIED (not confirmed against the manual); placeholder until moved to alea/game

TELEOP_START_S = AUTO_DURATION_S + TRANSITION_DURATION_S
MATCH_END_S = TELEOP_START_S + TELEOP_DURATION_S  # 158 s
ENDGAME_START_S = MATCH_END_S - ENDGAME_DURATION_S

# --- points
POINTS_TIP_AUTO = 20  # source: Competition Manual section 10 Table 10-2 (as read 2026-11-08); placeholder until moved to alea/game
POINTS_TIP_TELEOP = 20  # source: Competition Manual section 10 Table 10-2 (as read 2026-11-08); placeholder until moved to alea/game
POINTS_LEAVE = 3  # source: Competition Manual section 10 Table 10-2 (as read 2026-11-08); placeholder until moved to alea/game
POINTS_PARK_AUTO = 5  # source: Competition Manual section 10 Table 10-2 (as read 2026-11-08); placeholder until moved to alea/game
POINTS_PARK_TELEOP = 5  # source: Competition Manual section 10 Table 10-2 (as read 2026-11-08); placeholder until moved to alea/game
POINTS_BALL_IN_UP_CELL_END = 2  # pollen or nectar in an up-facing cell at the end; source: Competition Manual section 10 Table 10-2 (as read 2026-11-08); placeholder until moved to alea/game
POINTS_BOTTOM_NECTAR = 5  # Bottom Nectar Bonus; its trigger is UNVERIFIED, only paid in TipBehaviour.NECTAR_STAYS_DOWN; source: Competition Manual section 10 Table 10-2 (as read 2026-11-08); placeholder until moved to alea/game
# Flower and garden points exist in the manual; the abstract simulator does not model them.
POINTS_FLOWER = 2  # not modelled; source: Competition Manual section 10 Table 10-2 (as read 2026-11-08); placeholder until moved to alea/game
POINTS_GARDEN = 1  # not modelled; source: Competition Manual section 10 Table 10-2 (as read 2026-11-08); placeholder until moved to alea/game

# --- game pieces
POLLEN_ON_FIELD = 40  # shared by both alliances; source: Competition Manual 10.3.1 B (as read 2026-11-08); placeholder until moved to alea/game
NECTAR_STAGED_IN_RAISED_CELL = 3  # each alliance's raised cell starts with this much nectar; source: Competition Manual 10.3.1 B; placeholder until moved to alea/game
NECTAR_STAGED_IN_ALLIANCE_AREA = 5  # waiting in each alliance area; source: Competition Manual 10.3.1 B; placeholder until moved to alea/game
NECTAR_PER_ALLIANCE = NECTAR_STAGED_IN_RAISED_CELL + NECTAR_STAGED_IN_ALLIANCE_AREA  # 8 per alliance
NECTAR_RELEASED_PER_TIP = 1  # source: Competition Manual 10.1 (as read 2026-11-08); placeholder until moved to alea/game
NECTAR_RELEASE_ALL_TIME_LEFT_S = 60.0  # all remaining nectar is released with this much time left; source: Competition Manual 10.1 (as read 2026-11-08); placeholder until moved to alea/game
NECTAR_RELEASE_ALL_AT_S = MATCH_END_S - NECTAR_RELEASE_ALL_TIME_LEFT_S

# --- ranking points
RP_TIP_THRESHOLDS = (4, 7)  # tips for one ranking point each; source: Competition Manual Table 10-3, "all other events" (Premier events differ); the SWARM RP is not modelled; placeholder until moved to alea/game

# --- hive tip table: pollen needed in the up cell to tip, given 0..5 nectar in that cell
# source: dsim's model (BB_TIP_POLLEN, same as alea/hifi/hive_constants.py). Only the 0-nectar (8) and
# 3-nectar (3) entries are backed by the Event Field Setup Guide (PORTING.md item 8); the rest are
# dsim's. Placeholder until moved to alea/game.
TIP_POLLEN_BY_NECTAR = (8, 7, 6, 3, 1, 0)
# fmt: on


class TipBehaviour(Enum):
    """What happens to the balls in a cell when its hive tips. OPEN DECISION for the user.

    The real behaviour and the Bottom Nectar Bonus trigger are unverified. In both modes no
    pollen ever vanishes from the shared pool.
    """

    # Every ball in the tipped cell goes back to the field: pollen to the shared pool, nectar to
    # the owner's available nectar. No Bottom Nectar Bonus is paid.
    SPILL_TO_FIELD = "spill_to_field"
    # Pollen returns to the pool, but the cell's nectar stays in the lowered cell and pays
    # POINTS_BOTTOM_NECTAR each at the end.
    NECTAR_STAYS_DOWN = "nectar_stays_down"


def pollen_to_tip(nectar_in_cell: int) -> int:
    """Pollen the up cell needs to tip with this much nectar in it (nectar above 5 counts as 5)."""
    return TIP_POLLEN_BY_NECTAR[min(max(nectar_in_cell, 0), len(TIP_POLLEN_BY_NECTAR) - 1)]


class MatchPhase(Enum):
    AUTO = "auto"
    TRANSITION = "transition"
    TELEOP = "teleop"
    ENDGAME = "endgame"  # last ENDGAME_DURATION_S of teleop


def phase_at(t_s: float) -> MatchPhase:
    """Phase at match time t_s in [0, MATCH_END_S]; raises ValueError outside the match."""
    if t_s < 0 or t_s > MATCH_END_S:
        raise ValueError(f"t_s={t_s} is outside the match [0, {MATCH_END_S}]")
    if t_s < AUTO_DURATION_S:
        return MatchPhase.AUTO
    if t_s < TELEOP_START_S:
        return MatchPhase.TRANSITION
    if t_s < ENDGAME_START_S:
        return MatchPhase.TELEOP
    return MatchPhase.ENDGAME


def tip_points(phase: MatchPhase) -> int:
    """Points for one tip in this phase (no tips count in the transition here; see module doc)."""
    if phase is MatchPhase.AUTO:
        return POINTS_TIP_AUTO
    if phase in (MatchPhase.TELEOP, MatchPhase.ENDGAME):
        return POINTS_TIP_TELEOP
    return 0


def ranking_points_for_tips(tips: int) -> int:
    return sum(tips >= n for n in RP_TIP_THRESHOLDS)
