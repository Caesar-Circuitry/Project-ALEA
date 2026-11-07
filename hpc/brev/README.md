# hpc/brev

Brev instance setup. `setup.sh` installs uv, syncs the project with the `gpu` extra and runs the
72-million-shot study from `conf/study/brev72.yaml`. Pass `--plan` to print the plan only.

```
git clone https://github.com/Caesar-Circuitry/Project-ALEA.git && cd Project-ALEA
bash hpc/brev/setup.sh --plan
bash hpc/brev/setup.sh
```

`run_study` runs the self-test first and refuses to continue below 99.9 % agreement. Linux only.
Run `uv run pytest -m gpu` on the instance to check the GPU tests.

Ran 2026-11-07 on a Brev g2-standard-4 with one NVIDIA L4: self-test 100.000 %, about 2.0M
shots/s, the 72M-shot study took 1.2 minutes.

## Automating from your machine

- `brev exec <instance> "<cmd>"` runs a command non-interactively (`brev shell` is interactive only).
- `brev copy instance:/path ./local/` fetches results.
- `brev stop <instance>` pauses billing.
- The first SSH connect can take about 30 s.
- Start long runs with `nohup` and read the log, e.g. `brev exec <instance> "nohup bash hpc/brev/setup.sh > run.log 2>&1 &"`.

**Roadmap phase:** 1 (landed in PR 7)
