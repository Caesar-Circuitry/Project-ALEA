# hpc/brev

Brev instance setup. `setup.sh` installs uv, syncs the project with the `gpu` extra and runs the
72-million-shot study from `conf/study/brev72.yaml`. Pass `--plan` to print the plan only.

```
git clone https://github.com/Caesar-Circuitry/Project-ALEA.git && cd Project-ALEA
bash hpc/brev/setup.sh --plan
bash hpc/brev/setup.sh
```

`run_study` runs the self-test first and refuses to continue below 99.9 % agreement. Linux only.
Run `uv run pytest -m gpu` on the instance to check the GPU tests. Not yet run on a real
instance by this change.

**Roadmap phase:** 1 (landed in PR 7)
