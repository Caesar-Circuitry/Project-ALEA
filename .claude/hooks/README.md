# .claude/hooks

Python scripts that Claude Code runs before or after tool calls, and at session start or stop.
They use only the standard library and run with `uv run --no-project python`.

- `guard_physics.py` (PreToolUse, all agents): blocks edits to the frozen files
  `alea/sim/shotsim.py` and `alea/sim/study.py`. It also blocks Bash commands that write them,
  including through interpreters (`python`, `perl`, and others), `perl -i`, `sed -i`, `mv`, `cp`,
  `rm`, redirects, and `git checkout` or `git restore`. Set `ALEA_ALLOW_PHYSICS_EDIT=1` only
  with the user's approval (see `/physics-change`).
- `guard_container.py` (PreToolUse, every agent except the lead): runs shell work only in the
  dev container. A non-lead agent's Bash must be exactly one `just dev <cmd>`, `just dev-status`
  or `docker exec alea-dev <cmd>`. Anything else is blocked, including `git push` and `gh`. `Edit`,
  `Write`, `MultiEdit` and `NotebookEdit` may only touch paths inside the repo. `Read`, `Glob`
  and `Grep` may touch the repo and the scratchpad `/tmp/claude-<uid>/` (read-only), so
  `~/.ssh` and `~/.config/gh` are unreachable through them. `WebFetch` is not checked. Compound
  commands go inside `bash -c`. The container is `.devcontainer/cpu/`; see
  `.devcontainer/README.md`, including its "Prove it live" steps.
- `guard_lead.py` (PreToolUse, lead only): keeps the `lead` agent read-only. Only checks and
  read-only git and shell commands run. The lead may also run `just dev-up`, `just dev-down` and
  `just dev-status` on the host, but not `just dev <cmd>`. It allows `git push [-u] origin <branch>` (never main/master/HEAD,
  force, delete, mirror, all, tags, a refspec with `:` or `+`, another remote, or global git
  options) and `gh pr create`; `settings.json` makes both ask the user. Other `gh pr` writes
  (merge, edit, close, comment) stay blocked. It also blocks reads of `.env`, `*.pem`
  and `*.key` files through the shell.
- `subagent_gate.py` (Stop, implementer only): runs `ruff check`, `ruff format --check` and
  pytest. The implementer cannot finish while they fail. It gives up after three blocks. When
  `alea-dev` is running, the checks run inside it with `docker exec`. Otherwise they run on the
  host.
- `autoformat.py` (PostToolUse): runs `ruff format` and `ruff check --fix` on an edited `.py` file.
  It skips the frozen files.
- `session_start.py` (SessionStart): prints a short status: branch, `.venv`, golden data and the next roadmap row.

The guards fail closed. If the hook cannot read its input, it blocks the call. Set
`ALEA_ALLOW_HOST_AGENT_SHELL=1` to turn `guard_container.py` off, only with the user's approval.
Tests are in `tests/test_guard_hook.py`, `tests/test_guard_container.py`,
`tests/test_autoformat_hook.py` and `tests/test_session_start_hook.py`.

**Roadmap phase:** all
