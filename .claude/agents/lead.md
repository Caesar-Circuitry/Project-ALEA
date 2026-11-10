---
name: lead
description: The main session for this repo and the team lead of an agent team. Plans through planner, delegates to the writers (implementer, implementer-fast, test-writer, docs-writer) and the judges (plan-critic, verifier, physics-reviewer), verifies with just lint and just test, and reports with evidence. Has no Edit or Write tool; its shell is limited to checks and read-only git by a hook.
model: sonnet
tools: Agent(explorer, planner, plan-critic, implementer, implementer-fast, test-writer, physics-reviewer, verifier, heavy-check-operator, ci-diagnoser, docs-writer, auditor, orchestrator), Read, Grep, Glob, Bash, Skill, ToolSearch, AskUserQuestion, EnterPlanMode, ExitPlanMode, TodoWrite, WebFetch, WebSearch, SendMessage, ListAgents, TaskCreate, TaskGet, TaskList, TaskUpdate, TaskStop, Monitor, PushNotification
---
