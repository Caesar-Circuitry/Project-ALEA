"""TaskCreated hook: a task subject must say what kind of work it is and which files it owns.

Format: `<kind>: <paths or "all">`, kind one of impl, test, verify, safety, docs, plan. The test
gate reads the paths to learn which unit a task touched. Exit 2 deletes the task and returns the
reason to the agent. Pure stdlib.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import teamlib

SUBJECT = re.compile(r"^(impl|test|verify|safety|docs|plan): (.+)$")
FORMAT = (
    "Task subject must be `<kind>: <paths>` with kind one of impl, test, verify, safety, docs, "
    "plan, followed by at least one repo path or the word `all`. "
    "Example: `impl: alea/data/importer.py tests/test_data_import.py`.\n"
)


def subject_paths(subject: str) -> tuple[str, list[str]] | None:
    """(kind, paths) for a well-formed subject, else None. `all` gives an empty path list."""
    match = SUBJECT.match(subject.strip())
    if not match:
        return None
    words = [w.strip(",;") for w in match.group(2).split()]
    if "all" in words:
        return match.group(1), []
    paths = [w for w in words if "/" in w or "." in w]
    return (match.group(1), paths) if paths else None


def main() -> int:
    payload = teamlib.read_payload()
    subject = str(payload.get("task_subject", ""))
    if subject_paths(subject) is None:
        sys.stderr.write(f"BLOCKED task `{subject}`. {FORMAT}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
