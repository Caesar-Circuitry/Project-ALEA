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
| write or change code, tests, CI, configs | `implementer` | Sonnet |
| write or change docs, READMEs, decision records | `docs-writer` | Haiku |
| review anything under `alea/sim`, `alea/game`, `alea/hifi`, `tests/golden` | `physics-reviewer` | Opus |
| coordinate a multi-agent, multi-PR job | `orchestrator` | Fable, asks the user first |

One subagent per task, worktree isolation when two run at once, short summaries back.
The full policy, including when to escalate a model, is in `.claude/AGENTIC_WORKFLOW.md`.
The PR stages, what is done and what is next are in `.claude/ROADMAP.md`; read it before
starting a PR.

## Rules Claude Code enforces (hooks and permission rules)

- Edits to `alea/sim/shotsim.py` and `alea/sim/study.py` are blocked. They must stay identical
  to the Java Code Sim. The rare approved change goes through `/physics-change`.
- An `implementer` cannot finish while `ruff check`, `ruff format --check` or `pytest` fail.
- `git push` asks the user. Spawning `orchestrator` asks the user.
- Pre-commit rejects files over 1 MB outside `tests/golden/`, and private keys anywhere.

## Rules Claude follows

- After any change under `alea/sim` or `alea/game`, run `just selftest`: it must agree with the
  Java answers on at least 99.9 % of the 10,000 golden shots. Never regenerate
  `tests/golden/golden_shots.npy`; ask the user for it.
- Game values live only in `alea/game/`. Units go in names: `dist_in`, `speed_in_s`, `t_s`.
- No secrets in git. `.env` is ignored; `.env.example` carries empty values.
- Code runs on macOS, Linux and Windows, x86-64 and arm64. Use `pathlib`, no shell scripts in
  the dev path, platform markers in `pyproject.toml` instead of dropping a platform.
- Every folder has a `README.md` naming what goes there and which roadmap phase fills it.
- Small commits on a `setup/…` or `feature/…` branch, merged by pull request via `/pr`.
  Never commit to `main`.

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
```

## Gotchas

- The physics hook also blocks a shell command that names a frozen file next to a redirect,
  `sed -i`, `mv`, `cp` or `rm`. `git mv` of those files is allowed.
- `uv.lock` resolves for five platforms at once. If a package has no wheel for one of them, add
  a marker on that dependency; CI on that platform is the proof.
- The venv is not shared between worktrees. `just sync` is cheap once the cache is warm.
