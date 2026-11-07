# .claude/rules

Path-scoped guidance for Claude. A rule file loads only when the files it names are touched.

- `physics.md`: loads for `alea/sim`, `alea/game`, `alea/hifi` and `tests/golden`. Frozen files, self-test bar, constants.
- `cross-platform.md`: loads for Python, `pyproject.toml`, `justfile`, `.github` and `.devcontainer`. Paths, shell use, wheels per platform.

**Roadmap phase:** all
