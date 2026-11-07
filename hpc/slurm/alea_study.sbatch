#!/usr/bin/env bash
#SBATCH --job-name=alea-study
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --time=02:00:00
#SBATCH --output=alea-study-%j.log
# Submit from the repo root:  sbatch hpc/slurm/alea_study.sbatch
# Adjust partition/account with sbatch flags, e.g. --partition=gpu --account=<acct>.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
uv sync --all-extras --group dev
uv run python -m alea.sim.run_study --config conf/study/brev72.yaml --out "results/${SLURM_JOB_ID}"
