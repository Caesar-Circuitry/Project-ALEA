# .claude

Claude Code configuration for this repo. Every session here runs as the `lead` agent, which
coordinates subagents and never edits files itself.

- `ROADMAP.md` — setup PR status, what each PR delivers, the project phases after setup.
- `AGENTIC_WORKFLOW.md` — the model tiers, the standard loop, what is enforced vs requested.
- `settings.json` — default model (Sonnet), `agent: lead`, permission rules (Fable spawns and
  `git push` ask; `.env` is unreadable), and the two guard hooks.
- `agents/` — `lead`, `explorer` (Haiku), `implementer` (Sonnet, finishes green),
  `docs-writer` (Haiku), `physics-reviewer` (Opus), `ci-diagnoser` (Opus, read-only), `orchestrator` (Fable, asks first).
- `hooks/` — `guard_physics.py` (frozen sim files, all agents), `guard_lead.py` (lead's shell is
  checks-only), `subagent_gate.py` (implementer's lint + test gate), `autoformat.py`
  (PostToolUse: ruff on edited `.py` files), `session_start.py` (SessionStart summary).
- `rules/` — path-scoped guidance that loads only when matching files are touched.
- `skills/` — `/pr` and `/physics-change`, user-invoked procedures.

Personal overrides go in `settings.local.json` (git-ignored) or `CLAUDE.local.md` at the root.

Two folders are ignored by tools on purpose: `_incoming/` (the copied source from the old
project: Python, `AimDump.java`, `ShotDump.java`, robot Java; deleted in setup PR 8) and
`.claude/worktrees/` (full copies of the project made for parallel agents; clean up with
`just worktree-prune`). Ruff, pyright, VS Code (Python, Java, search, file watcher; see
`.vscode/settings.json`) and git skip them. They stay visible in the explorer.

**Roadmap phase:** all
