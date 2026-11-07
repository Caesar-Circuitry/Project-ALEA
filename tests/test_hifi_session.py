"""The hive session model, the hifi labelling and that fast results are unchanged."""

import numpy as np
import pytest

from alea.hifi.hifi_study import HifiParams, params_match, run_condition
from alea.hifi.hive_session import SessionParams, run_session, run_sessions
from alea.sim import results, run_study
from alea.sim.conditions import all_conditions


def _params(**kw):
    base = dict(n_sessions=20, shots_per_session=12, shot_interval_s=2.0, retarget_after_tip=True)
    return SessionParams(**{**base, **kw})


def test_open_parameters_have_no_default():
    with pytest.raises(TypeError):
        SessionParams(n_sessions=1, shots_per_session=1)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="retarget_after_tip"):
        HifiParams.from_config({"n_sessions": 1, "shots_per_session": 1, "shot_interval_s": 1})
    with pytest.raises(ValueError, match="unknown"):
        HifiParams.from_config(
            dict(
                n_sessions=1,
                shots_per_session=1,
                shot_interval_s=1,
                retarget_after_tip=True,
                restitution=0.5,
            )
        )


def test_perfect_shooter_tips_after_third_pollen():
    # 3 staged nectar + 3 pollen tips; the third pollen is offered at shot 3
    r = run_session(1.0, _params(shots_per_session=3), np.random.default_rng(0))
    assert r.captured == 3 and r.rejected == 0
    assert r.tips == 1
    assert r.spilled == 6  # 3 nectar + 3 pollen spill at the release
    assert len(r.spill_poses) == 6
    assert r.first_swing_start_s is not None and r.first_tip_done_s is not None
    assert r.first_tip_done_s - r.first_swing_start_s == pytest.approx(4.0, abs=0.05)


def test_never_scoring_never_tips():
    s = run_sessions(0.0, _params(), [1, 2, 3])
    assert s["hive_tips_mean"] == 0 and s["hive_p_tip"] == 0
    assert np.isnan(s["hive_first_tip_done_s_mean"])


def test_deterministic_and_seeded():
    a = run_sessions(0.6, _params(), [5, 0, 1])
    b = run_sessions(0.6, _params(), [5, 0, 1])
    assert a.keys() == b.keys()
    for k in a:
        assert a[k] == b[k] or (np.isnan(a[k]) and np.isnan(b[k]))
    c = run_sessions(0.6, _params(), [6, 0, 1])
    assert any(a[k] != c[k] for k in a if not np.isnan(a[k]))


def test_retarget_is_an_explicit_choice_that_matters():
    kw = dict(n_sessions=30, shots_per_session=40, shot_interval_s=1.0)
    keep = run_sessions(1.0, _params(retarget_after_tip=False, **kw), [1])
    follow = run_sessions(1.0, _params(retarget_after_tip=True, **kw), [1])
    assert keep["hive_rejected_mean"] > follow["hive_rejected_mean"]


def test_labelling_and_separation(tmp_path):
    cfg = tmp_path / "c.yaml"
    out = tmp_path / "out"
    cfg.write_text(
        "fidelity: hifi\nshots: 2000\nseed: 7\n"
        "hifi: {n_sessions: 5, shots_per_session: 8, shot_interval_s: 2.0,"
        " retarget_after_tip: true}\n"
        "conditions: {aim_deg: [1.0], speed_pct: [2.0], robot_ips: [0.0], ball_in: [2.8],"
        " bounce: [0.45]}\n",
        encoding="utf-8",
    )
    argv = ["--config", str(cfg), "--out", str(out), "--device", "cpu", "--skip-selftest"]
    run_study.main(argv)
    assert (out / "cond_hifi_000.npz").exists() and (out / "summary_hifi.csv").exists()
    assert not (out / "cond_000.npz").exists() and not (out / "summary.csv").exists()
    with np.load(out / "cond_hifi_000.npz") as z:
        assert str(z["fidelity"]) == "hifi"
    rows = results.load_summary(out)
    assert rows[0]["fidelity"] == "hifi" and "hive_tips_mean" in rows[0]
    assert results.detect_fidelity(out) == "hifi"

    run_study.main(argv)  # resume with the same parameters
    with pytest.raises(SystemExit, match="holds hifi"):
        run_study.main([*argv, "--fidelity", "fast"])
    fast_dir = tmp_path / "fast"
    fast_dir.mkdir()
    np.savez_compressed(fast_dir / "cond_000.npz", x=1)
    with pytest.raises(SystemExit, match="holds fast"):
        run_study.main(["--config", str(cfg), "--out", str(fast_dir), "--skip-selftest"])


def test_fast_results_unchanged_by_hifi_wiring():
    """hifi's tries/fired/hits equal the plain Study.run result for the same seed."""
    from alea.sim.study import Study

    st = Study("cpu")
    cond = all_conditions()[0]
    plain = st.run(cond, 3000, seed=11 + 1000 * cond["id"], batch=1000)
    hp = HifiParams(_params())
    tries, fired, hits, sess = run_condition(st, cond, 3000, 11, 1000, hp)
    for a, b in zip(plain[:3], (tries, fired, hits), strict=True):
        assert np.array_equal(a, b)
    assert sess["hive_p_score_input"] == pytest.approx(int(hits.sum()) / int(fired.sum()))
    assert params_match(sess, hp)


def test_interval_must_be_whole_ticks():
    with pytest.raises(ValueError, match="whole number of ticks"):
        _params(shot_interval_s=0.0123)
    assert _params(shot_interval_s=3.0).shot_interval_s == 3.0


def _suptitle(monkeypatch, out):
    import matplotlib.figure

    from alea.sim import plots

    seen = []
    orig = matplotlib.figure.Figure.suptitle

    def spy(self, t, *a, **k):
        seen.append(t)
        return orig(self, t, *a, **k)

    monkeypatch.setattr(matplotlib.figure.Figure, "suptitle", spy)
    plots.main(out)
    return seen[0]


def test_plot_suptitle_fast_and_hifi(tmp_path, monkeypatch):
    grid = dict(aim_deg=[1.0], speed_pct=[2.0], robot_ips=[0.0], ball_in=[2.8], bounce=[0.45])
    cond = all_conditions(grid)[0]
    fast, hifi = tmp_path / "fast", tmp_path / "hifi"
    fast.mkdir()
    hifi.mkdir()
    arr = np.full((2, 2), 40, dtype=np.int64)
    for out, fid in ((fast, "fast"), (hifi, "hifi")):
        extra = (
            {"fidelity": "hifi", "hive_caveat": "x", "hive_sessions": 1} if fid == "hifi" else {}
        )
        np.savez_compressed(
            results.cond_path(out, 0, fid),
            tries=arr + 5,
            fired=arr,
            hits=arr // 2,
            shots=1,
            seed=1,
            **extra,
            **cond,
        )
    base = "Effect of each variable (averaged over all the others)"
    assert _suptitle(monkeypatch, fast) == base  # exactly the origin/main text
    assert _suptitle(monkeypatch, hifi) == "[hifi] " + base
