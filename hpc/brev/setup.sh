#!/usr/bin/env bash
# Set up a fresh Brev GPU instance (Ubuntu, NVIDIA driver preinstalled) and run the 72M-shot study.
# Run from a clone of the repo:  bash hpc/brev/setup.sh [--plan]
set -euo pipefail
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
nvidia-smi -L
uv sync --all-extras --group dev
uv run python -m alea.sim.run_study --config conf/study/brev72.yaml "$@"
