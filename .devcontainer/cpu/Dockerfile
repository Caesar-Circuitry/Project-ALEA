# ALEA CPU dev container: the sandbox every non-lead agent runs its shell work in.
# Multi-arch (linux/arm64 and linux/amd64). No GPU, no Android SDK (Google ships no
# linux-arm64 build tools, so `just robot` stays in CI). No credentials are baked in.
FROM python:3.12-slim-bookworm

# uv from the official image, pinned.
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/

# Node.js 22 LTS with npm, copied from the official image, pinned. It is here to run third-party
# TypeScript (dsim, for the phase 1b validation traces) inside the sandbox; the project itself is
# Python. Same Debian bookworm as the base, so the binary links cleanly on arm64 and amd64.
COPY --from=node:22.17.0-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22.17.0-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# git, curl, a JDK 17 and libatomic1 (the node runtime pyright downloads needs it). build-essential is not needed: every dependency ships a wheel on
# linux arm64 and x86-64. `just` comes from PyPI (rust-just) because bookworm has no package.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates libatomic1 openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir rust-just==1.45.0

# Non-root user; set UID/GID to the host user's so bind-mount files keep the host owner.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid ${GID} dev \
    && useradd --uid ${UID} --gid ${GID} --create-home --shell /bin/bash dev \
    && mkdir -p /home/dev/.venv /home/dev/.cache/uv \
    && chown -R dev:dev /home/dev

# Git identity for commits, with placeholders. There is deliberately no credential helper and
# no remote auth, so `git push` fails here by design; push from the host.
ARG GIT_NAME="ALEA dev container"
ARG GIT_EMAIL="alea-dev@users.noreply.invalid"
ENV GIT_AUTHOR_NAME=${GIT_NAME} GIT_AUTHOR_EMAIL=${GIT_EMAIL} \
    GIT_COMMITTER_NAME=${GIT_NAME} GIT_COMMITTER_EMAIL=${GIT_EMAIL} \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false
# The repo is mounted at its host path (so worktree `.git` files resolve), hence the wildcard.
RUN git config --system --add safe.directory '*' \
    && git config --system credential.helper ""

# The venv lives outside the bind mount so host and container venvs never clash.
ENV UV_PROJECT_ENVIRONMENT=/home/dev/.venv \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# The repo is bind-mounted at its host path and `-w` points there; /home/dev is the fallback.
USER dev
WORKDIR /home/dev
CMD ["sleep", "infinity"]
