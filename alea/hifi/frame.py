"""Uses the dsim port (commit 62d2446e2ebdf416548fa1641847289bf47cdf36, genius0412); ALEA glue.

License: PolyForm Noncommercial 1.0.0 (see alea/hifi/LICENSE-dsim); lives under the hifi licence.

Frame conversion between dsim's field-centred frame (origin at the field centre, hive pivots at
x = +-12.75 in on y = 0, red at -x) and ALEA's frame (origin at a field corner, `alea.game`).

The shift is FIELD_SIZE_IN / 2 = 70.65 in on both axes. This is a PROVISIONAL choice made for
the conversion only: where ALEA's origin sits is OPEN (alea/hifi/PORTING.md, evidence item 1),
not settled by the CAD. It is NOT 70.75. Nothing depends on it: in `hive_session.offer_ball`
the two conversions cancel, so no study result changes with this number. Consequence, stated
here so nobody "fixes" it: the converted hive pivots are at x = 57.90 and 83.40, y = 70.65,
against `alea.game.biobuzz.HIVE_X_IN` = (58.0, 83.5) and `HIVE_Y_IN` = 70.75. The pair spacing
agrees (25.5 in); both axes are 0.10 in off ALEA's constants. That 0.10 in is reported and
tested, not absorbed. No axis flip is assumed: dsim "north" is +y, matching
`HIVE_UP` (red's up cell is toward -y = "south", dsim's `BB_HIVE_UP_STAGED`).

Role in the session model, stated plainly: `hive_session.offer_ball` builds the scored ball's
position in the ALEA frame and converts it to dsim's frame for `hive_accepts`. The two
conversions cancel (up to rounding), so the conversion is exercised but RESULT-NEUTRAL there; it
is kept, with its tests, because later steps (contacts, robot positions) will need it.
"""

from alea.game.biobuzz import FIELD_SIZE_IN
from alea.hifi.hive import Vec2

FIELD_CENTRE_IN = FIELD_SIZE_IN / 2


def dsim_to_alea(p: Vec2) -> Vec2:
    """A dsim (field-centred) point in the ALEA frame."""
    return Vec2(p.x + FIELD_CENTRE_IN, p.y + FIELD_CENTRE_IN)


def alea_to_dsim(p: Vec2) -> Vec2:
    """An ALEA point in dsim's field-centred frame."""
    return Vec2(p.x - FIELD_CENTRE_IN, p.y - FIELD_CENTRE_IN)
