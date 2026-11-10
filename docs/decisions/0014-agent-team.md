# 0014: Agent team, test gates and one config file

**Status:** proposed, 2026-11-09

## Context

Decision 0003 set up a coordinate-only lead with one writer (`implementer`) and kept agent teams
off because they are experimental and cost several times a single session. Since then the repo
grew to eight packages and about 690 tests. Three things slowed work down: one writer at a time,
plans that were not checked before code was written, and a test gate that only one agent
carried. Project specifics (commands, paths) were also repeated in agent files and hooks.

## Decision

- **Writers never judge, judges never edit.** Writers: `implementer` (`[careful]` items),
  `implementer-fast` (`[fast]` items, Haiku), `test-writer`, `docs-writer`. Judges: `planner`,
  `plan-critic`, `verifier`, `physics-reviewer` (the safety reviewer), `heavy-check-operator`.
  Judges have no Edit or Write tool and no `memory` field.
- **Tests are the default proof.** `test_gate.py` stops a writer, a team task or a writer
  teammate while lint or the unit's tests fail. `guard_tests.py` and `guard_bash.py` stop tests
  from being removed, skipped or deselected. Heavy checks (robot build, GPU tests, study smoke
  run, Java comparison) run only through `/heavy`.
- **One config file.** `.claude/repo.json` holds units and their test commands, protected,
  append-only and sensitive paths, forbidden commands, heavy checks, open areas, the profile
  and every assumption. Hooks, agents and skills read it.
- **Agent teams are on, behind a threshold.** `/feature` forms a team only when a plan has at
  least `team_threshold` independent items, with at most `team_cap` teammates on disjoint
  files. Below that it uses plain subagents, as before.
- **Two profiles.** `just profile max|pro` switches the three judges between Opus and Sonnet
  and sets the cap, the threshold and when `plan-critic` runs.
- Hooks stay Python with the standard library only, as the cross-platform rule asks.

This replaces the "agent teams stay off" line of 0003. Everything else in 0003 and 0006 stands:
the lead still cannot edit, non-lead shells still run in `alea-dev`, Fable still asks first.

## Consequences

- A `/feature` run costs more than a single implementer; the threshold and the `pro` profile
  are the controls. Set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` to `"0"` to go back.
- `verifier` moves from Sonnet to Opus on the `max` profile.
- Teammates do not get an agent file's `skills` or `hooks`, so bodies name the skills to load
  and the gate is registered globally. `/resume` does not restore teammates.
- The Task tools are not on by default for newer models; `settings.json` sets
  `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`. Without them the team coordinates by messages and the
  `SubagentStop` and `TeammateIdle` gates still apply.
- A new package adds one entry to `units` in `repo.json` (`/new-unit` plans it).
- New roles need an agent file, an entry in the lead's allowlist and in `tests/test_claude_config.py`.
