---
name: audit
description: Run the read-only auditor over the whole repo. Optional argument is a focus area (practices, security, ai-mistakes, rules); default is all. Prints the report and adds nothing to the repo.
disable-model-invocation: true
context: fork
agent: auditor
background: false
---

Audit the repo. The argument is the focus area: `practices`, `security`, `ai-mistakes` or
`rules`. With no argument, cover all four.

1. Follow the auditor checklist for the chosen area. Edit nothing.
2. Print the full report: findings ranked most severe first, each with severity, verified or
   plausible, `file:line` and a recommendation, then a short "What's healthy" section.
3. Do not write the report to a file. Finish by suggesting that the user may file it with
   `gh issue create --title "Audit <date>" --body-file -` (the user decides; do not run it).
