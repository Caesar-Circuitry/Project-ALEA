# .github

GitHub configuration: CI workflows, Dependabot, CODEOWNERS, PR template.

- `workflows/ci.yml`: on push/PR to main, runs ruff check, ruff format --check, pyright and
  pytest on ubuntu, ubuntu-arm, macOS, Windows and Windows-arm (Python 3.12, uv, GPU extra excluded).
  Pyright runs on ubuntu-latest only. A `robot` job builds `robot/` with Gradle (Temurin 17) when
  `robot/**` changes and is skipped cleanly if `robot/gradlew` does not exist yet. No selftest
  yet (the sim is not ported). No docs job: there is no `mkdocs.yml`; it is deferred to PR 7.
- `workflows/gpu-tests.md`: how GPU tests are run manually on Brev (no GPU runners).
- `ISSUE_TEMPLATE/`: bug and feature forms.
- `dependabot.yml`: weekly updates for GitHub Actions, uv and Gradle (`/robot`) dependencies.
- `pull_request_template.md`: PR checklist.
- `CODEOWNERS`: review ownership.

**Roadmap phase:** all (CI landed in PR 3)
