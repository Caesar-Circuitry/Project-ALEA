"""Stop hook (main session): run the tests of the units touched in the working tree.

Never blocks and never fails. Prints one summary line per touched unit as a `systemMessage`, so
a "tests pass" claim in the reply is backed by output the user can see. Skips the run when the
working tree is unchanged since the last run. Pure stdlib.
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import teamlib


def tree_digest(files: list[str], cwd: Path) -> str:
    digest = hashlib.sha256()
    for rel in files:
        path = cwd / rel
        stamp = path.stat().st_mtime_ns if path.exists() else 0
        digest.update(f"{rel}:{stamp}\n".encode())
    return digest.hexdigest()


def summaries(files: list[str], cwd: Path, root: Path, config: dict) -> list[str]:
    lines = []
    for unit in teamlib.units_for(files, config):
        if not unit.get("test"):
            lines.append(f"{unit['name']}: no test command")
            continue
        code, output = teamlib.run_check(unit["test"], cwd, root)
        state = "ok" if code == 0 else "FAILED"
        lines.append(f"{unit['name']}: {state}: {teamlib.summary_line(output)}")
    return lines


def main() -> int:
    try:
        payload = teamlib.read_payload()
        root = teamlib.project_root(payload)
        cwd = teamlib.work_dir(payload, root)
        config = teamlib.load_config(cwd)
        files = teamlib.changed_files(cwd)
        if not files:
            return 0
        stamp = teamlib.counter_path(payload, "touched").with_suffix(".digest")
        digest = tree_digest(files, cwd)
        if stamp.is_file() and stamp.read_text(encoding="utf-8") == digest:
            return 0
        lines = summaries(files, cwd, root, config)
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(digest, encoding="utf-8")
        if lines:
            print(json.dumps({"systemMessage": "tests for touched units: " + "; ".join(lines)}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
