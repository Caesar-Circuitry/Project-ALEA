# tests/hifi_traces/record_3d

Recorder for the dsim 3D hive traces in `tests/hifi_traces/sim3d/`. `record_hive3d.mts` runs
dsim's real `src/games/biobuzz/sim3d/hive3d.ts`, `contacts3d.ts` and the Rapier3d engine layer
(through `step3d`) at the pinned commit and writes the JSON fixtures. `fetch_dsim.py` makes the
pinned clone. dsim is untrusted: run both only in the `alea-dev` container, keep the clone out of
the repo, never use it as cwd. Exact commands are in `../README.md` (section "3D hive traces").

**Roadmap phase:** 1b (hifi port, traces).
