# .claude

Claude Code configuration for this repo.

- `AGENTIC_WORKFLOW.md` — which model handles which kind of problem, the standard loop, and the
  rules for running agents in parallel. Read it before spawning subagents.
- `agents/` — subagent definitions. Each file's `model:` frontmatter pins the tier for that role.
- `settings.json` — shared permissions allowlist and the physics-guard hook.
- `hooks/guard_physics.py` — blocks edits to the frozen physics files unless explicitly allowed.

Personal overrides go in `.claude/settings.local.json` (git-ignored by Claude Code).

**Roadmap phase:** all
