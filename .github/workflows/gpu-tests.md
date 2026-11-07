# GPU tests (manual)

GitHub-hosted runners have no GPU, so CI runs the CPU path only (`uv sync --no-extra gpu`).
GPU tests are run by hand on a Brev instance before any PR that touches the sim, and before
a study run.

## Steps

1. Start a Brev GPU instance (NVIDIA, CUDA 12 capable) and open a shell on it.
2. Clone the repo and check out the branch under test:
   `git clone https://github.com/<owner>/Project-ALEA && cd Project-ALEA && git checkout <branch>`
3. Install uv if missing, then run `uv sync --all-extras --group dev`. Do not use `just sync` here:
   it leaves out the `gpu` extra.
4. Confirm the GPU is visible: `nvidia-smi`.
5. Run `just lint` and `just test`, then the GPU-marked tests (`just gpu-test`) and `just selftest`.
   The selftest must agree with the golden shots at 99.9 % or better.
6. Paste the commands and their results into the PR description.
7. Stop the Brev instance when done; it bills while running.

## Notes

- Never regenerate golden files to make a GPU run pass.
- A result that differs between CPU and GPU is a bug to report, not a tolerance to widen.
