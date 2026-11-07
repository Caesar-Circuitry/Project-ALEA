# hpc/slurm

Example Slurm job running `python -m alea.sim.run_study --config conf/study/brev72.yaml`. The study
config is plain YAML, read with PyYAML.

`alea_study.sbatch` asks for one GPU for two hours, syncs the project with uv and writes results to
`results/<jobid>/`. Submit from the repo root with `sbatch hpc/slurm/alea_study.sbatch`; add
`--partition` and `--account` for your cluster. Untested on a real cluster.

**Roadmap phase:** 1 (landed in PR 7)
