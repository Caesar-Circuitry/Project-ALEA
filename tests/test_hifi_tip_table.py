"""The official tip thresholds, run through the ported logic (hive_will_tip and hive_step).

Event Field Setup Guide section 12: 8 pollen / 0 nectar tips; 3 pollen / 3 nectar tips.
Field Check: 3 nectar + 2 pollen does not tip, 3 nectar + 3 pollen tips, 7 pollen does not
tip, 8 pollen tips.
"""

import pytest

from alea.hifi.hive import BbElementKind, HiveLoad, HiveState, hive_step, hive_will_tip

CASES = [
    (8, 0, True),  # guide section 12
    (3, 3, True),  # guide section 12
    (2, 3, False),  # Field Check: 3N + 2P
    (7, 0, False),  # Field Check: 7P
]


def _runs_to_tip(pollen: int, nectar: int) -> bool:
    n = pollen + nectar

    def kind_of(i: int) -> BbElementKind:
        return "pollen" if i < pollen else "red"

    hive = HiveState("south", tuple(range(n)), 0, 0.0, False)
    for _ in range(60 * 10):  # 10 s at 1/60 s, longer than the 4 s swing
        r = hive_step(hive, 1 / 60, kind_of)
        hive = r.hive
        if r.tipped:
            return True
    return False


@pytest.mark.parametrize(("pollen", "nectar", "tips"), CASES)
def test_official_threshold(pollen: int, nectar: int, tips: bool):
    assert hive_will_tip(HiveLoad(pollen, nectar)) is tips
    assert _runs_to_tip(pollen, nectar) is tips
