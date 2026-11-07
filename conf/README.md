# conf (study configs)

YAML configuration. Study definitions live under `conf/study/` and are read with PyYAML
(`yaml.safe_load`). Hydra is not a dependency. Set `fidelity: fast` (default) or `hifi` (not yet implemented, decision 0005) in a study YAML, or pass `--fidelity`.

- `study/`: study definitions read by `python -m alea.sim.run_study --config`.

**Roadmap phase:** 1
