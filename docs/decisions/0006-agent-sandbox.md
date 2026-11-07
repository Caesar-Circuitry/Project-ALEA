# 0006: Agent shell sandbox in a dev container

**Status:** accepted, 2026-11-07

## Context

Claude Code subagents run shell commands. Before this decision they ran on the host, with the
user's git identity, SSH keys and `gh` token. A prompt cannot stop a subagent from running
`git push`. Only a rule the client enforces can. The team is a group of students who share this
repo, so a mistake by one agent can reach the shared remote.

The `lead` session must stay on the host. It runs `gh` and `git push` checks and needs the
user's tools. Every other agent (`implementer`, `verifier`, `explorer`, `docs-writer`, and the
rest) does shell work that can run in a container.

Options considered:

- Ask agents not to push. Rejected: a prompt is a guideline, not a control.
- Run everything in a container, the lead too. Rejected: the lead needs host `gh` and push.
- Give agents a restricted git and `gh` on the host. Rejected: the credentials stay in reach.
- Run non-lead shell work in a container with no push credentials, and enforce it with a hook.
  Chosen.

## Decision

- The `lead` stays on the host. Its shell rules are in `.claude/hooks/guard_lead.py`.
- Every other agent runs shell work in the container `alea-dev`, through `just dev <cmd>` or
  `docker exec alea-dev <cmd>`. `.claude/hooks/guard_container.py` (PreToolUse, matcher
  `Edit|Write|MultiEdit|NotebookEdit|Bash|Read|Glob|Grep`) blocks any other Bash command and any
  edit outside the repo. `Read`, `Glob` and `Grep` may reach only the repo and the session
  scratchpad `/tmp/claude-<uid>/`, and the scratchpad is read-only for them. So `~/.ssh` and
  `~/.config/gh` are unreachable through those tools. `WebFetch` is not checked.
- The image is `.devcontainer/cpu/`. It has git, uv, just and JDK 17. It has no GPU and no
  Android SDK.
- The container has no push credentials: no `~/.ssh`, no `~/.config/gh`, no `~/.gitconfig`, no
  `.netrc`, no credential helper. `git push` fails inside by design. The lead pushes and runs
  `gh pr create` on the host, and each asks the user first.
- Only the repo is mounted, at its real host path, so git worktrees (whose `.git` file holds an
  absolute path) resolve. Read-only overlays cover `.git/hooks`, `.git/config`, `.git/info` and
  `.git/modules`. `.env` is masked with `/dev/null`.
- Capabilities are dropped, `no-new-privileges` is set, and pids and memory are limited
  (512 pids, `DEV_MEMORY`, default 6 GB).
- `just dev` checks the overlays before each run. If the host rewrote `.git/config` or `.env`,
  the overlay is gone and `just dev` refuses until the user runs `just dev-down` and
  `just dev-up`.
- `.claude/hooks/subagent_gate.py` runs its checks in the container when it is running, and on
  the host when it is not.
- `ALEA_ALLOW_HOST_AGENT_SHELL=1` disables the guard. It is an emergency bypass, and only the
  user's explicit approval allows it.

## Consequences

Gains:

- The lead can push and open PRs on the host after the user approves (`git push` and
  `gh pr create` are in `permissions.ask`; `guard_lead.py` allows only a non-force push of a
  non-main branch to `origin` and `gh pr create`).
- A non-lead agent cannot push, use `gh`, or read the user's SSH keys or tokens from its shell.
- A non-lead agent cannot read `~/.ssh` or `~/.config/gh` with `Read`, `Glob` or `Grep`. The
  hook enforces this. It is not yet seen live (see the last weakness).
- Hooks and git config that the host runs cannot be planted from inside, because those paths are
  read-only.
- Worktrees work without a second copy of the repo.

Weaknesses, stated plainly:

- **The network is open.** The default `bridge` network allows outbound traffic, which was
  verified. `DEV_NETWORK` only sets the network name. There is no egress firewall. A firewall is
  a later PR. Until then, an agent that reads repo contents can send them out. `WebFetch` is not
  checked by the hook either.
- **The overlays are file-level and can disappear silently.** Many host git commands rewrite
  `.git/config`, and that replaces the file under its overlay. `_dev-check` catches this only for
  `.git/config` and `.env`. Other overlays are not checked.
- **Edits do not go through the container.** Agents edit with the host's file tools. The hook
  limits them to paths inside the repo, but a hook can be bypassed with the environment variable
  above, and the container does not see those edits as a boundary.
- **The guard reads command text.** It accepts one `just dev`, `just dev-status` or
  `docker exec alea-dev` call per Bash command and blocks everything else. It is strict on
  purpose, but it is a parser, not a sandbox.
- **Agents can still do damage in the repo.** Commits, branches, switches and local history
  rewrites are allowed inside the container. The repo is shared through the bind mount, so
  anything an agent writes into the working tree is written on the host too.
- **Credentials can still leak through the repo.** `.git/config` is readable in the container.
  Keep tokens out of remote URLs.
- **Branch creation needs `--no-track`.** `git switch -c x origin/main` prints a config write
  error, because it writes tracking to the read-only `.git/config`. Agents must use
  `git switch -c <name> --no-track origin/main`.
- **Windows is not supported.** `just dev` stops with an error that points to WSL2.
- **Two mount lists must match.** `justfile` (`dev-start`) is what `just dev-up` runs.
  `.devcontainer/cpu/devcontainer.json` is for editors. It has no `.env` mask and no
  `.git/info` or `.git/modules` overlays on purpose, and a test pins that. The two can drift.
- **`just robot` cannot run in the container.** There is no Android SDK. The robot build runs in
  CI or on a host that has the SDK.
- **The image is for CPU only.** The CUDA image is in `.devcontainer/cuda/`.
- **It adds Docker as a requirement.** Every non-lead agent needs a running `alea-dev` container.
- **The guard is not yet proven live.** It has unit tests only (about 85 crafted payloads and
  `tests/test_guard_container.py`). No real subagent has hit it, because the session that built
  it ran outside the repo, so its hooks did not load. Until the "Prove it live" steps in
  `.devcontainer/README.md` pass, do not describe the sandbox as proven.
