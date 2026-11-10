---
name: new-unit
description: Add a new package or folder to the repo with the agent team: confirms the name, plans it from the scaffold, then runs the same flow as /feature.
argument-hint: "<name> <owner or roadmap phase>"
user-invocable: true
disable-model-invocation: true
---

Add a new unit: $ARGUMENTS (first word is the name, the rest is the owner or roadmap phase).

1. Check the name against the rulebook: lowercase, where it lives, which roadmap phase fills
   it (`.claude/ROADMAP.md`). Confirm name, location and phase with the user with
   AskUserQuestion before anything is planned.
2. Spawn `planner` with the instruction to load the `new-unit-scaffold` skill and to produce
   one item per file of the scaffold. Items are mostly `[fast]`; anything with logic is
   `[careful]`. The plan must add the unit to `units` in `.claude/repo.json` with its prefixes
   and test command, and extend the doc tables the scaffold names.
3. Continue exactly as `/feature` from its step 1 (plan-critic, approval) to its step 7, with
   the same profile settings from `.claude/repo.json`.
