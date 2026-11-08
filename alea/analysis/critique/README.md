# alea.analysis.critique

Quantitative driver-critique features per match, computed from our robot's log only: cycle
times and bursts, idle gaps, shot cadence, flywheel readiness and aim quality. The
match-reflection pipeline and a large-model critique prompt consume them.

**Roadmap phase:** 4

- `signals.py`: `MatchSignals`, the format-neutral input (`from_log`, `from_logdata`, `from_synthetic`).
- `features.py`: `compute_features(signals)` returns `CritiqueFeatures` (`to_dict()`, `summary_lines()`).
- `__main__.py`: `python -m alea.analysis.critique <log> [--json out.json] [--synthetic SEED]`.

Match phase timing (30 s auto, 8 s transition, 120 s teleop, 30 s endgame) is a placeholder in
`features.py` until it moves to `alea/game` through a physics-reviewed PR. Log time 0 is assumed
to be the match start. Everything here is tested on synthetic logs only.
