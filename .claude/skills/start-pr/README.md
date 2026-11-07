# .claude/skills/start-pr

The `/start-pr` skill. `SKILL.md` starts the branch for one roadmap stage, such as `4` or `3b`.

- Fetches `origin`, then creates the branch from `origin/main`.
- Runs `just sync` and prints the stage's "Done when" list from `.claude/ROADMAP.md`.
- Never commits.

**Roadmap phase:** all
