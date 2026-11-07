# .devcontainer

The agent sandbox. Every agent except the lead runs its shell commands in the `alea-dev`
container. The lead stays on the host. Why: `docs/decisions/0006-agent-sandbox.md`.

- `cpu/` is the image in use now (landed in PR 7a). See `cpu/README.md`.
- `cuda/` is the CUDA image for Linux x86-64 and Brev (PR 7, untested). See `cuda/README.md`.

Needs `docker` and `just` on the host. Run these from the repo root.

**Roadmap phase:** 1 (the cpu image landed in PR 7a; cuda/ landed in PR 7)

## Start and stop

```
just dev-up        build the image, start `alea-dev`, run `just sync` inside it
just dev-status    say whether `alea-dev` is running
just dev-down      stop and remove `alea-dev`
```

`just dev-up` is safe to run again. The uv cache and venv volumes survive `dev-down`.
Run `just dev-down` and then `just dev-up` when the mounts change.

The lead runs `dev-up`, `dev-down` and `dev-status` on the host. Other agents may run
`dev-status` only.

## How agents run commands

Put `just dev` in front of the command. The folder stays the same:

```
just dev uv run pytest -q
just dev uv run ruff check .
docker exec alea-dev ls
```

Anything after `dev` goes to the command, flags included: `just dev --set x y` passes `--set`
through.

For `&&`, `;`, `|` or `$VARS`, wrap the whole thing in `bash -c`:

```
just dev bash -c 'uv run ruff check . && uv run pytest -q'
```

The hook `.claude/hooks/guard_container.py` enforces these rules:

- One `just dev`, `just dev-status` or `docker exec alea-dev` call per Bash command.
- Any other host command is blocked. The message says to use `just dev`.
- `Edit`, `Write`, `MultiEdit` and `NotebookEdit` may only touch paths inside the repo.
- `Read`, `Glob` and `Grep` may only reach the repo and the session scratchpad
  `/tmp/claude-<uid>/`. The scratchpad is read-only for them. A `Read` with no path is blocked.
  A `Glob` pattern or `Grep` `glob` that is absolute or starts with `~` or `..` is checked on
  its fixed directory part. A `Grep` regex is not a path, so it is not checked. Paths are
  resolved, so a symlink in the repo that points outside is blocked.
- `WebFetch` is not checked.

Git inside the container:

- Agents can commit, branch and switch.
- `git push` fails. There are no push credentials in the container. The user pushes from the host.
- `gh` is not in the image and has no token. Use it on the host.
- Create a branch with `--no-track`:

```
just dev git switch -c feature/my-branch --no-track origin/main
```

Without `--no-track`, git writes branch tracking to `.git/config`, which is read-only in the
container. The command prints a config write error.

## What is isolated, and what is not

Isolated:

- Push credentials. No `~/.ssh`, no `~/.config/gh`, no `~/.gitconfig`, no `.netrc`, no
  credential helper.
- Host files. Only the repo is mounted, at its real host path, so git worktrees resolve.
- Host files read by `Read`, `Glob` and `Grep` (enforced by the hook, not by the container,
  and not yet seen live; see "Prove it live"). Those tools run on the host, so the hook is the
  only thing that keeps `~/.ssh` out of reach.
- `.git/hooks`, `.git/config`, `.git/info` and `.git/modules` are read-only. A container agent
  cannot plant a hook or change `core.fsmonitor` or `hooksPath` for the host to run later.
- `.env` is masked with `/dev/null`.
- Linux capabilities are all dropped. `no-new-privileges` is set.
- Processes are capped at 512 (`--pids-limit`) and memory at `DEV_MEMORY` (default `6g`).
- Files written into the repo are owned by your host user. The container user is `dev`, uid
  1000 by default. If your host uid differs, set `DEV_UID` and `DEV_GID` before `just dev-up`.

Not isolated:

- Network. The default `bridge` network has open outbound access. `DEV_NETWORK` only names the
  network. There is no firewall yet. A firewall is a later PR. `WebFetch` is not limited either.
- Edits. Agents still edit with the host's file tools. The hook limits them to the repo path.
  The container does not limit them.
- Repo contents. Everything in the repo is readable and writable by agents. That includes
  `.git/config`, so do not put tokens in remote URLs.
- Windows. `just dev` is not supported yet. On Windows it stops with an error that points to
  WSL2. Use WSL2 for agent work.
- Android. The image has no Android SDK. Google ships no linux-arm64 build tools, so
  `just robot` runs in CI. JDK 17 is in the image.

## Prove it live

The guard has unit tests only. No real subagent has hit it yet, because the session that built
it ran outside this repo and the repo's hooks did not load. Until these steps pass, do not
call the sandbox proven.

The lead is the main session, and the guard does not check it. Test with subagents only.

1. Start Claude Code inside the repo, so its hooks load:

   ```
   cd Project-ALEA && claude
   ```

2. Start the container. The lead runs this on the host:

   ```
   just dev-up
   ```

3. Ask a subagent that has Bash (`verifier`) to run `pwd`. Expect a `BLOCKED:` message that
   says to use `just dev`. If `pwd` runs, the hooks did not load. Stop and report that.

4. Run this in a terminal in the repo. Expect the repo path, the same as on the host:

   ```
   just dev pwd
   ```

5. Ask a subagent that has Read but no Bash (`explorer`) to read `~/.ssh/config` with the
   Read tool. Expect `BLOCKED:` and the path. The file does not need to exist, because the
   path is refused before it is opened.

When all five pass, record the result in the PR, then update decision 0006.

## Settings

Set these in your shell or in the environment before `just dev-up`:

| Variable | Default | What it does |
|---|---|---|
| `DEV_NETWORK` | `bridge` | Docker network name |
| `DEV_UID`, `DEV_GID` | `1000`, `1000` | Owner of files written to the repo |
| `DEV_MEMORY` | `6g` | Memory limit for the container |
| `DEV_CWD` | folder you ran `just` in | Folder inside the container for `just dev` |

## Troubleshooting

**`read-only overlay on .git/config is gone (the host rewrote it)`**, or the same for `.env`.

Many host git commands replace `.git/config`. Then the read-only overlay on that file drops
out of the container without a warning. `just dev` checks for this and refuses to run.

Fix it on the host:

```
just dev-down
just dev-up
```

**`alea-dev` is not running.** The hook blocks `just dev` and asks you to start it. Run
`just dev-status`, then `just dev-up`.

**`git push` fails inside the container.** This is by design. Push from the host:

```
git push -u origin feature/my-branch
```

**`git switch -c x origin/main` prints a config write error.** Add `--no-track`. See above.

**`just robot` fails inside the container.** No Android SDK. Let CI build the robot code,
or run `just robot` on the host if you have the Android SDK.

**An agent is blocked and you must let it run on the host.** Set
`ALEA_ALLOW_HOST_AGENT_SHELL=1` for that session. This turns the guard off for every agent.
Use it only with the user's explicit approval, and turn it off again afterwards.
