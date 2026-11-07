"""The fidelity switch: fast works, hifi is a stub."""

import pytest

from alea.hifi import DSIM_VERSION, check_fidelity
from alea.sim import run_study


def test_fast_ok():
    assert check_fidelity("fast") == "fast"
    assert DSIM_VERSION


def test_hifi_not_implemented():
    with pytest.raises(NotImplementedError, match="0005"):
        check_fidelity("hifi")


def test_unknown_rejected():
    with pytest.raises(ValueError):
        check_fidelity("ultra")


def test_run_study_hifi_raises():
    with pytest.raises(NotImplementedError, match="0005"):
        run_study.main(["--fidelity", "hifi", "--plan"])
