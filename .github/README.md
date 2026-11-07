# .github

GitHub configuration: CI workflows, Dependabot, CODEOWNERS, PR template.

- `workflows/ci.yml`: on push/PR to main, runs ruff check, ruff format --check, pyright and
  pytest on ubuntu, macOS and Windows (Python 3.12, uv, GPU extra excluded). No selftest yet
  (the sim is not ported). No docs job yet: there is no `mkdocs.yml`; add one with the docs site.
- `dependabot.yml`: weekly updates for GitHub Actions and uv dependencies.
- `pull_request_template.md`: PR checklist.
- `CODEOWNERS`: review ownership.

**Roadmap phase:** all (CI landed in PR 3)
