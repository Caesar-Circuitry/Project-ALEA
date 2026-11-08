"""Tests for the generic strategy optimiser in alea.matchsim.search."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from alea.matchsim.search import (
    ParamSpace,
    ParamSpec,
    SearchResult,
    cross_entropy_method,
    grid_search,
    local_refine,
    plot_history,
    random_search,
)

SPACE = ParamSpace(
    [
        ParamSpec("x", "float", low=-5.0, high=5.0),
        ParamSpec("n", "int", low=0, high=10),
        ParamSpec("mode", "choice", choices=("a", "b", "c")),
    ]
)
OPT = {"x": 1.5, "n": 7, "mode": "b"}


def noisy_quadratic(params: dict, seed: int) -> float:
    noise = np.random.default_rng(seed).normal(0.0, 0.3)
    bonus = 0.0 if params["mode"] == "b" else -3.0
    return -((params["x"] - 1.5) ** 2) - 0.3 * (params["n"] - 7) ** 2 + bonus + noise


def _cem(seed: int = 1):
    return cross_entropy_method(SPACE, noisy_quadratic, 30, 0.2, 8, 8, seed)


def test_cem_finds_optimum():
    r = _cem()
    assert abs(r.best_params["x"] - OPT["x"]) < 0.5
    assert abs(r.best_params["n"] - OPT["n"]) <= 1
    assert r.best_params["mode"] == "b"
    assert r.best_se > 0


def test_random_search_finds_optimum():
    r = random_search(SPACE, noisy_quadratic, 600, 4, 3)
    assert abs(r.best_params["x"] - OPT["x"]) < 1.0
    assert abs(r.best_params["n"] - OPT["n"]) <= 1
    assert r.best_params["mode"] == "b"


def test_grid_and_local_refine():
    g = grid_search(SPACE, noisy_quadratic, 5, 4, 2)
    assert len(g.history) == 5 * 5 * 3 or len(g.history) <= 75
    assert g.best_params["mode"] == "b"
    r = local_refine(SPACE, noisy_quadratic, g.best_params, 8, 2, iterations=12)
    assert r.best_mean >= -1.0
    assert abs(r.best_params["x"] - 1.5) < 0.5


def test_same_seed_bit_identical_and_different_seed_differs():
    a, b, c = _cem(5), _cem(5), _cem(6)
    assert [e.params for e in a.history] == [e.params for e in b.history]
    assert [e.mean for e in a.history] == [e.mean for e in b.history]
    assert [e.seeds for e in a.history] == [e.seeds for e in b.history]
    assert [e.params for e in a.history] != [e.params for e in c.history]


def test_common_random_numbers():
    seen: dict[int, list[int]] = {}
    calls: list[tuple[dict, int]] = []

    def obj(p: dict, seed: int) -> float:
        calls.append((p, seed))
        return noisy_quadratic(p, seed)

    r = cross_entropy_method(SPACE, obj, 10, 0.3, 4, 5, 9)
    for e in r.history:
        seen.setdefault(e.generation, [])
        assert len(e.seeds) == 5
        if seen[e.generation]:
            assert e.seeds == seen[e.generation]
        seen[e.generation] = e.seeds
    assert len(seen) == 4
    assert len({tuple(s) for s in seen.values()}) == 4  # fresh seeds per generation
    # the objective really received those seeds
    assert [s for _, s in calls[:5]] == r.history[0].seeds


def test_json_round_trip(tmp_path: Path):
    r = _cem(2)
    p = tmp_path / "sub" / "r.json"
    r.to_json(p)
    back = SearchResult.from_json(p)
    assert back == r


def test_clip_and_vectors():
    out = SPACE.clip({"x": 99.0, "n": -4, "mode": "c"})
    assert out == {"x": 5.0, "n": 0, "mode": "c"}
    logspace = ParamSpace([ParamSpec("k", "float", low=0.01, high=100.0, log=True)])
    for p in logspace.sample(np.random.default_rng(0), 50):
        assert 0.01 <= p["k"] <= 100.0
    p = {"k": 1.0}
    assert np.allclose(logspace.to_vector(p), 0.0)
    assert abs(logspace.from_vector(logspace.to_vector(p))["k"] - 1.0) < 1e-12
    v = SPACE.from_vector([50.0, 3.6, 1.2])
    assert v == {"x": 5.0, "n": 4, "mode": "b"}
    for q in SPACE.sample(np.random.default_rng(1), 20):
        assert SPACE.from_vector(SPACE.to_vector(q)) == q


def test_top_k_ordering():
    r = random_search(SPACE, noisy_quadratic, 20, 2, 4)
    top = r.top_k(5)
    means = [e.mean for e in top]
    assert means == sorted(means, reverse=True)
    assert top[0].mean == r.best_mean
    assert len(r.top_k(100)) == 20


def test_plot_writes_png(tmp_path: Path):
    out = tmp_path / "h.png"
    plot_history(_cem(3), out)
    assert out.stat().st_size > 0
    assert out.read_bytes()[:4] == b"\x89PNG"
