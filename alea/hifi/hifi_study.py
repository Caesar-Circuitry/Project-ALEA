"""Uses the dsim port (commit 62d2446e2ebdf416548fa1641847289bf47cdf36, genius0412); ALEA glue.

License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim); lives under the hifi licence.

The `fidelity: hifi` study: for each condition, (1) the fast shot kernel runs UNCHANGED
(`alea.sim.study.Study.run`, same seed as a fast study would use, so tries/fired/hits are
identical to the fast result), then (2) its score rate feeds the seeded hive sessions of
`alea.hifi.hive_session`. What is and is not modelled is in that module's docstring.

Output files are labelled and kept apart from fast results: `cond_hifi_XXX.npz` (with a
`fidelity` field and the session columns), `summary_hifi.csv` (a `fidelity` column), and the
default directory `results/study-hifi`.

The `hifi:` block of the study YAML (or `HifiParams.from_config`) carries the open session
parameters. There is no restitution key: restitution is the study's own `bounce` axis, already
read by the fast kernel, and no hive-logic restitution is used.
"""

from dataclasses import dataclass

from alea.hifi.hive_session import SessionParams, run_sessions

FIDELITY_LABEL = "hifi"
DEFAULT_OUT = "results/study-hifi"
LABEL_TEXT = (
    "hifi session model; hive at rest during swing (kernel limit); not measured physics; "
    "n_sessions, shots_per_session, shot_interval_s and retarget_after_tip are open "
    "placeholders, not measured"
)
_KEYS = ("n_sessions", "shots_per_session", "shot_interval_s", "retarget_after_tip")


@dataclass(frozen=True)
class HifiParams:
    session: SessionParams

    @classmethod
    def from_config(cls, block: dict | None) -> "HifiParams":
        """Build from the YAML `hifi:` block; the open parameters must all be given."""
        block = dict(block or {})
        missing = [k for k in _KEYS if k not in block]
        if missing:
            raise ValueError(
                f"fidelity 'hifi' needs these open session parameters in the `hifi:` block: "
                f"{missing} (see alea/hifi/hive_session.py; none has a default)"
            )
        allowed = set(_KEYS) | {"initial_nectar", "alliance"}
        unknown = sorted(set(block) - allowed)
        if unknown:
            raise ValueError(f"unknown hifi key(s) {unknown}; valid keys: {sorted(allowed)}")
        # tick_s is deliberately not a YAML key: it is numerical resolution (dsim's 1/60 s timer
        # step, SessionParams default), not a study knob, so it stays fixed. It is still saved
        # (hive_tick_s) and compared on resume.
        return cls(SessionParams(**block))


def run_condition(study, cond: dict, shots: int, seed: int, batch: int, params: HifiParams):
    """tries, fired, hits (identical to the fast kernel) and the session summary dict."""
    tries, fired, hits = study.run(cond, shots, seed=seed + 1000 * cond["id"], batch=batch)
    n_fired = int(fired.sum())
    p_score = int(hits.sum()) / n_fired if n_fired else 0.0
    sessions = run_sessions(p_score, params.session, [seed, int(cond["id"]), 1])
    sessions["hive_caveat"] = LABEL_TEXT  # label only; rides along in npz and summary_hifi.csv
    return tries, fired, hits, sessions


def params_match(z, params: HifiParams) -> bool:
    """True if a stored cond_hifi file was made with these session parameters (for resuming).

    Compares every SessionParams field, including `tick_s` and `alliance` (stored as
    `hive_tick_s`, `hive_alliance`). A file lacking them (older run) does not match.
    """
    p = params.session
    try:
        return (
            int(z["hive_sessions"]) == p.n_sessions
            and int(z["hive_shots_per_session"]) == p.shots_per_session
            and float(z["hive_shot_interval_s"]) == p.shot_interval_s
            and int(z["hive_retarget_after_tip"]) == int(p.retarget_after_tip)
            and int(z["hive_initial_nectar"]) == p.initial_nectar
            and float(z["hive_tick_s"]) == p.tick_s
            and str(z["hive_alliance"]) == p.alliance
        )
    except KeyError:
        return False
