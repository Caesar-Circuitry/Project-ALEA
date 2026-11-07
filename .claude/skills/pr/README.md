# .claude/skills/pr

The `/pr` skill. `SKILL.md` ships the current branch as a pull request. It runs in the lead's
own context, not in a fork.

- A delegated `implementer` runs lint and tests plus the checks that match the changed paths
  (selftest, docs, robot) in the container, then commits what is left in small commits.
- The lead verifies the result, then on the host runs `git push origin <branch>` (no `-u`, see decision 0006) and
  `gh pr create`. Both ask the user, because the container has no credentials (decision 0006).
- The PR body follows `.github/pull_request_template.md` and is written to a scratchpad file.
  An existing PR for the branch is not duplicated: the new commits are pushed and its URL is
  printed. The URL is also sent as a push notification.

**Roadmap phase:** all
