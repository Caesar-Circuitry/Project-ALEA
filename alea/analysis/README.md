# alea.analysis

Calibration against real shots, driver critique, robot health monitoring.

**Roadmap phase:** 3-5

## Modules

- `hivelab.py`: reads a hive-shot-lab CSV (`read_hivelab_csv`, column mapping with defaults,
  `HiveLabFormatError` on a missing required column `shot, time_s, v0_in_s, angle_deg`), builds
  `ShotMeasurement` rows (`to_measurements`), reads and writes the measurement CSV, and has
  `wheel_surface_speed_in_s(ticks_per_s)` and `efficiency(v_exit_in_s, ticks_per_s)`.
  `SIM_ASSUMED_EFFICIENCY = 0.45` is a placeholder for the last factor of
  `alea.game.TICKS_TO_IN_S`; a physics-reviewed PR should export it from `alea.game`.
- `sync.py`: `offset_from_cue`, `match_offset` (burst-gap matching, returns `SyncResult`) and
  `join_launches`. Offset convention: `offset_s = t_log_s - t_video_s`.
- `cli.py` / `__main__.py`: `python -m alea.analysis hivelab-import <csv> --log <rlog|wpilog>
  [--cue-video-s X --cue-log-s Y] --out measurements.csv`, or `--launches-csv <t_s,before,after,dip>`
  for launches already known. Prints the sync result and the join count; exit 2 on a bad input
  or missing column, 3 if sync finds fewer than 2 pairs. `--map field=column` overrides columns.
- `efficiency.py` (branch feature/3-efficiency-estimate): bootstrap/Bayes efficiency and drag estimate.
- `critique/` (branch feature/4-driver-critique): driver-critique features.
- `reflection/` (branch feature/5-match-reflection): match-reflection prototype.

## Calibration track

Launcher calibration is a controlled track separate from video review of matches: phone
slow-motion (120/240 fps), green screen, one AprilTag in the ball plane, analysed with
hive-shot-lab (Apache-2.0, not vendored). Its CSV is joined to the robot log of the same session
to get exit speed against flywheel speed, so efficiency (and drag) can be estimated.

## Measurement CSV contract

Header, in this order. Empty cell = unknown. Measurements stay in this file, never in the
`launch` table.

| column | unit | meaning |
|---|---|---|
| measurement_id | | first 16 hex of sha1(`video_file`\|`shot_index`) |
| source | | `hivelab` |
| video_file, shot_index | | video name and shot number in it |
| burst_index, burst_size | | burst (shots closer than 0.6 s) and its size |
| t_video_s | s | time of the shot in the video |
| t_log_s | s | matched launch time in the log (empty if unjoined) |
| launch_id | | `launch.id` when known |
| v_exit_in_s | in/s | ball exit speed |
| angle_deg | deg | launch angle |
| apex_in | in | trajectory apex |
| drag_per_s | 1/s | fitted linear drag k |
| fit_rms_in | in | trajectory fit residual |
| result | | IN / LOW / HIGH / SHORT |
| flywheel_ticks_per_s_before, _after, dip_ticks_per_s | ticks/s | flywheel around the launch |
| wheel_surface_speed_in_s | in/s | `ticks_before / 28 * 2*pi*1.89` |
| efficiency | | `v_exit_in_s / wheel_surface_speed_in_s` (sim assumes 0.45) |
| notes | | e.g. `no launch within 0.25 s` |

## Sync method

`match_offset` takes every `log - video` difference as a candidate offset, scores it by the
number of video shot times within +-0.05 s of a log launch, and median-refines the best. It
survives a missed and a spurious shot. `ambiguous` is true if a different offset (more than
0.1 s away) scores within one pair of the best (periodic firing); then use a cue. Decision 0007:
the detector marks the first loop of the dip, a constant bias of about +20 to +40 ms. The offset
absorbs it, so it is not the true camera clock offset. `join_launches` takes the nearest
unused launch within +-0.25 s and keeps unmatched shots with a note.

## Needs real data

- A real hive-shot-lab CSV; the column set was read from code on 2026-11-08 and may change
  with the first export (use `--map`).
- A real robot log of the same session, and a cue (clap or LED) if the shots are periodic.
- The synthetic tests prove the algorithms, not the real clock bias or the efficiency value.
