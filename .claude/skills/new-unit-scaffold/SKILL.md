---
name: new-unit-scaffold
description: Load when creating a new package or folder in this repo. The files a new unit needs, what each must contain, the nearest unit to copy, and the tables to extend.
user-invocable: false
---

# Scaffold a new unit

A unit is a subpackage `alea/<name>/` with its tests. Copy the nearest existing one:
`alea/matchsim/` for a simulation or analysis package with a CLI, `alea/data/` for anything
that stores or imports data, `alea/web/pages/` for a new page.

## Files, one plan item each

| File | Must contain |
|---|---|
| `alea/<name>/__init__.py` | a one-line docstring; public names only |
| `alea/<name>/README.md` | what goes here, how to run it, and the line `**Roadmap phase:** <n>` |
| `alea/<name>/<module>.py` | the code; units in names; game values imported from `alea.game` |
| `alea/<name>/__main__.py` + `cli.py` | only if it has a command: `python -m alea.<name>`, `main(argv) -> int` |
| `tests/test_<name>_<topic>.py` | tests named in the plan; fixtures in the file; see `unit-tests` |
| `docs/decisions/NNNN-<slug>.md` | Context, Decision, Consequences, when the unit is a design choice |

## Then extend (one `docs:` item)

- `.claude/repo.json`: add the unit to `units` with `prefixes`
  (`alea/<name>/`, `tests/test_<name>`), `test` (`uv run pytest -q -k test_<name>`) and `lint`.
- `alea/README.md` folder list, the root `README.md` folder map, `.claude/ROADMAP.md` row.
- `mkdocs.yml` nav and `docs/decisions/README.md` index when a decision record was added.
- `pyproject.toml`: a new dependency goes in the right extra with platform markers, then
  `uv lock` (the user approves lock changes); never edit `uv.lock` by hand.
- `.github/CODEOWNERS` only when the unit is physics-sensitive.

## CI

No workflow change is needed: `.github/workflows/ci.yml` runs ruff, pyright and pytest over the
whole repo on four platforms. A unit with its own toolchain (as `robot/` has) copies the
`changes` + `robot` job pair with the path filter swapped; that edit is `[careful]`.

Not for a new folder outside `alea/` without the user's say: the top-level layout is fixed by
decision 0001.
