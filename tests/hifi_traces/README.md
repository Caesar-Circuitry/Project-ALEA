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
| `deflect.json` | `hiveDeflect` (hive.ts, pure, no 3D engine): each face, open top and mouth, pivot plane, inside/outside |

In the timer files `timer_steps` rows drop `hive.contents` (`hiveTimerStep` returns it
untouched; the recorder asserts that); `step_steps` rows keep it. Launches into the tray are
offered by the recorder and added only if dsim's `hiveAccepts` says yes (that add rule is the
recorder's, documented in `inputs.launch_rule`). The `kindOf` callback and the RNGs belong to the
caller in dsim, so the recorder defines them.

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
