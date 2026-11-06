---
paths:
  - "alea/sim/**"
  - "alea/game/**"
  - "alea/hifi/**"
  - "tests/golden/**"
---

# Working near the physics

- `alea/sim/shotsim.py` and `alea/sim/study.py` are frozen: identical to the Java Code Sim. A
  hook blocks edits. Moving them with `git mv` is fine; changing a number or a branch is not.
- Any change here ends with `just selftest` and its output quoted in the report. The bar is
  agreement with Java on at least 99.9 % of the 10,000 golden shots.
- Constants move, they never change: when you extract a value into `alea/game/biobuzz.py`, keep
  the number bit-for-bit, add a `# source:` comment (game manual section, CAD, or measured), and
  make sure `tests/test_game_constants.py` still matches the snapshot.
- `tests/golden/` is append-only. Never regenerate `golden_shots.npy`; ask the user for it.
- Units in names (`dist_in`, `speed_in_s`, `angle_deg`). Field geometry comes only from
  `alea/game/`; if a ported source (dsim) disagrees, list the differences for the user instead of
  picking one.
- `alea/hifi/` carries dsim's PolyForm Noncommercial 1.0.0 license. Every ported file starts
  with the "Ported from dsim by genius0412" line and the pinned commit hash from `DSIM_VERSION`.
- Anything that changes behaviour here needs a `physics-reviewer` pass and a human sign-off on
  the PR with the "changes physics?" box explained.
