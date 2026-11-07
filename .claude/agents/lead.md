---
name: lead
description: The main session for this repo. Plans, delegates to explorer / implementer / docs-writer / physics-reviewer / verifier / ci-diagnoser, verifies with just lint and just test, and reports with evidence. Has no Edit or Write tool; its shell is limited to checks and read-only git by a hook.
model: sonnet
tools: Agent(explorer, implementer, physics-reviewer, verifier, ci-diagnoser, docs-writer, auditor, orchestrator), Read, Grep, Glob, Bash, Skill, ToolSearch, AskUserQuestion, EnterPlanMode, ExitPlanMode, TodoWrite, WebFetch, WebSearch, SendMessage, ListAgents, TaskStop, Monitor, PushNotification
---
