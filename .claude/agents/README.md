# .claude/agents (subagent definitions)

One file per agent; the frontmatter sets its model, tools and hooks.

- `auditor.md` (opus): periodic whole-repo audit, read-only, ranked findings.
- `ci-diagnoser.md` (opus): diagnoses a failing GitHub Actions run, read-only.
- `docs-writer.md` (haiku): READMEs, MkDocs pages, decision records, docstrings.
- `explorer.md` (haiku): read-only codebase search.
- `heavy-check-operator.md` (sonnet): runs one heavy check from `repo.json`, read-only.
- `implementer.md` (sonnet): writer for `[careful]` plan items and routine, non-physics code.
- `implementer-fast.md` (haiku): writer for one `[fast]` plan item.
- `lead.md` (sonnet): main session; plans, delegates, verifies, cannot edit.
- `orchestrator.md` (fable): multi-agent, multi-PR work; only with explicit approval.
- `physics-reviewer.md` (judge): read-only safety review of sim, game, hifi, golden and other
  sensitive changes.
- `plan-critic.md` (sonnet): read-only attack on a plan before code is written.
- `planner.md` (judge): turns a task into items by file ownership, tagged `[fast]` or `[careful]`.
- `test-writer.md` (sonnet): writes the tests a plan names; never edits non-test code.
- `verifier.md` (judge): read-only check of a working tree or branch; PASS, FAIL or BLOCKED.

Writers never judge, judges never edit. The three judges run on Opus in the `max` profile and
Sonnet in `pro` (`just profile`). As teammates, agents get `tools`, `model`, `effort` and the
body but not `skills` or `hooks`, so each body names the skills to load, and the test gate is
also registered globally in `settings.json`. Judges carry no `memory` field: it would switch
Write and Edit on for them.

**Roadmap phase:** all (agents landed in PR 2)
