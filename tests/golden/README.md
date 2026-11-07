# Golden test data

Known-answer files. Never regenerate `golden_shots.npy`; ask for it.

- `golden_shots.npy`: 10,000 Java Code Sim shots and the Java answer for each (sha1 `2a13bb587528795e350fc0577e40fb2f7d36bcf4`). Columns: x, y, heading, ticks/s, vx, vy, ball diameter, restitution, result.
- `game_constants_snapshot.json`: snapshot of `alea/game/biobuzz.py`, checked by `tests/test_game_constants.py`.

Later: dsim traces, sample .rlog.

**Roadmap phase:** 1
