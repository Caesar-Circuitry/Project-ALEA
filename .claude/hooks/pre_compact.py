"""PreCompact hook: tell the compaction summary what a team run cannot afford to lose.

Stdout of a PreCompact hook that exits 0 is used as instructions for the summary. Pure stdlib.
"""

import sys

INSTRUCTIONS = (
    "Preserve verbatim: the plan items with their tags and file lists, which teammate owns "
    "which files, the task subjects and their states, and any open FAIL or BLOCKED rows from "
    "the verifier or the physics-reviewer."
)

if __name__ == "__main__":
    print(INSTRUCTIONS)
    sys.exit(0)
