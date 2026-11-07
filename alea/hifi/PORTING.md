# dsim port inventory

Pinned dsim commit: `62d2446e2ebdf416548fa1641847289bf47cdf36` (default branch `main`, committed
2026-11-02; github.com/genius0412/dsim, PolyForm Noncommercial 1.0.0, copy in `LICENSE-dsim`).
Plan and licensing: `docs/decisions/0005-hifi-dsim-port.md`. Ported so far (phase 1b): the pure hive logic only (below). Not ported: the 3D hive, contacts,
nectar box, and any use of the port by the study kernel; `check_fidelity('hifi')` still raises.

## Ported (branch feature/1b-hive-logic)

| Python | From dsim | Notes |
|---|---|---|
| `hive.py` | all of `src/games/biobuzz/hive.ts`: `otherSide`, `hivePivot`, `hiveCellPos`, `hiveApproachSign`, `hiveTakingSide`, `hiveAccepts`, `hiveLoad`, `hiveWillTip`, `hiveSurplus`, `hiveSwingRate`, `hiveTimerStep`, `hiveStep`, `spillPoses`, `hiveDeflect` and the types | snake_case functions; immutable dataclasses; `swingRate` is `swing_rate` (None = undefined); `contents` is a tuple; `rng` and `kind_of` are caller-supplied callables |
| `hive_constants.py` | the config.ts hive block, the fieldDims.gen.ts `HIVE` block and hive.ts' own constants | dsim's numbers, NOT alea/game's; each labelled with its dsim file:line |
| `hive_math.py` | `dsin`, `dcos` from `src/math.ts` | ported because they are short and exact; `math.sin/cos` differ from them by up to 6.0e-12 |

Validation: every fixture in `tests/hifi_traces/` is replayed by `tests/test_hifi_hive_*.py`
(helpers in `tests/hifi_replay.py`). Measured max deviation is exactly 0 (bit-identical) for
all floats in capture, load, sides, the three timer files, spill, deflect and trig, so the
tests demand equality. The spill replay also checks the RNG draw count (6 per pose) with a
test-side mulberry32 and a cycled-values RNG.

Deliberate non-matches with dsim: none in behaviour. `Math.round` and `Math.sign` are
reimplemented with JavaScript semantics (Python's `round` is banker's). Launch times in the
timer replay use the same JS rounding. In `hive_step`, as in dsim, `contents` is the caller's;
timer traces never clear it (see `tests/hifi_traces/README.md`).

Not yet decided: nothing from `alea/game/` is used by this code. The differences listed below
are still the user's to resolve before the port feeds any study.


## What to port, in order

| dsim file (size) | What it holds | Port difficulty |
|---|---|---|
| `src/games/biobuzz/hive.ts` (29 KB) | Pure hive logic: capture into the up CELL, load against the damper, the TIP (`BB_TIP_SWING_S` = 4.0 s), the release and the spill (`spillPoses`, caller supplies the RNG). Takes a state, returns a new one; reads no world. | Low: plain functions. Start here. |
| `src/games/biobuzz/config.ts` (4,406 lines; hive block only) | `BB_TIP_POLLEN` = `[8, 7, 6, 3, 1, 0]` (the tip table), hive geometry (`BB_HIVE_*`, `BB3_HIVE_*`), `BB_POLLEN_R` = 1.4, `BB_NECTAR_R` = 1.8. Geometry comes from a generated CAD file, `fieldDims.gen.ts`. | Low, but see the frame differences below. |
| `src/games/biobuzz/nectarBox.ts` (6.8 KB) | Human-player nectar box footprint. | Only if a study needs it. |
| `src/games/biobuzz/sim3d/hive3d.ts` (28 KB) | The hive as a rigid body on a pivot: contents torque, restoring torque, detent hold, joint tick. | High: built on dsim's 3D engine layer (`Engine3d`, `Rapier3d`, bodies, joints). |
| `src/games/biobuzz/sim3d/contacts3d.ts` (7.5 KB) | Hive contact pass (G409: a robot catching elements spilling from a tipped hive). | High: same engine layer. |

The split matters. The pure logic in `hive.ts` can be ported and validated on its own. Ball and
hive contacts in 3D mean reimplementing what dsim's rigid-body engine does, in Warp, and checking
it against recorded dsim traces. Decide whether the first release is 2D logic only.

## Differences to resolve with the user (step 3 of decision 0005)

Not decided here; `alea/game/` stays the source of field numbers. Checked against dsim at the
pinned commit and against `alea/game/biobuzz.py`.

- **Frame.** dsim is centred on the field: hive pivots at x = ±12.750 in, red at -x
  (`config.ts:245-251`). ALEA uses the Pedro/sim frame (`FIELD_SIZE_IN` = 141.3, `HIVE_X_IN` =
  58.0 and 83.5, `HIVE_Y_IN` = 70.75). The hive pair is 25.5 in apart in both, but ALEA's midpoint
  (x = 70.75) is not the field centre (70.65), and `HIVE_Y_IN` is 70.75 against 70.65. So the
  conversion is not a plain half-field shift; there is a 0.10 in offset to resolve, and the
  conversion needs its own test.
- **Same value:** pollen radius 1.4 in (`BB_POLLEN_R`, `config.ts:667`; `POLLEN_RADIUS_IN`,
  `biobuzz.py:17`). Hive tilt 30 degrees (`TILT_DEG`, `fieldDims.gen.ts:151`;
  `HIVE_REST_ANGLE_RAD`, `biobuzz.py:37`). Pivot height 43.95 in (`HIVE.PIVOT_Z`,
  `fieldDims.gen.ts:150`; `HIVE_PIVOT_HEIGHT_IN`, `biobuzz.py:22`).
- **Cell size: unresolved.** dsim: `CELL_W` 20.141 in, "across, along x, perpendicular to the
  tilt axis" (`config.ts:330-334`), and `CELL_D` 11.75 in, the true length along the bar, from
  `CELL_NEAR` 9.644 to `CELL_FAR` 21.394. ALEA: `CELL_WIDTH_IN` 21.06 in and
  `CELL_BOX_ALONG_MIN_IN` / `MAX_IN` 9.38 to 21.46 (a span of 12.08 in). Nothing in `alea/game/`
  says ALEA's 21.06 is measured the way dsim measures its width, so do not assume the 20.141 vs
  21.06 gap is a real difference or an error until that is established.
- **Restitution: not matched.** ALEA's 0.45 is the ball off the hive and its frame. dsim has
  `BB_POLLEN_WALL_REST` 0.35 (`config.ts:710`, pollen against walls, which dsim's own comment calls
  an approximation) and `BB3_ELEMENT_RESTITUTION` 0.55 (`config.ts:3445`, elements on the ground).
  A quick search of `hive3d.ts` and `bodies.ts` found no hive-specific value, but it was not
  exhaustive. Each of these changes scoring, so each needs an explicit answer before it is used.

## Validation

Traces must be recorded from dsim at the pinned commit and stored as new fixtures; nothing in
`tests/golden/` is regenerated. dsim ships `scripts/hive-calibrate.ts` and
`scripts/smoke-biobuzz/hive3d.ts`, which are the likely sources. Running dsim needs Node and its
dependencies; not set up here.
