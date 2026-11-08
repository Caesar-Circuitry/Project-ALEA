"""Generic seeded strategy optimiser (roadmap phase 7).

Nothing here knows about FTC or the match simulator. It maximises a noisy
``objective(params, seed) -> float`` over a mixed float / int / choice space and is fully
reproducible: one master seed fixes every sampled candidate and every evaluation seed.

Plugging in the match simulator (built on a sibling branch)::

    space = ParamSpace([
        ParamSpec("shoot_range_in", "float", low=40.0, high=120.0),
        ParamSpec("cycles_before_park", "int", low=1, high=6),
        ParamSpec("lane", "choice", choices=["left", "centre", "right"]),
    ])
    objective = lambda p, seed: simulate_match(profile_from(p), ..., seed=seed).our_score
    result = cross_entropy_method(space, objective, population=40, elite_frac=0.25,
                                  generations=8, n_eval=16, seed=24331)
    result.to_json(Path("out/search.json"))

Conventions:

* The objective is **maximised**.
* Each candidate in a generation is scored on the same ``n_eval`` seeds (common random
  numbers), so differences between candidates are not swamped by match-to-match luck. Each
  generation draws a fresh seed list from the master seed, which limits over-fitting to one
  set of seeds.
* ``best_*`` is the history entry with the highest mean. Because generations use different
  seeds this carries a mild winner's-curse bias; re-evaluate the winner on new seeds for an
  unbiased number.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

Objective = Callable[[dict, int], float]
Kind = Literal["float", "int", "choice"]

_SEED_MAX = 2**31 - 1


@dataclass(frozen=True)
class ParamSpec:
    """One searchable parameter: a float or int range, or a list of choices."""

    name: str
    kind: Kind
    low: float | None = None
    high: float | None = None
    choices: tuple | None = None
    log: bool = False

    def __post_init__(self) -> None:
        if self.kind == "choice":
            if not self.choices:
                raise ValueError(f"{self.name}: choice needs a non-empty choices list")
            object.__setattr__(self, "choices", tuple(self.choices))
            if self.log:
                raise ValueError(f"{self.name}: log scale does not apply to choices")
            return
        if self.kind not in ("float", "int"):
            raise ValueError(f"{self.name}: unknown kind {self.kind!r}")
        if self.low is None or self.high is None or not self.low <= self.high:
            raise ValueError(f"{self.name}: need low <= high")
        if self.log and self.low <= 0:
            raise ValueError(f"{self.name}: log scale needs low > 0")

    @property
    def opts(self) -> tuple:
        if self.choices is None:
            raise ValueError(f"{self.name}: not a choice parameter")
        return self.choices

    @property
    def lo(self) -> float:
        if self.low is None:
            raise ValueError(f"{self.name}: no bounds")
        return self.low

    @property
    def hi(self) -> float:
        if self.high is None:
            raise ValueError(f"{self.name}: no bounds")
        return self.high

    # transformed-space helpers (float/int only)
    def _fwd(self, x: float) -> float:
        return math.log(x) if self.log else float(x)

    def _inv(self, t: float) -> float:
        return math.exp(t) if self.log else float(t)

    @property
    def t_low(self) -> float:
        return self._fwd(self.lo)

    @property
    def t_high(self) -> float:
        return self._fwd(self.hi)

    def clip(self, value: Any) -> Any:
        if self.kind == "choice":
            if value in self.opts:
                return value
            raise ValueError(f"{self.name}: {value!r} not in {self.opts!r}")
        if self.kind == "int":
            return int(min(max(round(float(value)), math.ceil(self.lo)), math.floor(self.hi)))
        return float(min(max(float(value), self.lo), self.hi))

    def from_t(self, t: float) -> Any:
        """Decode a transformed coordinate (index for choices) into a valid value."""
        if self.kind == "choice":
            return self.opts[int(min(max(round(t), 0), len(self.opts) - 1))]
        return self.clip(self._inv(min(max(t, self.t_low), self.t_high)))

    def to_t(self, value: Any) -> float:
        if self.kind == "choice":
            return float(self.opts.index(value))
        return self._fwd(value)

    def sample(self, rng: np.random.Generator) -> Any:
        if self.kind == "choice":
            return self.opts[int(rng.integers(len(self.opts)))]
        if self.kind == "int":
            return int(rng.integers(math.ceil(self.lo), math.floor(self.hi) + 1))
        return self.clip(self._inv(rng.uniform(self.t_low, self.t_high)))

    def grid(self, points: int) -> list:
        if self.kind == "choice":
            return list(self.opts)
        if points <= 1 or self.lo == self.hi:
            return [self.from_t((self.t_low + self.t_high) / 2)]
        vals = [self.from_t(t) for t in np.linspace(self.t_low, self.t_high, points)]
        return list(dict.fromkeys(vals))  # ints may collapse; keep order

    def to_dict(self) -> dict:
        d = asdict(self)
        d["choices"] = list(self.opts) if self.choices is not None else None
        return d


class ParamSpace:
    """An ordered list of ``ParamSpec``."""

    def __init__(self, specs: Sequence[ParamSpec]) -> None:
        names = [s.name for s in specs]
        if len(set(names)) != len(names):
            raise ValueError("duplicate parameter names")
        self.specs: list[ParamSpec] = list(specs)

    def __len__(self) -> int:
        return len(self.specs)

    def sample(self, rng: np.random.Generator, n: int) -> list[dict]:
        return [{s.name: s.sample(rng) for s in self.specs} for _ in range(n)]

    def clip(self, params: dict) -> dict:
        return {s.name: s.clip(params[s.name]) for s in self.specs}

    def to_vector(self, params: dict) -> np.ndarray:
        """Transformed coordinates (log for log specs, choice index for choices)."""
        return np.array([s.to_t(params[s.name]) for s in self.specs], dtype=float)

    def from_vector(self, vec: Sequence[float] | np.ndarray) -> dict:
        if len(vec) != len(self.specs):
            raise ValueError("vector length does not match space")
        return {s.name: s.from_t(float(t)) for s, t in zip(self.specs, vec, strict=True)}

    def to_list(self) -> list[dict]:
        return [s.to_dict() for s in self.specs]


@dataclass
class Evaluation:
    """One candidate scored on one generation's shared seed list."""

    generation: int
    params: dict
    mean: float
    sd: float
    se: float
    seeds: list[int]


@dataclass
class SearchResult:
    best_params: dict
    best_mean: float
    best_sd: float
    best_se: float
    history: list[Evaluation]
    seed: int
    algorithm: str
    wall_time_s: float
    space: list[dict] = field(default_factory=list)

    def top_k(self, k: int) -> list[Evaluation]:
        """The k best history entries by mean, best first (ties keep history order)."""
        return sorted(self.history, key=lambda e: -e.mean)[:k]

    def to_json(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=1), encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path | str) -> SearchResult:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        d["history"] = [Evaluation(**e) for e in d["history"]]
        return cls(**d)


# --------------------------------------------------------------------------- internals


def _streams(seed: int) -> tuple[np.random.Generator, np.random.Generator]:
    """Independent (candidate sampling, evaluation seeds) generators from one master seed."""
    a, b = np.random.SeedSequence(seed).spawn(2)
    return np.random.default_rng(a), np.random.default_rng(b)


def _eval_seeds(seed_rng: np.random.Generator, n_eval: int) -> list[int]:
    return [int(s) for s in seed_rng.integers(0, _SEED_MAX, size=n_eval)]


def _score(objective: Objective, params: dict, seeds: list[int], generation: int) -> Evaluation:
    vals = np.array([float(objective(dict(params), s)) for s in seeds], dtype=float)
    sd = float(vals.std(ddof=1)) if len(vals) > 1 else 0.0
    return Evaluation(
        generation=generation,
        params=dict(params),
        mean=float(vals.mean()),
        sd=sd,
        se=sd / math.sqrt(len(vals)),
        seeds=list(seeds),
    )


def _finish(
    algorithm: str,
    space: ParamSpace,
    history: list[Evaluation],
    seed: int,
    t0: float,
) -> SearchResult:
    best = max(history, key=lambda e: e.mean)  # first max wins ties
    return SearchResult(
        best_params=dict(best.params),
        best_mean=best.mean,
        best_sd=best.sd,
        best_se=best.se,
        history=history,
        seed=seed,
        algorithm=algorithm,
        wall_time_s=time.perf_counter() - t0,
        space=space.to_list(),
    )


def _check(n_eval: int) -> None:
    if n_eval < 1:
        raise ValueError("n_eval must be >= 1")


# --------------------------------------------------------------------------- algorithms


def random_search(
    space: ParamSpace, objective: Objective, n_candidates: int, n_eval: int, seed: int
) -> SearchResult:
    """Uniform random candidates, all scored on one shared seed list."""
    _check(n_eval)
    t0 = time.perf_counter()
    rng, seed_rng = _streams(seed)
    seeds = _eval_seeds(seed_rng, n_eval)
    history = [_score(objective, p, seeds, 0) for p in space.sample(rng, n_candidates)]
    return _finish("random_search", space, history, seed, t0)


def grid_search(
    space: ParamSpace, objective: Objective, points_per_dim: int, n_eval: int, seed: int
) -> SearchResult:
    """Full factorial grid (choices use every option), one shared seed list."""
    _check(n_eval)
    t0 = time.perf_counter()
    _, seed_rng = _streams(seed)
    seeds = _eval_seeds(seed_rng, n_eval)
    combos: list[dict] = [{}]
    for s in space.specs:
        combos = [{**c, s.name: v} for c in combos for v in s.grid(points_per_dim)]
    history = [_score(objective, p, seeds, 0) for p in combos]
    return _finish("grid_search", space, history, seed, t0)


def cross_entropy_method(
    space: ParamSpace,
    objective: Objective,
    population: int,
    elite_frac: float,
    generations: int,
    n_eval: int,
    seed: int,
    smoothing: float = 0.3,
) -> SearchResult:
    """Cross-entropy method.

    Generation 0 is uniform over the space. After each generation the top ``elite_frac`` are
    used to refit a diagonal Gaussian (in the transformed space) for float/int parameters and
    categorical probabilities for choices. ``smoothing`` in [0, 1) is the weight kept on the
    previous distribution. Every generation draws a fresh shared seed list.
    """
    _check(n_eval)
    if not 0 < elite_frac <= 1:
        raise ValueError("elite_frac must be in (0, 1]")
    if not 0 <= smoothing < 1:
        raise ValueError("smoothing must be in [0, 1)")
    t0 = time.perf_counter()
    rng, seed_rng = _streams(seed)
    n_elite = max(1, round(population * elite_frac))
    specs = space.specs
    num_idx = [i for i, s in enumerate(specs) if s.kind != "choice"]
    cat_idx = [i for i, s in enumerate(specs) if s.kind == "choice"]
    mu = {i: (specs[i].t_low + specs[i].t_high) / 2 for i in num_idx}
    sigma = {i: max((specs[i].t_high - specs[i].t_low) / 2, 1e-12) for i in num_idx}
    floor = {i: 1e-3 * (specs[i].t_high - specs[i].t_low) for i in num_idx}
    probs = {
        i: np.full(len(specs[i].choices or ()), 1.0 / len(specs[i].choices or (0,)))
        for i in cat_idx
    }

    history: list[Evaluation] = []
    for gen in range(generations):
        seeds = _eval_seeds(seed_rng, n_eval)
        if gen == 0:
            cands = space.sample(rng, population)
        else:
            cands = []
            for _ in range(population):
                vec = np.zeros(len(specs))
                for i in num_idx:
                    vec[i] = rng.normal(mu[i], sigma[i])
                for i in cat_idx:
                    vec[i] = rng.choice(len(probs[i]), p=probs[i])
                cands.append(space.from_vector(vec))
        gen_evals = [_score(objective, p, seeds, gen) for p in cands]
        history.extend(gen_evals)
        order = sorted(range(len(gen_evals)), key=lambda j: -gen_evals[j].mean)[:n_elite]
        elite = np.array([space.to_vector(gen_evals[j].params) for j in order])
        for i in num_idx:
            mu[i] = smoothing * mu[i] + (1 - smoothing) * float(elite[:, i].mean())
            sd = float(elite[:, i].std())
            sigma[i] = max(smoothing * sigma[i] + (1 - smoothing) * sd, floor[i])
        for i in cat_idx:
            freq = np.bincount(elite[:, i].astype(int), minlength=len(probs[i])) / len(elite)
            p = smoothing * probs[i] + (1 - smoothing) * freq
            p = np.maximum(p, 1e-3)  # keep every option reachable
            probs[i] = p / p.sum()
    return _finish("cross_entropy_method", space, history, seed, t0)


def local_refine(
    space: ParamSpace,
    objective: Objective,
    start: dict,
    n_eval: int,
    seed: int,
    iterations: int = 10,
    step_frac: float = 0.1,
    shrink: float = 0.5,
) -> SearchResult:
    """Coordinate hill-climb from ``start`` (for example a previous result's best).

    Each iteration perturbs one coordinate at a time (+/- ``step_frac`` of the transformed
    range; ints move at least 1; choices try every other option) and re-scores the incumbent
    and all neighbours on one shared fresh seed list. The best moves in; if the incumbent
    wins, the step shrinks by ``shrink``.
    """
    _check(n_eval)
    t0 = time.perf_counter()
    _, seed_rng = _streams(seed)
    current = space.clip(start)
    step = step_frac
    history: list[Evaluation] = []
    for it in range(iterations):
        seeds = _eval_seeds(seed_rng, n_eval)
        cands = [current]
        base = space.to_vector(current)
        for i, s in enumerate(space.specs):
            if s.kind == "choice":
                cands += [{**current, s.name: c} for c in s.opts if c != current[s.name]]
                continue
            delta = step * (s.t_high - s.t_low)
            for sign in (-1.0, 1.0):
                vec = base.copy()
                vec[i] += sign * delta
                cand = space.from_vector(vec)
                if s.kind == "int" and cand[s.name] == current[s.name]:
                    nudged = int(current[s.name]) + int(sign)
                    cand = {**current, s.name: s.clip(nudged)}
                if cand != current and cand not in cands:
                    cands.append(cand)
        evals = [_score(objective, p, seeds, it) for p in cands]
        history.extend(evals)
        best = max(evals, key=lambda e: e.mean)  # incumbent is first, wins ties
        if best.params == current:
            step *= shrink
        current = dict(best.params)
    return _finish("local_refine", space, history, seed, t0)


# --------------------------------------------------------------------------- plotting


def plot_history(result: SearchResult, path: Path | str) -> None:
    """Write a PNG of per-generation mean score (all candidates, best, and mean +/- se)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gens = sorted({e.generation for e in result.history})
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(
        [e.generation for e in result.history],
        [e.mean for e in result.history],
        s=8,
        alpha=0.4,
        label="candidates",
    )
    best = [max(e.mean for e in result.history if e.generation == g) for g in gens]
    ax.plot(gens, best, color="C1", marker="o", label="best of generation")
    ax.set_xlabel("generation")
    ax.set_ylabel("mean objective")
    ax.set_title(f"{result.algorithm} (seed {result.seed})")
    ax.legend()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(p, dpi=100)
    plt.close(fig)
