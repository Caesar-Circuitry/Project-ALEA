# 0005: High-fidelity physics from dsim

**Status:** accepted, 2026-11-07. State of phase 1b: see the section at the end (2026-11-08).

## Context

The fast simulator (`alea/sim`, NVIDIA Warp) holds the hive at rest (30 degree tilt, no swing)
and ignores ball-to-ball contact and robot collisions (knowledge base, "what the model leaves
out"). That is right for the 72-condition shot study, but it cannot answer questions about hive
tipping (the official tip table `tipPollenByNectar`) or how balls behave once they pile up in a
cell. dsim (github.com/genius0412/dsim, community driver-practice tool) models both. dsim is
licensed PolyForm Noncommercial 1.0.0, which differs from the rest of ALEA.

## Decision

- High fidelity is an option, never a replacement: `fidelity: fast | hifi`, default `fast`, in
  the study YAML or `--fidelity` on `alea.sim.run_study`. The check lives in
  `alea.hifi.check_fidelity`; `hifi` is accepted and runs the hive-session study
  (`alea/hifi/hifi_study.py`, `hive_session.py`). `alea/sim/shotsim.py` and `study.py` stay frozen and keep matching the Java Code Sim.
- The port goes into `alea/hifi/` only, in phase 1b, by this plan:
  1. Pin the dsim commit in `alea/hifi/DSIM_VERSION` (pinned 2026-11-07 to `62d2446e`, the
     tip of dsim `main`; see `alea/hifi/PORTING.md`). Every ported file starts with "Ported from
     dsim by genius0412" and that hash.
  2. Port hive tipping (pivot, tilt dynamics, tip table) first, then ball-to-ball and
     ball-to-hive contacts.
  3. Take field geometry only from `alea/game/`. Where dsim's numbers differ, list the
     differences for the user instead of choosing one.
  4. Validate against dsim traces recorded at the pinned commit, as new fixtures; `tests/golden/`
     is never regenerated. The fast path must still pass `just selftest` (99.9 percent).
  5. Each step needs a `physics-reviewer` pass and human sign-off on the PR. This is
     orchestrator-sized work and needs the user's approval before it starts.
- Licensing: `alea/hifi/` keeps dsim's license text and stays separate from the rest of the code,
  so it can be left out of any non-noncommercial distribution.

## Consequences

- The fast path is unchanged (`shotsim.py`, `study.py` frozen; `just selftest` passes). `hifi` calls
  `Study.run` as is, then feeds each condition's score rate into seeded hive sessions that run
  the ported capture, tip table, 4 s swing timer, release and spill. Ball contacts, the 3D hive engine
  and robot collisions are not modelled; the session docstring lists exactly what is and is not.
- `hifi` results are labelled and kept apart: `results/study-hifi`, `cond_hifi_XXX.npz` with a
  `fidelity` field, `summary_hifi.csv`, `hifi_*.png` titled `[hifi]`. `run_study` refuses to
  write hifi into a directory holding fast results, and the reverse.
- Open parameters, not chosen: the session size and shot interval, `retarget_after_tip`, and
  restitution (only the study's per-condition `bounce` axis; dsim's hive miss bounce is unused).
  Cell width, height, opening height and the frame origin stay open (PORTING.md). The dsim to
  ALEA conversion shifts by `FIELD_SIZE_IN / 2` (70.65), leaving a 0.10 in difference from
  `HIVE_X_IN` / `HIVE_Y_IN`, tested in `tests/test_hifi_frame.py`.
- The official tip thresholds are tested against the ported logic (`tests/test_hifi_tip_table.py`).
- Results from `hifi` must never be mixed with `fast` results in one study without labelling.
- Noncommercial terms limit how `alea/hifi/` can be redistributed; check before publishing.
- The DSIM_VERSION pin is in place. Change it deliberately: a new commit means new traces.
- dsim's 3D hive and contacts run on its rigid-body engine layer, so they are much harder to
  port than its pure hive logic; `alea/hifi/PORTING.md` splits the two.

## State of phase 1b (2026-11-08)

- Ported: pin, the pure 2D hive logic (`hive.py`), the dsim traces (2D and 3D), and the pure
  arithmetic of the 3D hive (`hive3d.py`, `hive3d_constants.py`, `math3.py`: torques,
  `insideCell`, swing bookkeeping, detent decision), all replayed bit-for-bit. In the 3D replay
  the tray angle comes from the recording.
- Wired (step A): `fidelity: hifi` runs. The fast shot kernel is unchanged, followed by hive
  sessions on the 2D logic (`hive_session.py`, `hifi_study.py`, `frame.py`). The 3D arithmetic is
  not used by the study yet.
- Not yet ported: contents membership (`sim3d/derive.ts` `insideCell` with seat depth; pure
  geometry, the loads replay feeds `contents_n` from the recording), nectar box.
- Engine outputs used as inputs: tray angle, angular velocity and element positions.
- Not ported, and not possible without an engine: the swing itself (Rapier revolute body,
  damping 4.466, limits, solver iterations), contacts and G409, sleeping. The list of mismatches
  with dsim's engine is in `alea/hifi/PORTING.md`.
- Open for the user: whether to build a Warp or NumPy rigid-body layer for the swing and
  contacts (large, and dsim's calibration constants are fitted to Rapier), or to stop at the
  table-driven tip; the open geometry and restitution items (PORTING.md); the session
  placeholders (session size, `shot_interval_s`, `retarget_after_tip`). Nothing in `alea/game/`
  has been changed or chosen.
