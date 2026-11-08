"""High-fidelity option ported from dsim. PolyForm Noncommercial 1.0.0; see alea/hifi/README.md."""

from pathlib import Path

FIDELITY_CHOICES = ("fast", "hifi")

# Pinned dsim commit; read from the DSIM_VERSION file next to this module.
DSIM_VERSION = (Path(__file__).with_name("DSIM_VERSION")).read_text(encoding="utf-8").strip()


def check_fidelity(fidelity: str) -> str:
    """Validate a fidelity setting: "fast" (Warp shots) or "hifi" (plus the dsim hive logic)."""
    if fidelity not in FIDELITY_CHOICES:
        raise ValueError(f"fidelity must be one of {FIDELITY_CHOICES}, got {fidelity!r}")
    return fidelity
