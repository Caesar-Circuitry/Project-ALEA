# .github/workflows

GitHub Actions workflows. GitHub runs only `*.yml` files here.

- `ci.yml`: runs on pushes and pull requests to `main`. Checks on four runners (Ubuntu x86-64 and arm64, macOS, Windows), plus a `robot` build when `robot/**` changes.
- `gpu-tests.md`: not a workflow. It is the manual steps for GPU tests on a Brev instance, because GitHub has no GPU runners.

**Roadmap phase:** all (CI landed in PR 3, finished in PR 3b)
