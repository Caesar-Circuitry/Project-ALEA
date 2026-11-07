"""The frozen physics files and the golden shots must stay byte-identical.

The Claude Code hooks only block the obvious ways of editing these files; this test is the check
that CI enforces for every branch. Changing a hash here is a physics change: it needs the user's
approval through `/physics-change`, a passing self-test and a Java comparison on the PR. The
same values are recorded in `.claude/ROADMAP.md` and `tests/golden/README.md`.
"""

import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# SHA-1 of the file bytes (`shasum -a 1 <file>`); `.gitattributes` pins LF endings for .py.
FROZEN_SHA1 = {
    "alea/sim/shotsim.py": "a2e96d19db3f3f0d9f72653a939fa8513883c974",
    "alea/sim/study.py": "fd903a17a229e6c2b8c6e272be99bfb5421c203a",
    "alea/sim/hive_frame.b64": "96d5088baa044f3a3527e78a601a4df81f93866c",
    "tests/golden/golden_shots.npy": "2a13bb587528795e350fc0577e40fb2f7d36bcf4",
}


@pytest.mark.parametrize(("path", "sha1"), FROZEN_SHA1.items())
def test_frozen_file_is_unchanged(path: str, sha1: str) -> None:
    got = hashlib.sha1((ROOT / path).read_bytes(), usedforsecurity=False).hexdigest()
    assert got == sha1, f"{path} changed (sha1 {got}); frozen physics needs /physics-change"
