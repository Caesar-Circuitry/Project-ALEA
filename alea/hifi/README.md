# alea.hifi

High-fidelity option: hive tipping and ball-contact physics ported from dsim (genius0412/dsim). Carries dsim's PolyForm Noncommercial 1.0.0 license, different from the rest of ALEA. The pure hive logic is ported (phase 1b); the 3D hive and contacts are not. `fidelity: hifi` runs: the fast shot kernel unchanged plus hive sessions on the ported logic; the plan is in `docs/decisions/0005-hifi-dsim-port.md`.

- `DSIM_VERSION`: the pinned dsim commit every ported file must cite (`62d2446e`, committed 2026-11-02).
- `LICENSE-dsim`: dsim's PolyForm Noncommercial 1.0.0 license, verbatim, with its required notice.
- `PORTING.md`: what to port from dsim and in what order, the differences from `alea/game/` to resolve, and how to validate.
- `hive.py`, `hive_constants.py`, `hive_math.py`: the port of dsim's `hive.ts` (capture, load against the tip table, swing timer, release and spill, miss deflection). Uses dsim's numbers, not `alea/game`'s; replayed against `tests/hifi_traces/` by `tests/test_hifi_hive_*.py`.
- `check_fidelity(fidelity)`: validates the `fidelity: fast | hifi` option.
- `hive_session.py`: the session model (seeded fired shots into a hive, tips and timing); its docstring says what is and is not modelled and which parameters are open. `hifi_study.py`: the per-condition hifi run and the `hifi:` YAML block. `frame.py`: dsim to ALEA frame, shifted from the field centre (70.65, provisional: origin is open item 1; result-neutral because the two conversions cancel). These three are original ALEA glue that uses the port, under the same licence.
- Every `hive_*` column comes from a session model with the hive at rest during the swing (kernel limit); it is not measured physics, and the `hive_caveat` column says so. `shot_interval_s` must be a whole multiple of 1/60 s; the 1/60 s tick (dsim's timer step) is fixed and not a YAML key (`hive_tick_s`, `hive_alliance` are saved and checked on resume). The caveat also says the four session parameters are open placeholders.
- How to read the `hive_*` columns: `hive_spilled_mean` includes the 3 staged nectar; a ball captured before release counts in both captured and spilled; the let-swing-finish loop can count a tip completing after the last shot; `hive_first_*_s_mean` averages only over sessions that tipped (NaN if none); with `retarget_after_tip: false` every later scored ball is rejected after the first tip, so the hive cannot tip again.
- Results go to `results/study-hifi` (`cond_hifi_XXX.npz`, `summary_hifi.csv`), never into a fast results directory.
- `python -m alea.sim.run_study --fidelity fast|hifi` (or `fidelity:` in the study YAML) uses it.

**Roadmap phase:** 1b (hive logic ported; contacts and integration later)
