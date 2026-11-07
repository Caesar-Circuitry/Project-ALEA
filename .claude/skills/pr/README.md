# .claude/skills/pr

The `/pr` skill. `SKILL.md` ships the current branch as a pull request.

- Runs lint and tests, then the checks that match the changed paths (selftest, docs, robot).
- Commits what is left in small commits, then pushes. The push asks the user first.
- Prints the compare link and a PR body that follows `.github/pull_request_template.md`.

**Roadmap phase:** all
