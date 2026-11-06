"""Smoke test: the package imports and Warp can run on the CPU device."""

import alea


def test_version() -> None:
    assert alea.__version__


def test_warp_cpu_device() -> None:
    import warp as wp

    wp.init()
    assert wp.get_device("cpu") is not None
