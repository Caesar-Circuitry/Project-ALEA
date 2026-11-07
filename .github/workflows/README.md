# .github/workflows

GitHub Actions workflows. GitHub runs only `*.yml` files here.

- `ci.yml`: runs on pushes and pull requests to `main`. Checks on four runners (Ubuntu x86-64 and arm64, macOS, Windows), a `docs` job (`mkdocs build --strict`), plus a `robot` build when `robot/**` changes.
- `pages.yml`: on pushes to `main` only, builds the MkDocs site and deploys it to GitHub Pages. **One-time manual step:** the repo owner must enable Pages under Settings > Pages > Source: GitHub Actions, or the deploy job fails.
- `gpu-tests.md`: not a workflow. It is the manual steps for GPU tests on a Brev instance, because GitHub has no GPU runners.

**Roadmap phase:** all (CI landed in PR 3, finished in PR 3b; docs and Pages in PR 7)
