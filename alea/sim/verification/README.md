# alea.sim.verification

Scripts and Java dumps used to verify ALEA against the Java Code Sim. They need the Java builds and run on the team's machine, not in CI.

- `verify_physics.py`: kernel vs Java sim shot by shot (needs `ShotDump` build; set `ALEA_JAVA_BB` or put `bb/` next to the repo). `--save` writes `results/golden_shots_new.npy`; it never touches `tests/golden/`.
- `verify_study.py`: study kernel vs the real robot code (`rtout/AimDump`) and Java sim (set `ALEA_JAVA_ROOT`, a folder holding `rtout/` and `bb/`).
- `compare.py` with `java_ref.txt`: LUT sweep vs the Java `LutSweep` tool.
- `AimDump.java`, `ShotDump.java`: the Java dump tools.

**Roadmap phase:** 1
