# 0010. Abstract match simulator

Status: proposed (branch `feature/7-matchsim-core`)

## Context

Roadmap phase 7 asks for a match simulation: given our robot, a partner and two opponents, how
many points do we expect, how often do we tip the hive, and which robot change (faster cycle,
steadier shot, a nectar routine) is worth the build time? The Warp shot simulator answers a
different question (does one ball score from one spot) and is far too slow and too detailed to
play 10^5 matches. Match-level decisions depend on cycle times, ball supply, the tip table and
scoring, not on ball flight.

Two facts constrain the design. First, `alea/game` holds geometry and launcher constants only;
point values, match timing, ball counts, nectar release and ranking-point thresholds are not
there, and adding them is a game-values change that needs physics-reviewer and the user's
sign-off. Second, nearly every behavioural number (cycle times, real shot efficiency, opponent
strength) is unmeasured today.

## Decision

Build `alea.matchsim` as an abstract, event-driven simulator, not a physics engine.

- **Robot cycles, not trajectories.** Each robot is a generator that yields waiting times
  (drive, intake, spin-up, shot interval, park). A heap of wake times interleaves up to four
  robots over the 158 s match (30 s auto, 8 s transition, 120 s teleop with a 30 s endgame).
  There is no continuous time stepping and no collision model.
- **Shared state.** One pollen pool (40 balls) shared by both alliances; per alliance a hive
  with a raised cell (pollen and nectar counts), nectar stock and availability. A tip fires when
  the pollen in the raised cell reaches the table entry for the nectar in it, scores, empties
  the cell, flips which cell is raised, and releases one nectar; the remaining nectar is
  released with 60 s left. Hive geometry and mouth y come from `alea.game.biobuzz`.
- **Pluggable shot model.** The simulator never fires a ball. It asks a `ShotSuccessModel`
  (`p_make(distance_in, off_axis_deg, ticks_per_s, rng)`), with the flywheel speed taken from
  the launch LUT in `alea.game`. Shipped: an analytic `PlaceholderShotModel` whose shape is not
  fitted to data and which treats 0.45 as the assumed flywheel efficiency (the last factor of
  `TICKS_TO_IN_S`); a `TableShotModel` built from a finished shot-study `summary.csv`.
- **Placeholders for game points.** Rule values live in `alea/matchsim/rules.py`, each tagged
  with its source and "placeholder until moved to alea/game". They must move to `alea/game` in a
  physics-reviewed PR with the user's approval; until then results are indicative only.
- **Tip behaviour is an open decision.** What a tip does to the balls in the cell, and the
  trigger of the Bottom Nectar Bonus, are unverified. A `TipBehaviour` setting chooses:
  `SPILL_TO_FIELD` (default; matches dsim and `docs/knowledge-base.md`: balls return to the
  field, no bonus) or `NECTAR_STAYS_DOWN` (nectar stays and pays the bonus). Pollen never leaves
  the shared pool in either mode. The user must decide, with the manual in hand.
- **Initial state.** Each raised cell starts with 3 nectar and 5 nectar wait in each alliance
  area (manual 10.3.1 B), so the first tip needs the table entry for 3 nectar.
- **Seeds and reproducibility.** One `numpy.random.default_rng(seed)` per match, passed down
  through the context; no global random state. The runner derives one independent integer seed
  per match from the run seed with `SeedSequence.spawn`, writes it to `matches.csv`, so any
  single match can be replayed with `simulate_match(..., seed=<row seed>)`.
- **Parameter-space runs.** Large sweeps are a Python loop over independent matches
  (embarrassingly parallel). The sweep command and cost are in `alea/matchsim/README.md` (the
  GPU-queue entry).

## Needs real data

| Input | Placeholder now | Real source |
|---|---|---|
| Cycle times (drive, intake, shot interval, spin-up) | guesses in `RobotProfile` | match video and robot logs via the hive-shot-lab tracking track |
| Real make rate and flywheel efficiency distribution | `PlaceholderShotModel` (0.45 assumed) | hive-shot-lab calibration; then a model fitted per distance and angle |
| Opponent profiles | `ConstantCyclePolicy` guesses | FTCScout event data (scores, tipping counts) mapped to cycle time and make rate |
| Game points, ball counts, tip table | `rules.py` placeholders | Competition Manual and dsim, moved into `alea/game` |
| Shot model vs distance | study gives aggregate rates only | a distance-resolved shot study or video fit |

## Consequences

- Fast: thousands of matches per second on one CPU core; sweeps are cheap and need no GPU.
- Abstract: no robot-robot interference, defence, field congestion, driver variation or partial
  failures. Those would be added as policy behaviours or extra events, not physics.
- Results are only as good as the placeholders. Until the game values and cycle data are real,
  use the simulator for relative comparisons (does X beat Y), not absolute score predictions.
- Two `ShotSuccessModel` implementations must stay interchangeable, so the protocol is the
  contract the sibling `search` module and later fitted models rely on.
- A follow-up PR to `alea/game` is needed to retire the placeholder table; this record does not
  do it.
