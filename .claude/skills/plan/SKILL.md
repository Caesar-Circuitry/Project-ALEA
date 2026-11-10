---
name: plan
description: Plan a change without writing code. Prints numbered items partitioned by file ownership, each tagged [fast] or [careful], with the tests to add.
argument-hint: "[what to change]"
user-invocable: true
disable-model-invocation: true
context: fork
agent: planner
background: false
---

Plan this change and print the plan in your output format. Edit nothing.

$ARGUMENTS
