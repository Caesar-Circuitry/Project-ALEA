"""The CPU kernel must agree with the Java Code Sim on >= 99.9 % of the 10,000 golden shots."""

import numpy as np
import pytest

from alea.sim.selftest import GOLDEN, main
from alea.sim.shotsim import ShotSim


def test_golden_agreement_cpu():
    g = np.load(GOLDEN)
    assert len(g) == 10_000
    sim = ShotSim("cpu")
    got = np.empty(len(g), dtype=int)
    for dia, e in sorted({(r[6], r[7]) for r in g}):
        m = (g[:, 6] == dia) & (g[:, 7] == e)
        got[m] = sim.run(g[m, 0], g[m, 1], g[m, 2], g[m, 3], g[m, 4], g[m, 5], dia / 2, e)
    assert (got == g[:, 8].astype(int)).mean() >= 0.999


@pytest.mark.slow
def test_full_selftest_cpu():
    assert main("cpu")
