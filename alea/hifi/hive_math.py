"""Ported from dsim by genius0412, commit 62d2446e2ebdf416548fa1641847289bf47cdf36.

License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim). Not the license of the rest
of ALEA.

dsim's deterministic sine and cosine (`src/math.ts:65-88`): a Taylor polynomial to x^15 on a
folded range, about 1e-11 maximum error, using only +, -, *, / and rounding so every machine gets
the same bits. `hive.ts` calls them in `spillPoses`. They are ported (rather than replaced by
`math.sin` / `math.cos`) because they are short and the replay then matches dsim exactly; see
`test_trig_replay` in tests/test_hifi_hive_spill.py. Angles are in radians.
"""

import math

_PI = math.pi
_HALF_PI = _PI / 2
_TWO_PI = _PI * 2


def _js_round(x: float) -> float:
    """JavaScript `Math.round`: halves round toward +infinity (Python's round is banker's)."""
    f = math.floor(x)
    return float(f + 1) if x - f >= 0.5 else float(f)


def dsin(x: float) -> float:
    """dsim's deterministic sine (`math.ts:65`)."""
    if not math.isfinite(x):
        return math.nan  # JS: Math.round(+-Infinity) is +-Infinity, so inf - inf = NaN
    x -= _TWO_PI * _js_round(x / _TWO_PI)  # reduce to [-PI, PI]
    if x > _HALF_PI:
        x = _PI - x  # fold to [-PI/2, PI/2] via sin(PI-x) = sin(x)
    elif x < -_HALF_PI:
        x = -_PI - x
    x2 = x * x
    return x * (
        1
        + x2
        * (
            -1 / 6
            + x2
            * (
                1 / 120
                + x2
                * (
                    -1 / 5040
                    + x2
                    * (
                        1 / 362880
                        + x2 * (-1 / 39916800 + x2 * (1 / 6227020800 + x2 * (-1 / 1307674368000)))
                    )
                )
            )
        )
    )


def dcos(x: float) -> float:
    """dsim's deterministic cosine (`math.ts:86`)."""
    return dsin(x + _HALF_PI)
