# alea.hifi

High-fidelity option: hive tipping and ball-contact physics ported from dsim (genius0412/dsim). Carries dsim's PolyForm Noncommercial 1.0.0 license, different from the rest of ALEA. Stub until the port lands; the plan is in `docs/decisions/0005-hifi-dsim-port.md`.

- `DSIM_VERSION`: the pinned dsim commit every ported file must cite (`62d2446e`, committed 2026-11-02).
- `LICENSE-dsim`: dsim's PolyForm Noncommercial 1.0.0 license, verbatim, with its required notice.
- `PORTING.md`: what to port from dsim and in what order, the differences from `alea/game/` to resolve, and how to validate.
- `check_fidelity(fidelity)`: validates the `fidelity: fast | hifi` option. `fast` is the Warp simulator; `hifi` raises `NotImplementedError` pointing at decision 0005.
- `python -m alea.sim.run_study --fidelity fast|hifi` (or `fidelity:` in the study YAML) uses it.

**Roadmap phase:** 1b (stub now, port later)
