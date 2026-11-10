# ALEA

FTC team 24331 Caesar Circuitry's strategy analysis platform for BIOBUZZ 2026-27. Today it is a
validated NVIDIA Warp Monte Carlo shot simulator; it grows into match data, robot log import,
video review, driver critique, match simulation and a web app. Python 3.12 lives in `alea/`,
Java only in `robot/` (an FTC SDK sample, not the competition robot).

## How work happens here

Every session in this repo runs as the `lead` agent (`"agent": "lead"` in
`.claude/settings.json`). The lead plans, delegates, verifies and reports. It has no Edit or
Write tool, and a hook limits its shell to read-only and check commands. Code changes go through
subagents, each pinned to a model:

| Need | Spawn | Model |
|---|---|---|
| find files, symbols, call paths | `explorer` | Haiku |
| plan a change by file ownership; attack the plan | `planner`, `plan-critic` | Opus*, Sonnet |
| `[careful]` items: logic, multi-file code, CI, configs | `implementer` | Sonnet |
| `[fast]` items: one file, spec fully given | `implementer-fast` | Haiku |
| write the tests a plan names | `test-writer` | Sonnet |
| write or change docs, READMEs, decision records | `docs-writer` | Haiku |
| safety review: `alea/sim`, `alea/game`, `alea/hifi`, `tests/golden`, other sensitive paths | `physics-reviewer` | Opus* |
| check a working tree or branch before /pr | `verifier` | Opus* |
| run a heavy check (robot build, GPU tests) | `heavy-check-operator` | Sonnet |
| diagnose a CI failure | `ci-diagnoser` | Opus |
| periodic audit of practices, security, AI mistakes | `auditor` | Opus |
| coordinate a multi-agent, multi-PR job | `orchestrator` | Fable, asks the user first |

\* Opus on the `max` profile, Sonnet on `pro`; switch with `just profile max|pro`.
All Sonnet and Haiku work can consult Opus through the built-in advisor (`advisorModel: opus` in `.claude/settings.json`).

Writers never judge and judges never edit. Tests are the default proof; heavy checks are an
escalation. `/feature <what>` runs the whole loop: plan, approval, parallel writers on disjoint
files (an agent team for a big plan), verifier, safety review, docs; `/plan`, `/verify`,
`/new-unit`, `/heavy` run single steps. Units, commands, protected paths and the profile live
in `.claude/repo.json`.
The full policy, including when to escalate a model, is in `.claude/AGENTIC_WORKFLOW.md`.
The PR stages, what is done and what is next are in `.claude/ROADMAP.md`; read it before
starting a PR.

## Rules Claude Code enforces (hooks and permission rules)

- Edits to `alea/sim/shotsim.py` and `alea/sim/study.py` are blocked. They must stay identical
  to the Java Code Sim. The rare approved change goes through `/physics-change`.
- A writer (`implementer`, `implementer-fast`, `test-writer`) cannot finish while `ruff check`,
  `ruff format --check` or `pytest` fail; a team task cannot close while its unit's tests fail.
- Tests are not removed, skipped or deselected; golden files and applied migrations are
  append-only; `uv.lock` is not hand-edited; CI steps are not removed (`guard_tests.py`, `guard_bash.py`).
- `git push` asks the user. `/pr` opens the PR with `gh pr create`, which also asks. Spawning `orchestrator` asks the user.
- Every agent except the lead runs shell work in the container `alea-dev`, through `just dev`
  (`guard_container.py`). File edits stay inside the repo. Decision 0006.
- Pre-commit rejects files over 1 MB outside `tests/golden/`, and private keys anywhere.

## Rules Claude follows

- After any change under `alea/sim` or `alea/game`, run `just selftest`: it must agree with the
  Java answers on at least 99.9 % of the 10,000 golden shots. Never regenerate
  `tests/golden/golden_shots.npy`; ask the user for it.
- Game values live only in `alea/game/`. Units go in names: `dist_in`, `speed_in_s`, `t_s`.
- No secrets in git. `.env` is ignored; `.env.example` carries empty values.
- Code runs on macOS, Linux and Windows. Windows is x86-64 only for now (Windows arm64 is
  dropped until its dependencies ship wheels). Use `pathlib`, no shell scripts in the dev path,
  platform markers in `pyproject.toml` instead of dropping a platform.
- Every folder has a `README.md` naming what goes there and which roadmap phase fills it.
- Small commits on a `setup/…` or `feature/…` branch, merged by pull request via `/pr`.
  Never commit to `main`.
- The lead runs `just dev-up` before it delegates. `git push` and `gh` run on the host only (the lead, after the user approves).
  New branches: `git switch -c <name> --no-track origin/main`. Push with `git push origin <branch>`,
  never `-u` (it rewrites `.git/config` and breaks the container's overlay).
- If Remote Control is connected, send a `PushNotification` to the user's phone when a PR is
  ready (branch pushed, compare link printed) and when you are blocked on the user's input or a
  permission (push approval, a question, a denied action). One short line that leads with what to
  act on. No notifications for routine progress.

## Commands

```
just sync       uv sync --all-extras --no-extra gpu --group dev   (run first in a new worktree)
just test       uv run pytest                                     (skips gpu-marked tests)
just selftest   CPU self-test against tests/golden/golden_shots.npy
just lint       ruff check + ruff format --check + pyright
just fmt        ruff --fix + ruff format                           (implementer only)
just docs       uv run mkdocs build --strict
just robot      cd robot && ./gradlew assembleDebug               (JDK 17 + Android SDK)
just study      uv run python -m alea.sim.run_study --shots 10000 --device cpu
just dev-up     build and start the container `alea-dev`, then sync it (lead, host)
just dev-down   stop and remove `alea-dev`                            (lead, host)
just dev-status say whether `alea-dev` runs
just dev <cmd>  run <cmd> in `alea-dev`, e.g. `just dev uv run pytest -q`
```

## Gotchas

- The physics hook also blocks a shell command that names a frozen file next to a redirect,
  `sed -i`, `mv`, `cp` or `rm`. `git mv` of those files is allowed.
- `uv.lock` resolves for four platforms at once. If a package has no wheel for one of them, add
  a marker on that dependency; CI on that platform is the proof.
- The venv is not shared between worktrees. `just sync` is cheap once the cache is warm.
