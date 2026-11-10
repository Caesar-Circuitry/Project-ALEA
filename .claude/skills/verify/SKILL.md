---
name: verify
description: Verify the working tree, or a ref range given as the argument, with the read-only verifier. Prints a table of every check as PASS, FAIL or BLOCKED with quoted evidence.
argument-hint: "[ref range, e.g. main..HEAD] [--opus]"
user-invocable: true
disable-model-invocation: true
context: fork
agent: verifier
background: false
---

Verify the working tree diff. If an argument other than `--opus` is given, verify that ref
range instead: $ARGUMENTS

1. List what changed (`git status --short`, `git diff --stat`, or `git diff --stat <range>`)
   and map the files to units with `.claude/repo.json`.
2. Run your checklist item by item. Fix nothing.
3. Print the verdict and the table.
4. Last line, exactly one of:
   - `SAFETY REVIEW: needed (<sensitive path touched>)` when the diff touches a
     `sensitive_paths` prefix from `.claude/repo.json`. The caller then spawns
     `physics-reviewer` on the same diff; with `--opus` in the arguments it passes
     `model: opus` for that one review.
   - `SAFETY REVIEW: skipped (<why: no sensitive path in the diff>)`.
