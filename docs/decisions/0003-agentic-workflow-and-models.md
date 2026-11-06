# 0003: Agentic workflow and model tiers

**Status:** accepted, 2026-11-06

## Context

ALEA is built largely with Claude Code by a student FTC team. Model cost differs by an order of
magnitude between tiers, and the most expensive model (Fable) is rarely needed. The shot physics
must never change by accident, and several agents may work at once. The Claude Code docs draw a
line between instructions Claude may weigh (`CLAUDE.md`, prompts) and rules Claude Code applies
every time (tool lists, hooks, permission rules); the rules that cannot bend belong in the
second group.

## Decision

- **The main session coordinates and never edits.** `.claude/settings.json` sets
  `"agent": "lead"`. The `lead` agent definition carries no Edit or Write tool and an allowlist
  of the subagents it may spawn. A hook limits its shell to checks and read-only git.
- **Sonnet is the project default** (`"model": "sonnet"`, and `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`
  for unlabeled spawns). Haiku for `explorer` and `docs-writer`, Opus for `physics-reviewer`,
  Fable only for `orchestrator`.
- **Fable is gated by a permission prompt**: `permissions.ask` on `Agent(orchestrator)` and
  `Agent(model:fable)`. The user sees and answers every spawn.
- **Frozen physics files** (`alea/sim/shotsim.py`, `alea/sim/study.py`) are protected by a
  PreToolUse hook that applies to every agent. Bypass needs `ALEA_ALLOW_PHYSICS_EDIT=1` in the
  user's local settings plus the `/physics-change` procedure.
- **An implementer finishes green**: its Stop hook re-runs `ruff check`, `ruff format --check`
  and `pytest` and refuses up to three stops while they fail.
- **Procedures live in skills** (`/pr`, `/physics-change`), path-specific guidance in
  `.claude/rules/`, and `CLAUDE.md` stays under 100 lines.
- **No MCP servers.** GitHub goes through the `gh` CLI; nothing else external is in scope.

Full text: `.claude/AGENTIC_WORKFLOW.md`.

## Consequences

- Every code change passes through a subagent with a pinned model, so cost and blast radius are
  visible per spawn in `/usage`.
- A session started with `claude --agent implementer` opts out of the lead restrictions on
  purpose; the physics hook still applies.
- New roles need an agent file and an entry in the lead's allowlist; new frozen paths need a hook
  update and a test in `tests/test_guard_hook.py`.
