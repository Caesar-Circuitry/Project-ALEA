# alea.matchsim

Abstract, event-driven match simulator over robot cycles (no physics). Design: decision record
`docs/decisions/0010-match-simulator.md`.

**Roadmap phase:** 7

## What is here

| File | Role |
|---|---|
| `rules.py` | match timing, point values, ball counts, tip table (all PLACEHOLDERS), `MatchPhase`, `phase_at` |
| `shots.py` | `ShotSuccessModel` protocol, `PlaceholderShotModel`, `TableShotModel`, `LutSpeedModel` |
| `robot.py` | `RobotProfile`: cycle parameters and the robot routine |
| `policies.py` | `ConstantCyclePolicy`, `NoOpPolicy` for partners and opponents |
| `match.py` | `simulate_match(red, blue, shot_model, seed) -> MatchResult` |
| `run.py`, `__main__.py` | batch runner and CLI |
| `search.py` | generic seeded optimiser; see feature/7-matchsim-search |

## Run

```
uv run python -m alea.matchsim --matches 1000 --seed 1 [--config my.yaml] [--out results/matchsim]
```

Red robot 0 is "ours". Prints mean and sd of our score, tips and the score breakdown; writes
`matches.csv` (one row per match, with the per-match seed) and `summary.json` to the output
directory (default `results/matchsim/`, git-ignored). Same `--seed` gives identical files.

## YAML config

All keys optional; missing top-level keys fall back to the built-in default match.

```yaml
tip_behaviour: spill_to_field   # or nectar_stays_down; see Open decisions
shot_model:
  type: placeholder        # or: table
  efficiency: 0.45         # PlaceholderShotModel args: efficiency, speed_noise_frac,
  speed_noise_frac: 0.03   #   aim_noise_deg, peak_make, speed_window_frac, aim_window_frac
  aim_noise_deg: 2.0
  # type: table
  # summary_dir: results/study     # a finished shot study; also aim_deg, speed_pct, robot_speed_in_s
red:                       # robot 0 of red is "ours"
  - type: profile          # RobotProfile fields: name, drive_speed_in_s, intake_s_per_ball,
    name: ours             #   balls_per_load, shot_interval_s, spinup_s, shoot_spot_audience_up_in
    drive_speed_in_s: 45   #   [x, y], shoot_spot_rear_up_in, pickup_spot_in, start_spot_in,
    balls_per_load: 3      #   target_hive (own/red/blue), tip_policy, nectar_target_per_cell,
                           #   flywheel_bias_frac, park_time_s, auto_balls, auto_leave, auto_park
  - type: constant_cycle   # ConstantCyclePolicy: cycle_time_s, balls_per_cycle, make_rate,
    cycle_time_s: 20       #   shot_gap_s, start_s, park_time_s, leave, name
    make_rate: 0.5
blue:
  - {type: noop, leave: true, park: true}   # NoOpPolicy: name, leave, park
```

Positions are inches in the `alea.game` field frame. Unknown keys raise an error.

## Placeholders

None of these are in `alea.game` yet; moving them there is a game-values change that needs
physics-reviewer and the user's sign-off. Each carries its source in `rules.py`.

| Value | Source | Replaced by |
|---|---|---|
| Timing 30 s auto, 8 s transition, 120 s teleop | Manual 10.1 | `alea.game` |
| Endgame = last 30 s of teleop | UNVERIFIED | `alea.game` |
| Tip 20 (auto), 20 (teleop); leave 3; park 5 auto, 5 teleop; 2 per ball in an up cell at the end | Manual Table 10-2 | `alea.game` |
| Bottom Nectar Bonus 5 (trigger unverified, paid only in `nectar_stays_down`); flower 2, garden 1 (not modelled) | Manual Table 10-2 | `alea.game` |
| 40 pollen; each raised cell starts with 3 nectar, 5 more wait in the alliance area (8 per alliance) | Manual 10.3.1 B | `alea.game` |
| 1 nectar released per tip, all remaining at 60 s left | Manual 10.1 | `alea.game` |
| Ranking points at 4 and 7 tips (SWARM RP at 16 leave+park points not modelled) | Manual Table 10-3, "all other events" (Premier differs) | `alea.game` |
| Tip table `{8,7,6,3,1,0}` pollen by 0..5 nectar | dsim `BB_TIP_POLLEN` (= `alea/hifi/hive_constants.py`); only the 0-nectar (8) and 3-nectar (3) entries are backed by the Event Field Setup Guide | `alea.game` |
| Assumed flywheel efficiency 0.45 | last factor of `TICKS_TO_IN_S` | hive-shot-lab calibration |
| `PlaceholderShotModel` shape and peak, `RobotProfile` and policy defaults | guesses | video and log data, FTCScout |

## Open decisions for the user

- **What a tip does to the balls in the cell.** `tip_behaviour: spill_to_field` (default,
  matches `docs/knowledge-base.md` and dsim: the lowered cell cannot hold balls) returns all of
  them to the field (pollen to the shared pool, nectar to the owner's available nectar) and pays
  no Bottom Nectar Bonus. `nectar_stays_down` keeps the nectar in the lowered cell and pays the
  bonus per nectar at the end. Pollen never vanishes from the pool in either mode. The real
  behaviour and the bonus trigger are unverified.
- The cell that becomes raised after a tip starts empty here (the manual's 3-nectar staging is
  applied only to the starting raised cell).
- A tip completing in the transition counts as auto per manual 10.5; the simulator instead
  blocks launches in the transition.

## Needs real data

Cycle times and shot efficiency distribution (hive-shot-lab calibration), opponent profiles
(FTCScout), a distance-resolved make rate (the shot study gives only aggregate rates), and the
rule values above.

## GPU-queue entry: large parameter sweep

- **What:** 10^5 matches for each cell of a grid of robot profiles (for example drive speed x
  intake time x balls per load x shot interval, about 3^4 = 81 cells, 8.1 x 10^6 matches), one
  YAML per cell, results compared by mean score and tips.
- **Command:** one run per cell, in parallel over the cores:
  `uv run python -m alea.matchsim --matches 100000 --seed 1 --config sweep/cell_NN.yaml --out results/matchsim/cell_NN`
- **GPU:** none. The simulator is pure CPU numpy and Python with heap scheduling and small
  per-event work; a GPU does not help. Estimate on CPU only.
- **Time:** about 0.5 ms per match single-threaded (measured: 2000 default matches in 1 s
  including start-up, in the dev container). Allow 1 ms for richer profiles: 8.1 x 10^6
  matches is about 1 to 2.5 core-hours, under 1 h on 4 cores.
- **Cost:** a 4 to 8 vCPU cloud CPU instance at about $0.2 to $0.4 per hour, so about $0.5 or
  less; free on a team laptop.
- **Outputs:** per cell `matches.csv` (10^5 rows, ~15 MB, git-ignored) and `summary.json`; a
  merged table of cell parameters against mean and sd of our score for the decision. Only
  valid once the rule placeholders and cycle times are real; before that treat as relative.
