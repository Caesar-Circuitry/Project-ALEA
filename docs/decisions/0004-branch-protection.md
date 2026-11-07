# 0004: Branch protection on main

**Status:** accepted, 2026-11-06

## Context

Several agents and students push branches at once, and `main` must always pass lint, format,
types and tests on every supported platform. The project supports five targets (see
`[tool.uv].required-environments`), so a change that passes on Linux can still break on
Windows or ARM.

## Decision

`main` is protected:

- Changes arrive by pull request only; no direct pushes, no force pushes, no deletion.
- Branches must be up to date with `main` before merging.
- Required status checks are the CI matrix jobs, one per target:
  - `check (ubuntu-latest)`
  - `check (ubuntu-24.04-arm)`
  - `check (macos-latest)`
  - `check (windows-latest)`
  - `check (windows-11-arm)`
- The `robot` job is not required, because it runs only when `robot/**` changes and a skipped
  required check blocks merging. Reviewers confirm it is green on robot PRs.
- `.github/CODEOWNERS` review is required.
- Pyright runs on `ubuntu-latest` only; the other jobs do not run it.

## Consequences

- A red check on any of the five platforms blocks the merge.
- Renaming a matrix entry changes a check name and requires updating the protection rule.
- Adding a `docs` job (PR 7) means deciding whether to add it to the required list.
