---
name: pr
description: Open a pull request for the current branch. The implementer runs the checks and commits in the container; the lead then pushes and runs gh pr create on the host (each asks the user) and prints the PR URL.
disable-model-invocation: true
---

Ship the current branch as a pull request. This skill runs in the lead's own context. The
container `alea-dev` has no credentials, so it cannot push or call `gh` (decision 0006): checks
and commits happen there, push and `gh` happen on the host. Stop at the first failure.

1. `git branch --show-current`. If it is `main`, stop and ask the user for a branch name (new
   branches are made inside the container with `git switch -c <name> --no-track`).
   Then `git status --porcelain` and note what is uncommitted.
2. Delegate to the `implementer` subagent (its shell runs in the container via `just dev`):
   - `just lint` and `just test`.
   - `just selftest` if `alea/sim/` or `alea/game/` changed (`git diff --name-only main...HEAD`).
   - `just docs` if `docs/` or `mkdocs.yml` changed. If `mkdocs.yml` does not exist yet, skip it
     and say so.
   - `just robot` if `robot/` changed. Skip with a note if there is no JDK 17 or Android SDK.
   - Then commit what is left in small logical commits. Messages: imperative first line under 72
     characters, a blank line, then why. End with the attribution lines the session's system
     reminder gives; if it gives none, add none.
   - If a check fails, it stops and reports; do not continue.
3. Verify what the container did: `git status` and `git log main..HEAD --stat`. Nothing should
   be changed that the task did not ask for (no stray files, no edits to frozen physics files).
4. Check for an existing PR: `gh pr list --head <branch>`.
   - Exists: run `git push origin <branch>` (asks the user), say that the PR already exists
     and give its URL. Do not create another. Go to step 7.
   - None: continue.
5. On the host, `git push origin <branch>`, with no `-u`: `-u` writes tracking into `.git/config`,
   which makes the container's read-only overlay go stale and `just dev` refuse to run. This asks
   the user; that is expected.
6. Write the PR body to a file in the session scratchpad directory (the path the harness gives,
   not `/tmp`), so no shell quoting is involved. It follows `.github/pull_request_template.md`:
   What and why, Checks, How it was tested (paste the real command output), anything skipped and
   why, known limits. If the branch completes a row in `.claude/ROADMAP.md`, say so in the body
   so the row is set to "merged" after the user merges. Title: imperative, under 70 characters.
   Then run `gh pr create --base main --head <branch> --title "<title>" --body-file <file>`.
   This asks the user.
7. Print the PR URL, then call the PushNotification tool with the one-line message
   `PR ready: <branch> <url>`. It is skipped when the user is at the terminal.
