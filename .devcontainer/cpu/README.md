# .devcontainer/cpu

The CPU image for the agent sandbox. `just dev-up` builds it from this folder and runs the
`alea-dev` container from it. Multi-arch: linux/arm64 and linux/amd64. No GPU.

**Roadmap phase:** 1 (landed in PR 7a, `setup/07a-devcontainer`)

## What is in the image

- Base: `python:3.12-slim-bookworm`.
- `uv` 0.13.7, copied from the official uv image.
- Node.js 22.17.0 and npm, copied from the official node image. Only for running third-party
  TypeScript such as dsim (phase 1b); the project itself is Python.
- `just` 1.45.0, from PyPI (`rust-just`).
- git, curl, ca-certificates, `libatomic1` (the node runtime that pyright needs) and OpenJDK 17
  (headless).
- The build context is this folder only. There is no root `.dockerignore`, so the repo is not
  sent to Docker.
- The default working directory is `/home/dev`. `dev-start` passes `-w` with the repo path, so
  `just dev` and `docker exec` land in the repo. There is no `/workspace`.
- No GPU and no Android SDK. Google ships no linux-arm64 build tools, so `just robot` runs in CI.
- User `dev`, uid and gid 1000 by default (`DEV_UID`, `DEV_GID`).
- Git identity placeholder: `ALEA dev container <alea-dev@users.noreply.invalid>`.
- No credential helper and no push credentials. `GIT_ASKPASS=/bin/false`, so `git push` fails.
- The project venv is at `/home/dev/.venv`, a volume named `alea-dev-venv`. It is outside the
  repo, so the host venv and the container venv never clash.
- The uv cache is a volume named `alea-dev-uv-cache`.
- The container runs `sleep infinity`. Commands come in through `docker exec`.

## Files

- `Dockerfile`: the image.
- `devcontainer.json`: for editors that open the folder in a container (VS Code and others).
  `just dev-up` does not read it. Its mounts must match the `dev-start` recipe in `justfile`.
  The `.env` mask and the `.git/info` and `.git/modules` overlays are only in `justfile`. This is
  deliberate. `test_devcontainer_json_overlays` in `tests/test_guard_container.py` pins it.

## Rebuild

`just dev-up` runs `dev-build` every time. The Docker cache makes that cheap when the Dockerfile
did not change. To rebuild now:

```
just dev-build
just dev-down
just dev-up
```

`dev-down` matters. A running container keeps the old image until it is removed.

To rebuild with no cache, run this from the repo root. Replace the `1000` values with your
uid and gid if they differ:

```
docker build --no-cache -t alea-dev:cpu --build-arg UID=1000 --build-arg GID=1000 .devcontainer/cpu
```

## Check the image

```
just dev uv --version
just dev just --version
just dev java -version
just dev node --version
just dev git --version
```

Expected: uv 0.13.7, just 1.45.0, openjdk 17, node v22.17.0.
