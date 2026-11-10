---
name: heavy
description: Run one heavy check from .claude/repo.json (robot-build, gpu-tests, study-smoke, java-compare) and report what was observed. Use only when a unit test cannot prove the claim.
argument-hint: "[check name; default robot-build]"
user-invocable: true
disable-model-invocation: true
context: fork
agent: heavy-check-operator
background: false
---

Run the heavy check named `$ARGUMENTS` from `heavy_checks` in `.claude/repo.json`. With no
name, run the first entry. Follow the `run-heavy-check` skill. Report only; fix nothing.
