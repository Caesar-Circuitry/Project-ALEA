# .devcontainer/cuda

CUDA image for Linux x86-64 machines with an NVIDIA GPU and for Brev instances. It mirrors
`../cpu/` (same `dev` user, uv 0.13.7, just 1.45.0, git identity placeholder, no credentials,
venv and uv cache in volumes) on `nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04`. uv installs
Python 3.12. The sandbox rules of decision 0006 apply: no push credentials, no secrets, dropped
capabilities, `no-new-privileges`, a process limit.

**Roadmap phase:** 1 (landed in PR 7, `setup/07-dev-env-docs`)

## Use

Needs Docker with the NVIDIA Container Toolkit. In VS Code, "Reopen in Container" and pick this
folder's `devcontainer.json`. `postCreateCommand` runs `uv sync --all-extras --group dev`, which
includes the `gpu` extra. Then `uv run pytest -m gpu`.

By hand from the repo root:

```
docker build -t alea-dev:cuda .devcontainer/cuda
docker run --rm --gpus all alea-dev:cuda nvidia-smi
```

## Differences from cpu

- Not wired into `just dev-up`; the agent sandbox stays on the CPU image.
- Single-arch (linux/amd64). No macOS or Windows host support; use `cpu/` there.
- `--gpus=all` in `runArgs`.

## Not yet verified

The image was written on a machine without an NVIDIA GPU and has not been built or run. Build it
and run `uv run pytest -m gpu` on a GPU host before relying on it.

## Files

- `Dockerfile`: the image.
- `devcontainer.json`: VS Code and Codespaces config.
