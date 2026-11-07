# ALEA task runner. Install `just`: brew install just | winget install Casey.Just | cargo install just
# Every recipe is a single shell-neutral command; the raw commands are also listed in README.md.
set windows-shell := ["pwsh", "-NoLogo", "-NoProfile", "-Command"]

default:
    @just --list

# Create/update the virtual env with every CPU extra and the dev tools
sync:
    uv sync --all-extras --no-extra gpu --group dev

# Run the CPU test suite (skips gpu-marked tests)
test:
    uv run pytest

# Run the shot-sim self-test against the 10,000 golden Java shots on CPU
selftest:
    uv run python -c "from alea.sim import selftest; import sys; sys.exit(0 if selftest.main('cpu') else 1)"

# Run a study; e.g. `just study 10000 cpu`
study shots="10000" device="cpu":
    uv run python -m alea.sim.run_study --shots {{shots}} --device {{device}}

# Lint, format check and type check
lint:
    uv run ruff check . && uv run ruff format --check . && uv run pyright

# Auto-fix lint and format
fmt:
    uv run ruff check --fix . && uv run ruff format .

# Build the docs site strictly
docs:
    uv run mkdocs build --strict

# Serve the docs locally
docs-serve:
    uv run mkdocs serve

# Build the sample robot code (needs JDK 17 + Android SDK)
[unix]
robot:
    cd robot && ./gradlew assembleDebug

# Build the sample robot code (needs JDK 17 + Android SDK)
[windows]
robot:
    cd robot; .\gradlew.bat assembleDebug

# Remove clean agent worktrees under .claude/worktrees/ and their merged worktree-agent-* branches
worktree-prune:
    uv run python -m alea.tools.worktree_prune

# --- Agent sandbox (CPU dev container). The lead stays on the host; every other agent runs its
# shell work through `just dev ...`. Needs only `docker`. Push credentials never enter it.
# The repo is mounted at its own host path (not /workspace) so a git worktree's `.git` file, which
# holds an absolute host path, resolves inside the container. Settings (override with env vars):
# DEV_NETWORK is the docker network (default `bridge`; point it at a restricted network to limit
# egress), DEV_UID/DEV_GID the owner of files written to the bind mount, DEV_MEMORY the memory
# cap, DEV_CWD the working directory inside the container (default: where `just dev` is run).
dev_network := env("DEV_NETWORK", "bridge")
dev_uid := env("DEV_UID", "1000")
dev_gid := env("DEV_GID", "1000")
dev_memory := env("DEV_MEMORY", "6g")
# The project root; CLAUDE_PROJECT_DIR keeps it right when run from inside a worktree.
dev_root := env("CLAUDE_PROJECT_DIR", justfile_directory())
dev_cwd := env("DEV_CWD", invocation_directory())
# Read-only overlays so the container cannot plant code the host later runs (git hooks, config
# such as core.fsmonitor or hooksPath, `.env` secrets). Evaluated on every `dev-up`; a path that
# does not exist is skipped. objects, refs and the index stay writable so commits work. Branch
# tracking is written to .git/config, so agents use `git switch -c x --no-track origin/main`.
dev_ro_hooks := "-v " + dev_root + "/.git/hooks:" + dev_root + "/.git/hooks:ro"
dev_ro_config := "-v " + dev_root + "/.git/config:" + dev_root + "/.git/config:ro"
dev_ro_info := if path_exists(dev_root + "/.git/info") == "true" { "-v " + dev_root + "/.git/info:" + dev_root + "/.git/info:ro" } else { "" }
dev_ro_modules := if path_exists(dev_root + "/.git/modules") == "true" { "-v " + dev_root + "/.git/modules:" + dev_root + "/.git/modules:ro" } else { "" }
dev_mask_env := if path_exists(dev_root + "/.env") == "true" { "-v /dev/null:" + dev_root + "/.env:ro" } else { "" }

# Build the dev image (cached, so cheap when nothing changed)
dev-build:
    docker build -t alea-dev:cpu --build-arg UID={{dev_uid}} --build-arg GID={{dev_gid}} .devcontainer/cpu

# Start the long-lived `alea-dev` container, creating it if missing. To change mounts, `just dev-down` first.
dev-start:
    docker start alea-dev || docker run -d --name alea-dev --network {{dev_network}} --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=512 --memory={{dev_memory}} -w "{{dev_root}}" -v "{{dev_root}}:{{dev_root}}" {{dev_ro_hooks}} {{dev_ro_config}} {{dev_ro_info}} {{dev_ro_modules}} {{dev_mask_env}} -v alea-dev-venv:/home/dev/.venv -v alea-dev-uv-cache:/home/dev/.cache/uv alea-dev:cpu sleep infinity

# Install the project inside the container
dev-sync:
    docker exec -w "{{dev_root}}" alea-dev just sync

# Build the image, start the container and sync it (idempotent)
dev-up: dev-build dev-start dev-sync

# Stop and remove the container; the uv cache and venv volumes are kept
dev-down:
    docker rm -f alea-dev

# Say whether the container is running
dev-status:
    docker ps -a --filter name=^alea-dev$ --format "alea-dev: {{"{{"}}.Status{{"}}"}}"

# File overlays (.git/config, .env) are dropped silently when the host rewrites the file (git on
# the host replaces .git/config on many commands). Refuse to run until `dev-down` + `dev-up`.
[unix]
_dev-check:
    @docker exec -w "{{dev_root}}" alea-dev sh -c 'for f in .git/config .env; do if [ -e "$f" ] && ! grep -q "/$f " /proc/self/mountinfo; then echo "read-only overlay on $f is gone (the host rewrote it): ask the user to run just dev-down and just dev-up" >&2; exit 1; fi; done'

# Run a command in the container, in the same folder as here: `just dev uv run pytest -q`.
# Compound commands go inside it: `just dev bash -c 'ls && pwd'`.
[positional-arguments]
[unix]
dev *args: _dev-check
    @docker exec -w "{{dev_cwd}}" alea-dev "$@"

# just's PowerShell variant would re-split quoted arguments, so refuse instead of mangling them.
[windows]
dev *args:
    {{ error("just dev is not supported on Windows yet; use WSL2") }}

# GPU tests (Brev / any NVIDIA machine)
gpu-test:
    uv run pytest -m gpu
