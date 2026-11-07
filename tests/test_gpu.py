"""GPU checks. Deselected by default (`-m "not gpu"`); run on a CUDA machine: `just gpu-test`."""

import pytest
import warp as wp

from alea.sim.conditions import all_conditions
from alea.sim.selftest import main
from alea.sim.study import Study

pytestmark = pytest.mark.gpu


@pytest.fixture(scope="module", autouse=True)
def _require_cuda():
    wp.init()
    if wp.get_cuda_device_count() == 0:
        pytest.skip("no CUDA device")


def test_selftest_passes_on_cuda():
    assert main("cuda") is True


def test_small_study_on_cuda():
    _, fired, hits = Study("cuda").run(all_conditions()[0], 10_000, seed=1)  # pyright: ignore[reportAssignmentType]
    assert fired.sum() > 0
    assert hits.sum() <= fired.sum()
