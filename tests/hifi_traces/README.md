# tests/hifi_traces

Traces recorded from dsim's pure hive logic (`src/games/biobuzz/hive.ts`) at the pinned commit
`62d2446e2ebdf416548fa1641847289bf47cdf36` (same hash as `alea/hifi/DSIM_VERSION`). They are the
reference the `alea/hifi` port will be replayed against (next branch). Nothing here is replayed
yet; `tests/test_hifi_traces_schema.py` only checks structure and the pin. Every number came
from running dsim's own code (`hive.ts`, `config.ts`), not from retyping. Change the pin, and
these files must be re-recorded.

Each file has the top-level fields `dsim_commit`, `source_file`, `scenario`, `generator`
(script and command), `inputs`, plus the recorded outputs. Floats are full precision
(JavaScript shortest round-trip). A hive written without a `swingRate` key means dsim's
`undefined`. Units are dsim's: inches, seconds, degrees, field-centred frame (not ALEA's frame).

| File | Scenario |
|---|---|
| `capture.json` | `hiveCellPos`, `hivePivot`, `hiveApproachSign`, `hiveTakingSide`, `hiveAccepts`: a footprint grid around the accept box edges, opening heights and `BB_HIVE_ACCEPT_MARGIN` (default, 0, 5), inbound/outbound/ascending/level velocities; both alliances, both up sides, settled / pre-release / post-release |
| `load.json` | `hiveLoad`, `hiveWillTip`, `hiveSurplus`, `hiveSwingRate` over pollen 0..14 x nectar 0..9 (past the end of the tip table), red and blue nectar, order variants |
| `sides.json` | `otherSide`, pivot, approach sign, taking side and taking-cell position for both alliances and sides |
| `timer_dt60_threshold.json` | `hiveTimerStep` and `hiveStep` at dt = 1/60 s from swing start through release (2 s left), settle, loads exactly at threshold, both sides |
| `timer_dt60_surplus.json` | same at dt = 1/60 s for surplus loads (rate, rate cap), an idle below-threshold tray, elements fired into a swinging tray |
| `timer_coarse.json` | same at dt = 0.25, 1, 3 and 5 s (3 and 5 s exercise the settle fallback spill) |
| `spill.json` | `spillPoses` with a mulberry32 RNG (seed and source in `inputs.rng`) and a cycled-values RNG; counts 0, 1, 3, 8, 14; both alliances; mid-swing and settled; `draws` = RNG calls (6 per pose) |
| `constants.json` | the config.ts hive/tip/spill block (`BB_TIP_POLLEN` = [8,7,6,3,1,0], `BB_TIP_*`, `BB_SPILL_*`, `BB_HIVE_*`, `BB3_HIVE_*`, `BB_CELL_OPEN`, radii), hive.ts' own constants, the `HIVE` block of `fieldDims.gen.ts`, tip-table lookup for nectar 0..12 |
| `trig.json` | dsim's own `dsin`/`dcos` (`src/math.ts`, polynomial approximations, ~1e-11 error, not `Math.sin/cos`) sampled at whole degrees 0..360, negative angles, the fan/kick angles `spillPoses` feeds them for the `spill.json` stream, and the fan extremes. The Python port must port them or tolerance-check against these |
| `deflect.json` | `hiveDeflect` (hive.ts, pure, no 3D engine): each face, open top and mouth, pivot plane, inside/outside |

Timer-file caveats:

- `hiveTimerStep` never clears `contents` (the caller does) and the recorder keeps the tray full, so after the settle a timer run starts a second swing: `tips` can reach 2 at dt 3 and 5 while `hiveStep` rows show 1 (it empties the tray at the release). Compare the two only up to the first `tipped`.
- Launch times are in seconds (`t_s`) and applied at step `round(t_s/dt)`, so they scale with dt. Applied launches are in `launches_timer` / `launches_step`; any not reached are in `launches_not_reached_*`.
- The recorder's add rule always aims at the taking-cell centre, inbound and descending, so timer traces never contain a refused launch. Refusal is covered only by `capture.json`.
- `BB_SPILL_*` constants are defined in `hive.ts`, not `config.ts` (the config filter matches none of them); they are in `constants.json` under `hive_ts`.

In the timer files `timer_steps` rows drop `hive.contents` (`hiveTimerStep` returns it
untouched; the recorder asserts that); `step_steps` rows keep it. Launches into the tray are
offered by the recorder and added only if dsim's `hiveAccepts` says yes (that add rule is the
recorder's, documented in `inputs.launch_rule`). The `kindOf` callback and the RNGs belong to the
caller in dsim, so the recorder defines them.

## 3D hive traces (`sim3d/`)

Recorded from dsim's REAL 3D code: `src/games/biobuzz/sim3d/hive3d.ts`, `contacts3d.ts` and the
deterministic Rapier3d engine layer under them, driven through dsim's own `step3d` at dt = 1/60 s.
It does run under tsx with `--ignore-scripts`: needs `@dimforge/rapier3d-deterministic-compat`
0.20.0 (wasm, "compat" build, `await init()`; no native or postinstall step) and
`@dimforge/rapier2d-compat` 0.19.3 (`initPhysics()` loads the 2D engine too). Recorder:
`record_3d/record_hive3d.mts`. Same top-level fields as above plus `source_files`; units are
dsim's (inches, seconds, radians, field-centred frame). The sim3d result is NOT bit-reproducible
across machines (dsim's own `hive-calibrate.ts` header says so for a Windows run), so a port
replay needs tolerances; this recording was checked for determinism on one machine only.

| File | Scenario |
|---|---|
| `constants3d.json` | the config.ts constants the 3D hive reads (`BB3_HIVE_*`, seat depth, element mass, tilt), GRAVITY, SIM_DT, tray mass props, centre-of-mass w, pivot x, cell boxes |
| `statics3d.json` | pure functions: `hiveContentsTorque` (staged loads x tilt grid, both alliances), `hiveRestoringTorque`, `hiveHoldTorque`, `insideCell` (grid with min depth 0 and the seat depth) |
| `loads_no_tip_blue.json` | `step3d` per-tick trace, blue hive: empty rest (240 ticks), 7P, 2P+3N, 0P+4N for 480 ticks; the detent holds, angle stays at the stop |
| `loads_tip_blue.json` | same for 8P, 3P+3N, 1P+4N, 0P+5N (guide packing) and 8P (line2 packing), 540 ticks: breakaway, swing, release (SPILLS event), TIP event |
| `loads_red.json` | red hive (up cell south, opposite sign): 8P tips, 7P holds, 540 ticks |
| `joint_tick.json` | `hive3dJointTick` (hiveDynamicTick) called once on staged hive states: near stop, just off the stop (spill tagging), mid swing, level, far stop spent, far stop moving, failed swing reset, empty cell, angle undefined |
| `g409_contacts.json` | `hiveContactPass` through `step3d`: 8P tip with the robot parked away (no G409) vs under the down cell (G409 lines), 600 ticks |

Load-trace row fields: `pollen`, `nectar`, `alliance`, `packing`, `seed`, `ticks`, `element_ids`,
`summary` (tick of first `tipping>0`, first `released`, first tip; final tips, up side, tray angle,
contents count, elements below z = 2 in, final load), `events` as `[tick, text]`, and `columns`
with one entry per tick: `tray_theta_rad` / `tray_omega_rad_s` (Rapier body, full precision),
`hive_angle_rad` / `hive_ang_vel_rad_s` (dsim's world JSON, rounded to 4 decimals by dsim),
`tipping_s`, `released` (0/1), `tips`, `up`, `contents_n` (derived membership), `spill_n` (spill tag
count for that alliance), `tray_held` (detent pin on, 0/1), `nectar_due`. G409 rows: `spill_n`,
`g409_lines_total`, `lowest_tagged_z_in` (-1 when none tagged) per tick. A hive written without
`angle` / `angVel` means `undefined`. Worlds are the stock `createBiobuzzWorld('free', seed, ..., '3d')`
with `world.balls` cleared and the load staged in the up cell by the recorder (staging rule in
`statics3d.json` `inputs`); `contents` in `joint_tick.json` is whatever the fresh world carried
(ids 44..46), not the staged elements.

Not covered: `hiveDetentHold` / `hiveContactPass` are only reached through `step3d` (no isolated
call), launches into a swinging tray, robot contact with the tray, `__setDetentForCalibration`,
the kinematic tray path (`hive3dTick` returns at once when the dynamic tray is on, as it is by
default), `engineImpl` internals beyond the tray body, and anything past 600 ticks.

Rerun (versions: node v22.17.0, npm 10.9.2, tsx 4.23.15; `<wt>` = absolute worktree path):

```
just dev python3 <wt>/tests/hifi_traces/record_3d/fetch_dsim.py        # prints e.g. /tmp/dsim3d-XXXX/src, verifies HEAD == pin
just dev npm install --ignore-scripts --no-audit --no-fund --prefix /tmp/dsim3d-XXXX @dimforge/rapier3d-deterministic-compat@0.20.0 @dimforge/rapier2d-compat@0.19.3 tsx@4.23.15
just dev cp <wt>/tests/hifi_traces/record_3d/record_hive3d.mts /tmp/dsim3d-XXXX/record_hive3d.mts
just dev /tmp/dsim3d-XXXX/node_modules/.bin/tsx /tmp/dsim3d-XXXX/record_hive3d.mts /tmp/dsim3d-XXXX/src <wt>/tests/hifi_traces/sim3d
```

`node_modules` sits in the PARENT of the clone so Node's resolution finds Rapier from dsim's files
without installing into the clone. Determinism check: the recorder was run twice, the second time
into a scratch directory, and `diff -r` of the two output trees was empty.

## Licence notice

These fixtures embed dsim constants and outputs. They are derived from dsim by genius0412
(github.com/genius0412/dsim) at the pinned commit and are under PolyForm Noncommercial 1.0.0;
see `alea/hifi/LICENSE-dsim`. Do not redistribute them outside those terms.

## dsim is untrusted

dsim is third-party code under PolyForm Noncommercial. It was checked out inside the `alea-dev`
container at `/tmp/dsim-src` (no `node_modules`); it was only read and imported there. Never run
anything with that directory as cwd, never write into it, install nothing with lifecycle scripts
(`--ignore-scripts`), and run all dsim code through `just dev`. The recorder lives in `record/`,
not in the dsim tree.

## Rerun

Versions used: node v22.17.0 (`just dev node --version`), npm 10.9.2, tsx 4.23.15.

```
just dev bash -c 'mkdir -p /tmp/dsim-rec && npm install --ignore-scripts --prefix /tmp/dsim-rec tsx@4.23.15'
just dev bash -c 'cp <worktree>/tests/hifi_traces/record/record_hive.mjs /tmp/dsim-rec/ && cd /tmp/dsim-rec && ./node_modules/.bin/tsx record_hive.mjs /tmp/dsim-src <worktree>/tests/hifi_traces'
```

`<worktree>` is the absolute repo path. The recorder reads the dsim commit from the checkout's
metadata files and writes it into every fixture; it must equal `alea/hifi/DSIM_VERSION`.

**Roadmap phase:** 1b (hifi port).
