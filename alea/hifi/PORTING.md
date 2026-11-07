# dsim port inventory

Pinned dsim commit: `62d2446e2ebdf416548fa1641847289bf47cdf36` (default branch `main`, committed
2026-11-02; github.com/genius0412/dsim, PolyForm Noncommercial 1.0.0, copy in `LICENSE-dsim`).
Plan and licensing: `docs/decisions/0005-hifi-dsim-port.md`. Ported so far (phase 1b): the pure 2D hive logic and the pure arithmetic of the 3D hive (both
below). Not ported: the 3D engine (the swing), contacts, nectar box, and any use of the port by
the study kernel; `check_fidelity('hifi')` still raises.

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

Deliberate non-matches with dsim: none in the values the fixtures cover. `Math.round` and
`Math.sign` are reimplemented with JavaScript semantics (Python's `round` is banker's); launch
times in the timer replay use the same JS rounding. `dsin`/`dcos` return NaN for NaN or
infinite input, as dsim does, instead of raising. Remaining small differences: `dsin(-0.0)`
returns -0.0 where a +0 may appear in JS (equal under `==`), and Python ints vs JS numbers (for
example the integer `tips`) are not distinguished from floats beyond what the tests compare. In `hive_step`, as in dsim, `contents` is the caller's;
timer traces never clear it (see `tests/hifi_traces/README.md`).

Not yet decided: nothing from `alea/game/` is used by this code. The differences listed below
are still the user's to resolve before the port feeds any study.


## Ported: the pure part of the 3D hive (branch feature/1b-3d-port)

| Python | From dsim | Notes |
|---|---|---|
| `hive3d.py` | `sim3d/hive3d.ts`: `insideCell`, `hiveContentsTorque`, `hiveRestoringTorque`, `hiveHoldTorque`, `stopAngle`, `tippingFromAngle`, `hiveDynamicTick` (`hive3dJointTick`), the decision of `hiveDetentHold`; `tilt.ts`: `hiveTiltAngle`, `hiveTrayRefTheta`; `bodies.ts`: `hivePivotX`, `hiveCellLocalBox` (CAD path), `hiveTrayComW`, `hiveTrayMassProps`, `elementMass` | immutable `Hive3dState`; the tray angle and angular velocity are caller-supplied; `detent_decision` returns the Rapier writes (creep, wake, pin pose) as a `DetentDecision` instead of doing them |
| `hive3d_constants.py` | the `BB3_*` block of `config.ts`, `GRAVITY`, `SIM_DT`, and the CAD cell boxes from `fieldColliders.gen.ts:3` | dsim's numbers, not alea/game's; each with its dsim file:line; names already in `hive_constants.py` are re-exported |
| `math3.py` | `sim3d/math3.ts`: `rotate2`, `tiltQuatX` | through `dsin` / `dcos` |

There is no solver, integrator, joint or contact code in any of these. The port reads the tray
angle the way dsim reads it (`hive.angle`, or the engine body when absent) but cannot produce it.

Validation (`tests/test_hifi_hive3d_*.py`, helpers in `tests/hifi_replay3d.py`), with dsim's
own recorded outputs from `tests/hifi_traces/sim3d/`:

| Fixture | What is replayed | Measured max deviation |
|---|---|---|
| `constants3d.json` | every config constant, mass props, centre of mass, pivot x, cell boxes, element masses | exactly equal |
| `statics3d.json` | 290 contents-torque rows, 58 restoring/hold rows, 5184 `insideCell` points | 0.0 (bit-identical); all inside flags equal |
| `joint_tick.json` | all 19 single-call cases: hive record out, nectar due, events, spill tags | 0.0; events and spill maps equal |
| `loads_*.json` (11 rows) | `hive_dynamic_tick` run per tick over the RECORDED angle and angular velocity: tipping countdown, released, tips, up side, nectar due, SPILLS and TIP event ticks | 0.0 over all ticks |
| `loads_*.json` | `detent_decision` on the recorded pre-step tray state vs the recorded `tray_held` | all ticks equal (one tick skipped, see below) |

Tolerance: none. Every float is demanded equal, because every recorded number is a pure
function of its inputs and the port keeps dsim's operation order and its `dsin` / `dcos`. If a
later change makes a replay differ in the last bit, say so and set a stated tolerance; do not
loosen silently.

What the `loads_*.json` replay is, and is not. The angle and angular velocity of every tick come
FROM THE RECORDING (dsim's world JSON, rounded to 4 decimals, which is what `hiveDynamicTick`
reads), so this proves that the state machine turns a given swing into dsim's bookkeeping. It
does not prove the swing. Also fed from the recording: `contents` (rebuilt from `contents_n`) and
the spill tag count (`spill_n`); spill tagging itself is covered by `joint_tick.json` only, where
the staged element positions are rebuilt by a test-side copy of the recorder's `fillCell`. The
detent decision check rebuilds contents composition from the staged load (nectar first); the one
tick where the tray sits at a stop with a partly emptied cell is skipped because the kinds of
the remaining ids are not recorded. `hiveDetentHold` is not called alone by any fixture, and the
creep and wake outputs have only hand-derived unit tests (read off `hive3d.ts:242-330`).

### Where the port cannot match dsim's engine

These are the places where the pure port stops being dsim. None is hidden; none is fixable
without writing a rigid-body engine, which this branch does not do.

1. **The swing trajectory.** Tray angle and angular velocity per tick are the result of a Rapier
   revolute-joint solve: angular damping `BB3_HIVE_DAMPING` 4.466, the joint's limits, the
   contents pressing on the tray, 8 solver iterations, and a fixed dt that is 1/60 s in the
   recording but unverified for the engine's own internal substeps. The port takes the angle as
   an input. Anything that needs the angle to EVOLVE (a study, a what-if load, a robot leaning on
   the tray) needs an engine.
2. **Contacts and G409** (`hiveContactPass`, `contacts3d.ts`, `contactPairsWith`, the Rapier
   collision groups): not ported. `g409_contacts.json` is recorded but not replayed.
3. **Sleeping and waking.** Dsim pins the tray, Rapier then sleeps it, and the breakaway has to
   wake the body and the elements (`hive3d.ts:304-321`). The port returns `wake` as a decision;
   what sleeping does to the solve is the engine's.
4. **The detent pin as a physical act.** `detent_decision` says "pin the pose and zero the
   velocity"; whether the body then stays exactly there (and what `trayTilt` reads, which needs
   dsim's `datan2`, not ported) is the engine.
5. **Cross-machine non-determinism.** Dsim's own `hive-calibrate.ts` header says the sim3d
   result is not bit-reproducible across machines (seen on a Windows run), and the recording was
   checked for determinism on one machine only. The pure functions here are deterministic, but a
   future replay against traces from another machine would need tolerances on the engine-derived
   inputs.
6. **Calibration constants fit to that engine.** `BB3_HIVE_DETENT` 3041, `BB3_HIVE_DAMPING`
   4.466 and `BB3_HIVE_BALLAST` 6 were fitted by dsim's `scripts/hive-calibrate.ts` against its
   own Rapier setup. Used in another engine they have no guarantee. The torque functions use
   them exactly as dsim does.
7. **Not ported on purpose:** the kinematic tray path (`hive3dTick`, off by default), the
   algebraic fallback of `hiveCellLocalBox` (not reached with `BB3_FIELD_COLLIDERS` true), and
   the calibration overrides (`__setDetentForCalibration`, the ballast override).

8. **Shared spill map and event order.** In dsim `bb.spill` is one object shared by the red
   then blue loop of `hiveDynamicTick`, and events are pushed red first. `hive_dynamic_tick` is
   per alliance and copies the map, so the caller must feed red's returned `spill` into blue's
   call and keep the red-then-blue event order.
9. **Readback rounding contract.** `hiveDynamicTick` reads `hive.angle` / `angVel` as rounded to
   4 decimals by dsim's readback, while the detent reads the unrounded `trayTilt(body)`. The
   caller must supply each in that form; the port does not round. The replays do so (rounded
   columns for the tick, full-precision body columns for the detent).
10. **The `useHiveDynamic()` gate** (`hive3d.ts:487`, which makes `hive3dJointTick` return at
   once on the kinematic tray) is not modelled. Harmless while `BB3_HIVE_DYNAMIC` is true, which
   `tests/test_hifi_hive3d_statics.py` asserts.
11. **NaN.** `min` / `max` in `tippingFromAngle` and `hiveTiltAngle` follow JavaScript (NaN in,
   NaN out). Other NaN paths (for example `Math.sign(NaN)` comparisons) are not specially
   tested.

Differences from `alea/game/` listed below still apply to the 3D numbers (the CAD cell boxes
here are dsim's measurement of its own CAD export). Nothing from `alea/game/` is used.

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

The CAD and guide evidence below was added later; the user's rule is to use whatever matches real life, and where evidence cannot settle a number it stays open.

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
  `hive.ts` itself has the hive miss bounce, `BB_HIVE_MISS_REST` 0.3 (`hive.ts:471`) and
  `BB_HIVE_MISS_TANGENT` 0.5 (`hive.ts:472`); ported as dsim's values, not compared with ALEA's
  0.45, not decided. A quick search of `hive3d.ts` and `bodies.ts` found no hive-specific value, but it was not
  exhaustive. Each of these changes scoring, so each needs an explicit answer before it is used.

## Evidence from the field CAD and the field guides (2026-11-07)

Source: field CAD, an Onshape STEP export of the BIOBUZZ field, provided by the user. It is not
committed (35 MB). Origin is at the tile centre, y up, in the match-start state with the red
audience cell and blue scoring cell raised. Measured with OpenCascade. Also used: three FIRST
guides: the Field Check list (`field-check`), the Initial Field Element Assembly Guide, and the
2027 Event Field Setup Guide v1.0. All lengths are in inches.

1. **Frame.** CAD tiles run ±70.585 in. The hive pivot is at z = 0. The pair is centred on
   x = 0 within about 0.01 in (bracket centres +12.7585 and -12.7415; stepped spacer at
   x = -12.743). CAD puts the hive at field centre, so it does not support ALEA's 0.10 in
   offset (`HIVE_Y_IN` 70.75 vs `FIELD_SIZE_IN` / 2 = 70.65). The CAD cannot show where ALEA's
   frame origin comes from. Recommendation: derive the dsim-to-ALEA conversion from the field
   centre, not from 70.75. Confirm ALEA's origin before wiring.
2. **Pivot.** Spacer centred at y = 43.95 in, z = 0. Matches both dsim and ALEA (43.95 in).
3. **Cell depth.** In the cell frame (rotated 30 degrees about the pivot axis) the skins run
   9.644 to 21.394 in along the bar, which is 11.75 in. That is exactly dsim `CELL_NEAR`,
   `CELL_FAR` and `CELL_D`. The outer ribs and back skin run about 9.42 to 21.456 in. ALEA has
   9.38 to 21.46. Both are right, because they measure different things (skin span vs outer
   span). Recommendation, not a decision: a physics model should use the skin span, because the
   ball's travel space is the skin span. The outer span is the frame envelope.
4. **Cell width.** Ribs are 21.000 in. The full red cell bounding box, including cable ties, is
   21.061 in (ALEA `CELL_WIDTH_IN` 21.06). The blue cell's is 21.191 in; the cause is not
   investigated. Skins: bottom 20.198 in, top 19.832 in, back 20.937 in. dsim's `CELL_W` 20.141
   matches no outer part. It is probably an inner width, but that was not measured. Open.
5. **Cell height.** The rib profile is 16.083 in tall (ALEA `CELL_H` 15.79 in, dsim 13.997 in).
   What each number is defined as is unknown. Open. The cell centre offset (dsim 13.4398 in vs
   ALEA 5.18 in) is not resolved. It depends on the definitions in item 5.
6. **Accept opening.** Field Check item 1.13 says the bottom of an upright cell opening is
   53.5 ± 0.50 in above the tiles. dsim's 53.375 in is inside that range. The opening height
   is not measured: dsim's opening runs 53.375 to 65.497 in (12.122 in), and the 14 in figure
   is not in `alea/game/`. Open.
7. **Up-side staging.** The Event Field Setup Guide 11.1 says the red hive's audience-side cell
   and the blue hive's scoring-side cell start raised, with 3 nectar in each raised cell. This
   matches ALEA `HIVE_UP` = (-1, 1) in meaning. dsim's red-south / blue-north orientation was
   not checked against this.
8. **Tip table.** The guides say a hive must tip with 8 pollen and 0 nectar, and with 3 pollen
   and 3 nectar (Event Field Setup Guide section 12). The Field Check says 3 nectar + 2 pollen
   does not tip, 3 nectar + 3 pollen tips, 7 pollen does not tip, and 8 pollen tips (the "+1"
   steps read as 3 and 8 pollen). dsim's `BB_TIP_POLLEN` = `[8, 7, 6, 3, 1, 0]` gives those
   thresholds when read as nectar 0 -> 8 and nectar 3 -> 3. Only the table was compared, by
   reading. The ported tip logic was not run against these official checks. Suggested
   follow-up: add such a test.
9. **Restitution.** Not in the CAD or the guides. It needs a physical drop test. Stays open.

Status:

- Settled by evidence: pivot (item 2), depth conventions (item 3), up-side staging (item 7),
  tip table thresholds (item 8), opening bottom within tolerance (item 6).
- Open: frame origin (item 1), width definition (item 4), height and centre offset (item 5),
  opening height (item 6), restitution (item 9).

Nothing here changes any constant. `alea/game/` is untouched.

## Validation

Traces must be recorded from dsim at the pinned commit and stored as new fixtures; nothing in
`tests/golden/` is regenerated. dsim ships `scripts/hive-calibrate.ts` and
`scripts/smoke-biobuzz/hive3d.ts`, which are the likely sources. The traces are recorded (`tests/hifi_traces/`, with the recorder and how to rerun it in
`tests/hifi_traces/README.md`); rerunning needs Node and runs only in the `alea-dev` container.
