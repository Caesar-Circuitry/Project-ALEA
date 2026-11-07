# .github

GitHub configuration: CI workflows, Dependabot, CODEOWNERS, PR template.

- `workflows/ci.yml`: on push/PR to main, runs ruff check, ruff format --check, pyright and
  pytest on ubuntu, ubuntu-arm, macOS and Windows (Python 3.12, uv, GPU extra excluded).
  Pyright runs on ubuntu-latest only. Pytest includes `tests/test_selftest.py` (CPU golden-shot
  agreement) and `tests/test_frozen_files.py` (SHA-1 pins on the frozen physics files).
  `uv sync --locked` fails CI if `uv.lock` is stale. Every action is pinned to a full commit SHA
  with a version comment; Dependabot bumps them. Only superseded PR runs are cancelled, never
  pushes to `main`. A `robot` job builds `robot/` with Gradle (Temurin 17) when `robot/**`
  changes and is skipped cleanly if `robot/gradlew` does not exist yet. No docs job: there is no
  `mkdocs.yml`; it is deferred to PR 7.
- `workflows/gpu-tests.md`: how GPU tests are run manually on Brev (no GPU runners).
- `ISSUE_TEMPLATE/`: bug and feature forms.
- `dependabot.yml`: weekly updates for GitHub Actions, uv and Gradle (`/robot`) dependencies.
- `pull_request_template.md`: PR checklist.
- `CODEOWNERS`: review ownership.

**Roadmap phase:** all (CI landed in PR 3)
