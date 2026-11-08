# 0009. Reflection first: re-scope of the video and analysis track

Date: 2026-11-08. Amends [0008](0008-video-geometry-and-click-log.md) (see its amendment note).

## Context

Decision 0008 set the video track as a physics calibration path. The plan was: field geometry,
click-and-log, then a ballistic fit (stage 2.3) that tunes the shot simulator from video.

Three things changed on 2026-11-08.

1. The team wants feedback on matches. A driver asks "what could I have done better in that
   match?" The video track should answer that question first.
2. Calibrating the launcher from video is hard to do well with phone footage from the pits.
   It needs a controlled setup: slow motion, a known tag, a green screen. That is a separate
   job from match review.
3. Minors are visible on match streams. Footage must stay on the team's machines.

## Decision

1. **Video review is for post-match reflection.** A model reviews one match. It reads the
   robot logs, an overlay score timeline and a simulation baseline. Later it reads field state
   taken from video. It writes what the drivers could have improved.
   - The output is text and JSON only.
   - No frames leave the machine.
   - Any value filled in where data is missing is tagged `inferred`.
2. **Launcher calibration is a separate, controlled track.** A person runs a slow-motion phone
   test (120 or 240 fps) with a green screen and one AprilTag in the ball plane. The footage is
   analysed with the external tool `hive-shot-lab` (Apache-2.0, v1.0.0, github.com/boltonftc/hive-shot-lab).
   - We use it as an external tool. We do not vendor it.
   - Efficiency is `v_exit_in_s / (flywheel_ticks_per_s / 28 * 2 * pi * 1.89)`.
   - The sim assumes 0.45. The measured value is compared with that number.
   - StarterBot launcher: 1:1 drive, 28 ticks per revolution, 1.89 in wheel radius.
   - The procedure is in [the calibration protocol](../calibration-protocol.md).
3. **Stage 2.3 is deprioritised.** The ballistic fit from video is not on the critical path.
   Calibration moves to the `hive-shot-lab` track (phase 3).
4. **Phases 5, 6 and 7 get their first stages.**
   - Phase 5: match reflection report (decision 0011 covers its prompt and report format).
   - Phase 6: a Streamlit web app for the team (`alea/web/`). The `web` extra already exists.
   - Phase 7: a match-level strategy simulator (decision 0010) and a seeded optimiser.
5. **Long term: field-state extraction.** A local model finds field state in video: field mask,
   background model, robots and balls. A large model then interprets that state and fills gaps
   with `inferred` tags. This is decision 0013, pending a feasibility spike.
6. **Placeholders until real data.** These values stay as documented placeholders:
   - Top-plate height: 16.0 in (to be measured).
   - Hive-cell landing surface: 49.13 in (to be measured).
   - Game point values: tip 20, leave 3, park 5, ball in the up cell 2, and the rest.
     These are not in `alea/game/` yet. Branches use documented placeholders until a
     physics-reviewed PR adds the table.

## Consequences

- The shot sim's frozen files do not change. `alea/sim/shotsim.py` and `alea/sim/study.py` are
  untouched by this decision.
- The 0.45 efficiency stays the sim's assumption until the hive-shot-lab run produces a
  measured value with an interval. Nothing changes the sim on the strength of one session.
- Calibration needs real footage. Every number marked as a placeholder needs a measurement:
  the top-plate height, the landing surface height, and the tag size written on each sheet.
- Game point values need a decision from the user. Until then, reflection reports label every
  points figure as a placeholder.
- The video track gets a privacy rule. Footage stays local, and only text and JSON reports
  are shared.
- Stage 2.2b (match segmenter and overlay events) becomes the next video step. It needs no
  real footage: it is tested on a synthetic stream.
- Open for the user: the points table, and whether the team accepts an external Apache-2.0
  tool in the calibration path.
