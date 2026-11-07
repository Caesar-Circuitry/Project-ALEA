# conf (study configs)

YAML configuration. Study definitions live under `conf/study/` and are read with PyYAML
(`yaml.safe_load`). Hydra is not a dependency. The `fidelity` switch arrives in PR 8.

- `study/`: study definitions read by `python -m alea.sim.run_study --config`.

**Roadmap phase:** 1
