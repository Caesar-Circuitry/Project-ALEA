# 0004: Branch protection on main

**Status:** accepted, 2026-11-06

**Amended 2026-11-07:** the ruleset now matches the list below, plus a bypass for admins (see
Decision). The bypass applies only when merging a pull request.

## Context

Several agents and students push branches at once, and `main` must always pass lint, format,
types and tests on every supported platform. The project supports four targets (see
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
- The `robot` job is not required, because it runs only when `robot/**` changes and a skipped
  required check blocks merging. Reviewers confirm it is green on robot PRs.
- `.github/CODEOWNERS` review is required.
- Pyright runs on `ubuntu-latest` only; the other jobs do not run it.
- Branches must be up to date with `main` (strict status checks) before merging.
- Deleting `main` and force-pushing to it are blocked.
- Repository admins may bypass the rules, with `bypass_mode` set to `pull_request`. The bypass
  works only when merging a pull request. Nobody can push directly to `main`, admins included.

Why the bypass: `CODEOWNERS` lists only `@CohenHill`, who also opens most PRs. GitHub never lets
an author approve their own PR, so without the bypass every physics PR would be blocked.

## Consequences

- A red check on any of the four platforms blocks the merge.
- Renaming a matrix entry changes a check name and requires updating the protection rule.
- Adding a `docs` job (PR 7) means deciding whether to add it to the required list.
- Strict checks mean a PR must be rebased or merged with `main` after each merge to `main`.
- The admin bypass exists only because there is one code owner. Adding a second code owner
  would let the bypass be removed, so that the review rule works without it.
