# 0005: High-fidelity physics from dsim

**Status:** accepted, 2026-11-07

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
  `alea.hifi.check_fidelity`; `hifi` raises `NotImplementedError` pointing here until the port
  lands. `alea/sim/shotsim.py` and `study.py` stay frozen and keep matching the Java Code Sim.
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

- Nothing in the fast path changes now; the stub only adds the option and the error message.
- Results from `hifi` must never be mixed with `fast` results in one study without labelling.
- Noncommercial terms limit how `alea/hifi/` can be redistributed; check before publishing.
- The DSIM_VERSION pin is in place. Change it deliberately: a new commit means new traces.
- dsim's 3D hive and contacts run on its rigid-body engine layer, so they are much harder to
  port than its pure hive logic; `alea/hifi/PORTING.md` splits the two.
