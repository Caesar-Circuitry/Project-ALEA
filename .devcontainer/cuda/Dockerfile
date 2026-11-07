# ALEA CUDA dev container for Linux x86-64 hosts with an NVIDIA GPU, and Brev instances.
# Mirrors ../cpu/Dockerfile (same user, uv, just, git identity, no credentials) on an NVIDIA
# CUDA base image so Warp and CuPy find the driver libraries. Not used by `just dev-up`.
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/

# uv installs Python 3.12 itself, so the image needs no deadsnakes PPA. `just` comes from PyPI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates libatomic1 openjdk-17-jdk-headless python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir rust-just==1.45.0

ARG UID=1000
ARG GID=1000
RUN groupadd --gid ${GID} dev \
    && useradd --uid ${UID} --gid ${GID} --create-home --shell /bin/bash dev \
    && mkdir -p /home/dev/.venv /home/dev/.cache/uv \
    && chown -R dev:dev /home/dev

ARG GIT_NAME="ALEA dev container"
ARG GIT_EMAIL="alea-dev@users.noreply.invalid"
ENV GIT_AUTHOR_NAME=${GIT_NAME} GIT_AUTHOR_EMAIL=${GIT_EMAIL} \
    GIT_COMMITTER_NAME=${GIT_NAME} GIT_COMMITTER_EMAIL=${GIT_EMAIL} \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false
RUN git config --system --add safe.directory '*' \
    && git config --system credential.helper ""

ENV UV_PROJECT_ENVIRONMENT=/home/dev/.venv \
    UV_LINK_MODE=copy \
    UV_PYTHON=3.12 \
    PYTHONUNBUFFERED=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

USER dev
WORKDIR /home/dev
CMD ["sleep", "infinity"]
