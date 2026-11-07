# .claude/agents (subagent definitions)

One file per agent; the frontmatter sets its model, tools and hooks.

- `auditor.md` (opus): periodic whole-repo audit, read-only, ranked findings.
- `ci-diagnoser.md` (opus): diagnoses a failing GitHub Actions run, read-only.
- `docs-writer.md` (haiku): READMEs, MkDocs pages, decision records, docstrings.
- `explorer.md` (haiku): read-only codebase search.
- `implementer.md` (sonnet): default agent for routine, non-physics code.
- `lead.md` (sonnet): main session; plans, delegates, verifies, cannot edit.
- `orchestrator.md` (fable): multi-agent, multi-PR work; only with explicit approval.
- `physics-reviewer.md` (opus): read-only review of sim, game, hifi and golden changes.
- `verifier.md` (sonnet): read-only check of a finished branch before `/pr`.

**Roadmap phase:** all (agents landed in PR 2)
