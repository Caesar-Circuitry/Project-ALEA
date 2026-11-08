# 0011: Match reflection pipeline

Status: accepted (design); thresholds and point values are placeholders.

## Context

Video review in ALEA is mainly for post-match reflection: after a match, a large model reviews
what happened and says what the drivers could have improved. The evidence is the robot log (when
and from where the robot fired, how fast the flywheel was), the score overlay read from a
streamed match (when points and tips appeared), and a simulator baseline (how often a shot from
that distance should score). Later the video can add field state (where balls and robots were).
That is roadmap phase 5. The pipeline code should not need a model to run, and a model should not
need to see video: minors appear on match footage.

## Decision

- Reflection first. The product is a short, ranked list of driver improvements with evidence.
- Inputs: a robot log (`.rlog` / `.wpilog`, launches from `alea.data.launches`), overlay events
  (JSONL, schema version 1, produced by `alea.video.overlay`), and a `Baseline` (expected make
  probability against distance, from a finished shot-study `summary.csv` or a placeholder curve).
  Field state from video is a future input; the report's `gaps` list already names it.
- A local pipeline does the arithmetic: `timeline.py` builds a `MatchTimeline` (launches, score
  steps, tips, phase boundaries, idle gaps, cadence), `baseline.py` computes expected points,
  `report.py` produces the report JSON (metrics, timeline, rule-based findings, gaps), `prompt.py`
  wraps that JSON in a self-contained prompt. A large model only reads text. Nothing in the
  package calls a model or the network; the user pastes `prompt.txt` where they choose.
- No frames or images are read, stored or referenced. The prompt carries no file names, paths or
  personal data; only the match label, alliance and team number the user passed in.
- `inferred` tagging. Every metric, timeline entry and finding has `source`. `measured` means it
  comes straight from a log value or an overlay event. `inferred` means any assumption was filled
  in: a placeholder baseline curve, a log clock assumed to start with the match, phases from
  nominal durations instead of the on-screen clock, a launch with no Aim sample. A value that
  depends on an inferred input is inferred. `gaps` lists each such substitution.
- Clock alignment. Overlay events give match time as `150 - clock_s_remaining` (the clock read
  off the overlay). The log clock starts when logging started. `align_log_to_match` tries every
  offset that would put one score step a fixed lag (1 s, placeholder) after one launch and keeps
  the offset with the most launch/score-step pairs within 1 s, needing at least two pairs
  (`measured`). With fewer pairs, the first launch is lined up with the first scoring event
  (`inferred`). Without overlay events the log is assumed to start at match start, offset 0
  (`inferred`). When the overlay has no clock readings, match time falls back to the video time
  minus the video time of the first `auto` event (`inferred`). The offset is a report metric
  (`log_to_match_offset_s`) with its `source`. Launch events are tagged with the offset's source
  because their place on the match clock depends on it.
- Game values (2 points per made ball, 20 per tip, phase lengths, the 95 % setpoint rule, idle
  gap length) are module constants marked as placeholders until a physics-reviewed PR moves them
  into `alea.game`.

## Consequences

- The pipeline works with logs alone today and gets better as overlay events and a real baseline
  arrive; the report says which parts are inferred.
- The study's `summary.csv` has no distance column (the study samples random spots), so a
  baseline from it sets the level and the distance shape stays the placeholder shape, `inferred`.
  A summary with a `dist_in` column is used as measured.
- Needs real data before it can be trusted: a real log of a streamed match, overlay events read
  from the user's clip, a real study baseline, and real score-lag and flywheel-dip numbers.
  All thresholds were tuned on synthetic data.
- Rule-based findings are a floor, not the analysis; the large model's answer is the product and
  is only as good as the data in the report.
