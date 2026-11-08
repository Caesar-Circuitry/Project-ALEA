# alea.sim

Monte Carlo shot simulator on NVIDIA Warp (GPU, CPU fallback). Physics here is frozen: it must match the Java Code Sim on >= 99.9 % of the 10,000 golden shots (`selftest.main('cpu')`, or `just selftest`).

- `shotsim.py`: physics kernel and fixed-shot kernel. FROZEN, byte-identical to alea-original@7e2334bc.
- `study.py`: the study kernel (random spots, robot-code aiming, errors, counting). FROZEN; only its `shotsim` import line differs from the original.
- `hive_frame.b64`: hive support-frame cubes read by `shotsim.py`.
- `selftest.py`: golden-shot check plus kernel consistency checks; reads `tests/golden/golden_shots.npy`.
- `run_study.py`: `python -m alea.sim.run_study [--config conf/study/brev72.yaml] [--shots N] [--device cpu]`; writes `results/study/` (git-ignored) with `cond_XXX.npz`, `summary.csv`, plots. Resumes a stopped run. With `--fidelity hifi` (and a `hifi:` block in the YAML, see `conf/study/hifi_example.yaml`) it runs the same kernel plus hive sessions and writes labelled `results/study-hifi/` (`cond_hifi_XXX.npz`, `summary_hifi.csv`, `hifi_*.png`); it refuses to mix the two kinds in one directory. For hifi, an `out` of `results/study` coming from the YAML (set or defaulted) is redirected to `results/study-hifi` with a printed line; any other `out`, or `--out` on the command line, is used as given (and still refused if it holds fast results).
- `conditions.py`: builds the condition grid (defaults = brev72). `plots.py`: pictures from a finished study.
- `results.py`: `detect_fidelity`, `cond_path`, `load_summary` (summary.csv, or rebuilt from `cond_XXX.npz`), `factor_effects`, `worst_best`; plain Python, no GPU. Used by `plots.py` and `notebooks/02_study_results.py`.
- `verification/`: checks against the Java sim.

`setup_brev.sh` from the original is not moved here; Linux-only setup lives in `hpc/` (roadmap PR 7).

**Roadmap phase:** 1
