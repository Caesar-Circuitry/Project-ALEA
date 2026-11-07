# ALEA roadmap

Where the repo is, what each pull request delivers, and where the project goes after setup.
Read this before starting a PR. Update the status table when a PR merges (the `/pr` skill
reminds you).

Last updated: 2026-11-07.

## Setup PRs: status

| # | Branch | Scope | Status | Blocked on |
|---|---|---|---|---|
| 1 | `setup/01-skeleton` | Folder tree, `pyproject.toml`, `uv.lock`, pre-commit, `justfile`, CODEOWNERS | merged (GitHub #1) | |
| 2 | `setup/02-claude-workflow` | `.claude/` agents, hooks, skills, rules, `CLAUDE.md`, decision 0003 | merged (#2) | |
| 3 | `setup/03-ci` | CI on ubuntu, macOS, Windows; Dependabot; PR template | merged (#3), **partial** | |
| 3b | `setup/03b-ci-complete` | Finish PR 3, see below | merged (#8): four runners, Windows 11 ARM dropped; Dependabot PRs resolved 2026-11-07 (#4, #5, #10, #11 merged; #6, #9 closed; Gradle pinned to v5 in #17) | |
| 4 | `setup/04-move-sim` | Move the shot sim in, physics frozen | merged (#16) | |
| 5 | `setup/05-robot-contract` | `docs/robot-interface.md`, sample robot, contract test | merged (#19) | |
| 6 | `setup/06-data-importers` | SQLAlchemy models, `.rlog` reader, `.wpilog` reader | merged (#24) | |
| 7a | `setup/07a-devcontainer` | CPU dev container, agent shell sandbox, guard_container hook, decision 0006 | merged (#23) | |
| 7 | `setup/07-dev-env-docs` | Dev containers, `hpc/`, MkDocs site, notebook, README | todo | `_incoming/` docs text |
| 8 | `setup/08-hifi-stub` | `alea/hifi` stub, `fidelity` switch, decision 0005, delete `_incoming/` | todo | PR 4 |

PRs 4 to 8 need the source the user copies from `~/Downloads/alea_project` into `_incoming/`.
If `_incoming/` is missing, stop and ask; do not reconstruct the source.

## What each PR must deliver

### 3b: finish CI
Merged PR 3 runs three runners and has no docs or robot job. Remaining:
- Add `ubuntu-24.04-arm` to the matrix (all four targets from
  `[tool.uv].required-environments`). Run pyright once, on ubuntu.
- `robot` job on `robot/**` changes: Temurin JDK 17, Gradle cache, `./gradlew assembleDebug`.
- `docs` job: `mkdocs build --strict`, deploy Pages on `main`. Add it in PR 7 if `mkdocs.yml`
  does not exist yet.
- `.github/workflows/gpu-tests.md`, issue templates (`bug.yml`, `feature.yml`), Gradle in
  Dependabot, `docs/decisions/0004-branch-protection.md`.
- Merge or close the open Dependabot branches (checkout 7, setup-uv 7, warp-lang 1.19.0). Done 2026-11-07.
- Done when: CI green on all four runners.
- Dropped for now: Windows 11 ARM (win32/ARM64). cryptography, pyarrow, protobuf and debugpy
  lack win_arm64 wheels. Revisit when they ship them.

### Before 4: import the original ALEA code
The original Java-validated Warp code is not in this repo yet. Clone it into the git-ignored
`_incoming/` folder from the repo root:

```
git clone https://github.com/Caesar-Circuitry/alea-original.git _incoming/alea_project
git -C _incoming/alea_project rev-parse HEAD
```

The HEAD must be `7e2334bc8d09a7dc64e825c0838658ae7e91a9af`. The code lives in
`_incoming/alea_project/code/`.

Run the self-test with the repo venv. Do not pass `-I` to Python: the script imports
sibling modules.

```
just sync
uv run python _incoming/alea_project/code/selftest.py cpu
```

At that commit, 100.000 % of the 10,000 golden shots agree. The bar is at least 99.9 %.

Current hashes of the frozen files in the repo. `tests/test_frozen_files.py` enforces the SHA-1
values in CI.

| File | SHA-1 (`shasum -a 1`) | Git blob (`git hash-object`) |
|---|---|---|
| `alea/sim/shotsim.py` | `a2e96d19db3f3f0d9f72653a939fa8513883c974` | `b0ef01c353787dd74fee7a25dfb72b27c105c8c9` |
| `alea/sim/study.py` | `fd903a17a229e6c2b8c6e272be99bfb5421c203a` | `df8fed7170a8fbb9bfaf20618c5533f46d614caf` |
| `tests/golden/golden_shots.npy` | `2a13bb587528795e350fc0577e40fb2f7d36bcf4` | `0c8b180cd40808351b2278ff9050c86519c58fd4` |

```
shasum -a 1 alea/sim/shotsim.py
git hash-object alea/sim/shotsim.py
```

`study.py` differs from the original in `_incoming/` (SHA-1 `e2f14e2854c7647fa2a7f0126b84244f25df7549`)
only in its import line: `from shotsim import` became `from alea.sim.shotsim import`.

Windows: `certutil -hashfile <file> SHA1`.

Copying `shotsim.py`, `study.py` or `golden_shots.npy` into the repo is a physics change. It
needs the user's approval through `/physics-change`. Never regenerate `golden_shots.npy`. If
it is missing, stop and ask.

### 4: move the sim (physics frozen)
- Record the SHA-1 of `shotsim.py` and `study.py` in the PR body before anything moves.
- Move the sim files into `alea/sim/` with `git mv`. Only import lines may change in the two
  frozen files.
- Game constants into `alea/game/biobuzz.py` with `# source:` comments. Snapshot them in
  `tests/golden/game_constants_snapshot.json` and test equality.
- Verification scripts into `alea/sim/verification/`. `golden_shots.npy` into `tests/golden/`;
  if it is missing, stop and ask, never regenerate.
- `conf/study/brev72.yaml`; `run_study` keeps `--shots --device` and gains `--config`.
- `tests/test_selftest.py` asserts at least 99.9 % agreement.
- Agents: `implementer` moves, `physics-reviewer` signs off on the diff.
- Done when: `just selftest` passes and `just study` writes `summary.csv`.

### 5: robot contract
- `docs/robot-interface.md` first: PsiKit key, type, units, rate, source. All keys under
  `Alea/`. Motor current needs `FtcLogTuning.logMotorCurrent=true`.
- `robot/`: TeamCode-only Gradle project on FTC SDK v12.0 with PsiKit from
  `repo.dairy.foundation` (check the actual version on the Maven index).
- `tests/test_robot_contract.py` checks the Java keys and constants against the doc and
  `alea.game`. Decision 0002.
- Done when: contract test passes and `./gradlew assembleDebug` is green in CI.

### 6: data importers
- `alea/data/models.py` (Team, Event, Match, Robot, LogFile, Shot) and Alembic; default
  `sqlite:///alea.db`.
- `alea/data/rlog.py`: pure-Python RLOG revision 2 decoder, the format PsiKit writes. A tiny
  golden `.rlog` in `tests/golden/`.
- `.wpilog` reader behind the `logs` extra, same key contract.
- Done when: a sample log imports into SQLite with every contract key.

### 7: dev environment and docs
- `.devcontainer/cpu/` landed in 7a. `.devcontainer/cuda/` is still to do; `hpc/brev`,
  `hpc/slurm`, `hpc/apptainer` are still to do.
- `mkdocs.yml` and docs text from `_incoming/`; decision 0001.
- Notebook paired with jupytext; root README with a per-OS install table.
- Done when: `just docs` is clean and Pages is live.

### 8: hifi stub
- `alea/hifi/` README, `DSIM_VERSION`, `fidelity: fast | hifi` (hifi raises
  `NotImplementedError`), decision 0005 with the dsim port plan.
- Delete `_incoming/`; no file over 1 MB outside `tests/golden/`.
- Done when: the end-to-end checks in the setup plan pass from a fresh clone.

## After setup: project phases

Each `alea/` subfolder belongs to a phase; its README says which.

| Phase | Area | Folder | Goal |
|---|---|---|---|
| 0 | Data contract | `robot/`, `alea/data/` | Every robot log and match result lands in one database |
| 1 | Shot simulator | `alea/sim/`, `alea/game/`, `conf/`, `hpc/` | Monte Carlo studies on Brev GPUs, results in notebooks |
| 1b | High fidelity | `alea/hifi/` | Port dsim hive tipping and ball contacts, validated against dsim traces |
| 2 | Video review | `alea/video/` | Field homography, click-and-log, then tracking |
| 3-5 | Analysis | `alea/analysis/` | Calibrate the sim on real shots, driver critique, robot health |
| 6 | Web app | `alea/web/` | Streamlit for the team, FastAPI service later |
| 7 | Match simulation | `alea/matchsim/` | Full auto and match simulation on top of the shot sim |

Phase work uses `feature/<phase>-<topic>` branches, one PR each. Large ports (the dsim port in
1b) are the kind of job `orchestrator` exists for, and only with the user's approval.

## Rules for agents using this file

- Pick work from the first row marked **next**. Do not start a PR whose "Blocked on" is not met.
- One PR per row. Do not fold a later PR's scope into an earlier one.
- When a PR merges, change its status and mark the following row **next**, in the same PR or
  right after it.
