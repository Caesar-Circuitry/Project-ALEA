# ALEA

Strategy analysis platform for FTC team 24331 Caesar Circuitry, BIOBUZZ 2026-27 season.
Starts as a validated GPU Monte Carlo shot simulator (NVIDIA Warp) and grows into a match
database, robot log import, video review, driver critique, robot health monitoring, full match
simulation, scouting and a web app.

Full README lands with the docs PR. Quick start today:

```
uv sync --all-extras --no-extra gpu --group dev
uv run pytest
```

## Commands

Every recipe in `justfile`, with the command it runs. Install `just` first: `brew install just`,
`winget install Casey.Just` or `cargo install just`.

```
just                  list the recipes (same as just --list)
just sync             uv sync --all-extras --no-extra gpu --group dev
just test             uv run pytest
just selftest         uv run python -c "from alea.sim import selftest; import sys; sys.exit(0 if selftest.main('cpu') else 1)"
just study 10000 cpu  uv run python -m alea.sim.run_study --shots 10000 --device cpu
just lint             uv run ruff check . && uv run ruff format --check . && uv run pyright
just fmt              uv run ruff check --fix . && uv run ruff format .
just docs             uv run mkdocs build --strict
just docs-serve       uv run mkdocs serve
just robot            cd robot && ./gradlew assembleDebug        (Unix)
just robot            cd robot; .\gradlew.bat assembleDebug      (Windows)
just worktree-prune   uv run python -m alea.tools.worktree_prune
just gpu-test         uv run pytest -m gpu
just dev-build        docker build -t alea-dev:cpu --build-arg UID=1000 --build-arg GID=1000 .devcontainer/cpu
just dev-start        docker start alea-dev || docker run -d --name alea-dev ... alea-dev:cpu sleep infinity
just dev-sync         docker exec -w <repo root> alea-dev just sync
just dev-up           just dev-build, then just dev-start, then just dev-sync
just dev-down         docker rm -f alea-dev
just dev-status       docker ps -a --filter name=^alea-dev$
just dev <cmd>        docker exec -w <this folder> alea-dev <cmd>
```

Notes:

- `just sync` leaves out the `gpu` extra. On a GPU machine, run `uv sync --all-extras --group dev`.
- `just robot` needs JDK 17 and the Android SDK.
- The dev container is the sandbox for agents. Its setup and troubleshooting are in
  `.devcontainer/README.md`. `just dev-start` runs `docker run` with the repo mounted at its host
  path, read-only overlays on `.git/hooks`, `.git/config`, `.git/info` and `.git/modules`, and a
  `/dev/null` mask on `.env`. Print the full `docker run` line with `just --show dev-start`.
- `just dev-up` and `just dev-start` need `docker`. `just dev` and `just dev-status` need the
  container running. `just dev` is not supported on Windows yet; it stops with an error that
  points to WSL2.
- The container has no Android SDK, so `just robot` runs in CI, not in the container.
- On Windows, recipes run in PowerShell 7 (`pwsh`). Install PowerShell 7 first. The shell is set
  by `set windows-shell` in `justfile`.

**Roadmap phase:** all (the full README lands in PR 7)
