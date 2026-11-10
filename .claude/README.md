# .claude

Claude Code configuration for this repo. Every session here runs as the `lead` agent, which
coordinates subagents and never edits files itself.

- `ROADMAP.md` — setup PR status, what each PR delivers, the project phases after setup.
- `AGENTIC_WORKFLOW.md` — the model tiers, the standard loop, what is enforced vs requested.
- `repo.json` — the only project-specific file of the agent team: units with their test
  commands, protected and sensitive paths, forbidden commands, heavy checks, open areas, the
  active profile and every assumption. Hooks, agents and skills read it.
- `profile.py` — `just profile max|pro` switches the judges' model, the team cap and threshold.
- `settings.json` — default model (Sonnet), `agent: lead`, agent teams on, permission rules
  (Fable spawns and `git push` ask; `.env` is unreadable), and the hooks.
- `agents/` — `lead`; writers `implementer` (Sonnet), `implementer-fast` (Haiku), `test-writer`
  (Sonnet), `docs-writer` (Haiku); judges `planner`, `verifier`, `physics-reviewer` (Opus or
  Sonnet by profile), `plan-critic` (Sonnet); `explorer` (Haiku), `heavy-check-operator`,
  `ci-diagnoser` (Opus, read-only), `auditor`, `orchestrator` (Fable, asks first).
- `hooks/` — `guard_physics.py` (frozen sim files, all agents), `guard_lead.py` (lead's shell is
  checks-only), `autoformat.py`
  (PostToolUse: ruff on edited `.py` files), `session_start.py` (SessionStart summary),
  `guard_bash.py` and `guard_tests.py` (no forbidden commands, no weakened tests),
  `test_gate.py` (writers finish green), `task_shape.py`, `test_touched.py`, `pre_compact.py`.
- `rules/` — path-scoped guidance that loads only when matching files are touched.
- `skills/` — commands `/feature`, `/plan`, `/verify`, `/new-unit`, `/heavy`, `/pr`,
  `/start-pr`, `/physics-change`, `/audit`; knowledge skills `unit-tests`, `fake-externals`,
  `run-heavy-check`, `new-unit-scaffold` that agents load themselves.

Personal overrides go in `settings.local.json` (git-ignored) or `CLAUDE.local.md` at the root.

Two folders are ignored by tools on purpose: `_incoming/` (the copied source from the old
project: Python, `AimDump.java`, `ShotDump.java`, robot Java; deleted in setup PR 8) and
`.claude/worktrees/` (full copies of the project made for parallel agents; clean up with
`just worktree-prune`). Ruff, pyright, VS Code (Python, Java, search, file watcher; see
`.vscode/settings.json`) and git skip them. They stay visible in the explorer.

**Roadmap phase:** all
