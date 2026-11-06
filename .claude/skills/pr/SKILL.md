---
name: pr
description: Open a pull request for the current branch. Runs the checks, commits what is left, pushes (asks first) and prints the compare link with the PR template filled in.
disable-model-invocation: true
context: fork
agent: implementer
background: false
---

Ship the current branch as a pull request. Work in this order and stop at the first failure.

1. `git branch --show-current`. If it is `main`, stop: ask the user for a branch name.
2. `git status --porcelain`. Note what is uncommitted.
3. `just lint` and `just test`. If anything under `alea/sim/` or `alea/game/` changed on this
   branch (`git diff --name-only main...HEAD`), also `just selftest`. If `docs/` or `mkdocs.yml`
   changed, `just docs`. If `robot/` changed, `just robot` (skip with a note if no JDK 17).
4. Commit what is left in small logical commits. Messages: imperative first line under 72
   characters, a blank line, then why. End with the attribution line the repo uses.
5. `git push -u origin <branch>`. This prompts the user; that is expected.
6. Print:
   - the compare link `https://github.com/Caesar-Circuitry/Project-ALEA/compare/<branch>?expand=1`
   - a PR body following `.github/pull_request_template.md` if it exists, otherwise these
     headings: What changed / How it was tested (paste the command output) /
     Self-test passed? / Changes physics? (if yes: explanation and Java comparison attached).
