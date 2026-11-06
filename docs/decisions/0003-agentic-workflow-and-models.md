# 0003: Agentic workflow and model tiers

**Status:** accepted, 2026-11-06

## Context

ALEA is built largely with Claude Code by a student FTC team. Model cost differs by an order of
magnitude between tiers, and the most expensive model (Fable) is rarely needed. The shot physics
must never change by accident, and several agents may work at once.

## Decision

- Work is routed by problem type: Haiku for lookups and boilerplate, Sonnet for routine
  implementation, Opus for physics-adjacent work and review, Fable for complex multi-agent
  orchestration only and only with the user's explicit per-task approval.
- The tiers are enforced where possible: `.claude/agents/*.md` pin `model:` per role; the only
  Fable-pinned agent (`orchestrator`) refuses to run unless the spawn prompt states user approval.
- A `PreToolUse` hook blocks writes to `alea/sim/shotsim.py` and `alea/sim/study.py` unless
  `ALEA_ALLOW_PHYSICS_EDIT=1` is set.
- Parallel agents use one worktree, branch and PR each; edits to `alea/game/` and `conf/` are
  serialized.

Full text: `.claude/AGENTIC_WORKFLOW.md`.

## Consequences

- Most sessions run on Sonnet or Opus; Fable use is visible and deliberate.
- Physics edits are impossible without a conscious bypass plus human review.
- New roles need an agent file; new frozen paths need a hook update.
