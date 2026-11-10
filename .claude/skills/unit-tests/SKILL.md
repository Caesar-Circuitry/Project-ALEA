---
name: unit-tests
description: Default way to prove any change; load before writing or running tests in this repo. Test layout, the patterns the suite already uses, and the exact commands.
user-invocable: false
---

# Unit tests

Tests are the proof. A claim without a test run quoted next to it is not proven.

## Layers (rulebook: "Commands", "Rules Claude follows")

- `tests/test_<unit>_<topic>.py`, flat, one file per topic. No `conftest.py`; fixtures live in
  the test file that uses them. Type-annotate tests `-> None`.
- Default run is CPU only. `@pytest.mark.gpu` tests are deselected by `addopts` and run as a
  heavy check; `@pytest.mark.slow` marks anything over about a minute.
- `tests/golden/` holds saved known answers (Java shot answers, constants snapshot, a sample
  log). Append-only: add a file, never change one, never regenerate `golden_shots.npy`.
- `tests/hifi_traces/` holds recorded dsim traces that the hifi tests replay step by step.

## Patterns to copy

- **Temp database** (`tests/test_data_import.py`): a `session` fixture builds
  `sqlite:///<tmp_path>/test.db`, runs `upgrade(url)`, yields a session, disposes the engine.
- **Golden input**: `ROOT = Path(__file__).resolve().parent.parent`, then read the file under
  `tests/golden/`; assert exact keys and values, and that the file stays tiny.
- **Docs as contract** (`test_contract_keys_match_doc`, `tests/test_robot_contract.py`): parse
  the markdown table or the Java source with `re` and compare sets with the Python constants.
- **Failure paths**: `with pytest.raises(rlog.RlogError):` on a truncated or corrupt input; CLI
  tests call `main([...])` and assert the exit code and `capsys` output.
- **Optional dependency**: `pytest.importorskip("cv2")` at the top of the file. This is the
  only skip the suite uses; never add `skip` or `xfail` to get green.
- **Streamlit pages** (`tests/test_web_app.py`): `AppTest.from_file(str(APP)).run()` with a
  `monkeypatch.setenv` fixture for headless mode; assert `not at.exception`.
- **Hooks** (`tests/test_guard_hook.py`, `tests/test_team_hooks.py`): run the script with
  `subprocess.run([sys.executable, HOOK], input=json.dumps(payload))` and assert the exit code.
- Numbers: `numpy.testing` or `pytest.approx` with an explicit tolerance and the unit in the
  name (`err_in`, `tol_deg`).

## Commands

Subagents prefix every command with `just dev` (the sandbox). The lead runs them bare.

```
just sync                                   first, in a new worktree
<unit "test" command from .claude/repo.json>   while working, e.g. uv run pytest -q -k test_data
just test                                   uv run pytest, the whole CPU suite
just lint                                   ruff check + ruff format --check + pyright
just selftest                               after any change under alea/sim or alea/game
```

Never pass `--deselect`, `--ignore`, `-k "not ..."` or `-p no:`; a hook blocks them.

If the claim cannot be unit-tested (needs a GPU, the robot build, the Java sim or real
footage), say so and hand it to the verifier as BLOCKED. Never start a heavy check from here.
