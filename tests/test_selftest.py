"""The CPU kernel must agree with the Java Code Sim on >= 99.9 % of the 10,000 golden shots."""

import pytest

from alea.sim.selftest import golden_agreement, main
from alea.sim.shotsim import ShotSim


def test_golden_agreement_cpu():
    agree, n_golden = golden_agreement(ShotSim("cpu"))
    assert n_golden == 10_000
    assert agree >= 0.999


@pytest.mark.slow
def test_full_selftest_cpu():
    assert main("cpu")
