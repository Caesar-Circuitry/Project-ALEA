# ALEA task runner. Install `just`: brew install just | winget install Casey.Just | cargo install just
# Every recipe is a single shell-neutral command; the raw commands are also listed in README.md.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

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
robot:
    cd robot && ./gradlew assembleDebug

# GPU tests (Brev / any NVIDIA machine)
gpu-test:
    uv run pytest -m gpu
