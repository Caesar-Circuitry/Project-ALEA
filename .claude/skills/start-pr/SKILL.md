---
name: start-pr
description: Start the branch for a ROADMAP stage. Takes a stage id such as 4 or 3b, creates the branch from origin/main, syncs the environment and prints the stage's done-when list. Never commits.
disable-model-invocation: true
context: fork
agent: implementer
background: false
---

Start work on one stage of `.claude/ROADMAP.md`. The argument is the stage id (`4`, `3b`, ...).
Work in this order and stop at the first failure. Never commit.

1. `git fetch origin`.
2. Find the stage in `.claude/ROADMAP.md`: its row in the status table and its section under
   "What each PR must deliver". If the id is not there, stop and say so.
3. Derive the branch name from the stage title: lowercase, words joined with hyphens, no
   punctuation. Setup stages (the table's Branch column already has one) use `setup/NN-slug`
   (`NN` is the two-digit id, with its letter suffix if any, e.g. `setup/03b-ci-complete`); later
   phases use `feature/slug`. Prefer the name in the Branch column when it exists.
4. If the branch exists locally (`git branch --list <branch>`) or on origin
   (`git ls-remote --heads origin <branch>`), stop and say so. Do not switch to it.
5. `git switch -c <branch> origin/main`.
6. `just sync`.
7. Print the branch name and the stage's "Done when" list from the roadmap section, verbatim.
   If the section has no such list, print the whole section and say so.
