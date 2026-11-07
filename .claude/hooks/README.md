# .claude/hooks

Python scripts that Claude Code runs before or after tool calls, and at session start or stop.
They use only the standard library and run with `uv run --no-project python`.

- `guard_physics.py` (PreToolUse, all agents): blocks edits to the frozen files
  `alea/sim/shotsim.py` and `alea/sim/study.py`. It also blocks Bash commands that write them,
  including through interpreters (`python`, `perl`, and others), `perl -i`, `sed -i`, `mv`, `cp`,
  `rm`, redirects, and `git checkout` or `git restore`. Set `ALEA_ALLOW_PHYSICS_EDIT=1` only
  with the user's approval (see `/physics-change`).
- `guard_lead.py` (PreToolUse, lead only): keeps the `lead` agent read-only. Only checks and
  read-only git and shell commands run. It also blocks reads of `.env`, `*.pem` and `*.key`
  files through the shell.
- `subagent_gate.py` (Stop, implementer only): runs `ruff check`, `ruff format --check` and
  pytest. The implementer cannot finish while they fail. It gives up after three blocks.
- `autoformat.py` (PostToolUse): runs `ruff format` and `ruff check --fix` on an edited `.py` file.
  It skips the frozen files.
- `session_start.py` (SessionStart): prints a short status: branch, `.venv`, golden data and the next roadmap row.

Both guards fail closed. If the hook cannot read its input, it blocks the call. Tests are in
`tests/test_guard_hook.py`, `tests/test_autoformat_hook.py` and `tests/test_session_start_hook.py`.

**Roadmap phase:** all
