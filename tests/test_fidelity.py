"""The fidelity switch: fast and hifi both validate; hifi needs its open parameters."""

import pytest

from alea.hifi import DSIM_VERSION, check_fidelity
from alea.sim import run_study


def test_fast_ok():
    assert check_fidelity("fast") == "fast"
    assert DSIM_VERSION


def test_hifi_ok():
    assert check_fidelity("hifi") == "hifi"


def test_unknown_rejected():
    with pytest.raises(ValueError):
        check_fidelity("ultra")


def test_run_study_hifi_needs_open_parameters(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("fidelity: hifi\n", encoding="utf-8")
    with pytest.raises(ValueError, match="shot_interval_s"):
        run_study.main(["--config", str(cfg), "--plan"])
