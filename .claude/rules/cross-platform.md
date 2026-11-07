---
paths:
  - "**/*.py"
  - "pyproject.toml"
  - "justfile"
  - ".github/**"
  - ".devcontainer/**"
---

# Cross-platform code

ALEA runs on macOS, Linux and Windows, on x86-64 and arm64, with no GPU. CI proves it on four
runners. When you edit code or config:

- Paths through `pathlib`; no hard-coded `/` or `\`; no assumptions about case sensitivity.
- No shell scripts in the dev path. Helpers are Python run via `uv run python`, or `just`
  recipes that are single-line and shell-neutral. Linux-only scripts live under `hpc/`.
- Subprocesses via `subprocess.run([...])` with a list, never `os.system`.
- A dependency without a wheel on one platform gets a PEP 508 marker on that dependency; never
  drop the platform. Re-run `uv lock`; `[tool.uv].required-environments` makes it fail loudly.
- NVIDIA-only paths (Warp CUDA device, CuPy, RAPIDS) always have a CPU fallback and are tested
  with `@pytest.mark.gpu` so the default run skips them.
- Line endings are handled by `.gitattributes`; do not add `.bat`-only or `.sh`-only steps to
  the README without the other OS's equivalent.
