# ALEA — instructions for Claude Code

ALEA is FTC team 24331 Caesar Circuitry's strategy analysis platform (BIOBUZZ 2026-27). It starts
as a validated NVIDIA Warp Monte Carlo shot simulator and grows into a match database, robot log
import, video review, driver critique, robot health, match simulation, scouting and a web app.
Python 3.12 for everything in `alea/`; Java only in `robot/` (FTC SDK sample).

## Rules (every change)

1. **Never change the shot physics.** `alea/sim/shotsim.py` and `alea/sim/study.py` must stay
   identical to the Java Code Sim. Moving them is fine; changing numbers or logic is not. A hook in
   `.claude/settings.json` blocks edits to them unless `ALEA_ALLOW_PHYSICS_EDIT=1` is set, and that
   only happens with the user's explicit OK plus a Java comparison attached to the PR.
2. **The self-test must pass** after any change touching the sim: `just selftest`
   (`selftest.main("cpu")` agrees with the Java answers on >= 99.9 % of 10,000 golden shots).
3. **No big files in git**: no video, logs, `.npz` results, models, zips. `tests/golden/` is the only
   exception. Pre-commit rejects files over 1 MB elsewhere.
4. **No secrets in git.** Keys go in `.env` (ignored); `.env.example` has empty values.
5. **Units in names** (`dist_in`, `speed_in_s`, `t_s`). Game values live only in `alea/game/`.
6. **Small commits, clear messages, on a branch, merged by pull request.** Never commit to `main`.
7. **Every NVIDIA-only path has a CPU fallback.** Code must run on macOS, Linux and Windows,
   x86-64 and arm64. No shell scripts in the dev path; helpers are Python or `uv`/`just` commands.
8. **Every folder has a README** saying what goes there and which roadmap phase fills it.

## Commands

```
just sync        uv sync --all-extras --no-extra gpu --group dev
just test        uv run pytest                      (skips gpu-marked tests)
just selftest    CPU self-test against tests/golden/golden_shots.npy
just study       uv run python -m alea.sim.run_study --shots 10000 --device cpu
just lint        ruff check + ruff format --check + pyright
just fmt         ruff --fix + ruff format
just docs        uv run mkdocs build --strict
just robot       cd robot && ./gradlew assembleDebug   (JDK 17 + Android SDK)
just gpu-test    uv run pytest -m gpu                 (Brev / NVIDIA machine)
```

## Where things live

| Path | What | Phase |
|---|---|---|
| `alea/game/` | BIOBUZZ field, hive, rules, robot constants (single source of truth) | 1 |
| `alea/sim/` | Warp shot sim (frozen physics), studies, self-test, `verification/` | 1 |
| `alea/hifi/` | dsim-ported hive tipping, PolyForm NC license (stub) | 1b |
| `alea/data/` | SQLAlchemy models, `.rlog`/`.wpilog` importers | 0 |
| `alea/video/`, `alea/analysis/`, `alea/web/`, `alea/matchsim/` | later phases | 2-7 |
| `robot/` | sample FTC project showing the ALEA logging contract (not the competition code) | 0 |
| `docs/` | MkDocs site; `docs/decisions/` holds numbered decision records | all |
| `conf/` | Hydra configs (`conf/study/*.yaml`) | 1 |
| `tests/` | pytest; `tests/golden/` known answers | all |
| `hpc/` | Brev, Slurm, Apptainer (Linux only) | 1 |

## Model policy

Read `.claude/AGENTIC_WORKFLOW.md` before spawning agents. Short version: Haiku for lookups and
boilerplate, Sonnet for routine implementation, Opus for physics-adjacent work and review.
**Fable is for complex multi-agent orchestration only and only when the user has explicitly
approved it for that task.** Never escalate to Fable on your own.

## Workflow

Plan mode for anything multi-file. Explore → plan → implement in a worktree → `just test` +
`just selftest` → review → PR using `.github/pull_request_template.md`. Physics-touching diffs
need a human sign-off. See `.claude/AGENTIC_WORKFLOW.md` for the full loop and parallelism rules.
