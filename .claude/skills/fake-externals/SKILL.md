---
name: fake-externals
description: Load when code calls a network service, hardware, a database, a GPU, the clock, a model API or anything random, to make it testable without the real thing.
user-invocable: false
---

# Fake the externals

Put each external call behind one function or one argument, so a test can replace it. The
suite never needs the network, a GPU, a robot or a real match video.

| External | How this repo fakes it | Example |
|---|---|---|
| Database | SQLite file under `tmp_path`, migrated with `upgrade(url)` | `tests/test_data_import.py` |
| Robot logs | Synthetic logs from `alea/data/synthetic.py`; one tiny golden `.rlog` | `tests/make_golden_rlog.py` |
| Match video | Synthetic frames from `alea/video/field/synth.py`; real clips only via the `ALEA_LOCAL_CLIP` env var, skipped when unset | `tests/test_video_field_movers.py` |
| GPU | The Warp `cpu` device; the same kernel must run on both | `tests/test_selftest.py` |
| Java sim / dsim | Saved answers in `tests/golden/` and traces in `tests/hifi_traces/` | `tests/test_hifi_frame.py` |
| Randomness | A fixed seed passed in as an argument; assert on the seeded result | `tests/test_matchsim_search.py` |
| Clock, env vars, API keys | `monkeypatch.setenv` / `monkeypatch.setattr`; never read `.env` in a test | `tests/test_web_app.py` |
| Model or web API | The prompt is built by a pure function (`build_prompt`) that tests check; the call itself sits in one function a test replaces with a stub | `alea/analysis/reflection/prompt.py` |

Rules:

- One method per external call. No call to the network or a subprocess from module import time.
- Assert the failure path too: the timeout, the missing file, the truncated log, the missing
  optional package (`pytest.importorskip`), each with `pytest.raises` or an exit code.
- Never mock the function under test, and never assert only that a mock was called.
- A new fake that others will reuse goes next to the code it fakes (as `synthetic.py` and
  `synth.py` do), not in a test file.
- The first live call to a paid or external service needs the user's go-ahead (roadmap).
