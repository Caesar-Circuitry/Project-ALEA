"""Clone dsim at the pinned commit into a NEW temp directory and print the clone path.

Run inside the alea-dev container only (dsim is untrusted). Takes no arguments and installs
nothing: the npm install (with --ignore-scripts) is a separate command, see ../README.md.
The clone is never used as a working directory.
"""

import subprocess
import tempfile
from pathlib import Path

PIN = "62d2446e2ebdf416548fa1641847289bf47cdf36"
URL = "https://github.com/genius0412/dsim"


def run(args: list[str], cwd: Path) -> str:
    out = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def main() -> None:
    parent = Path(tempfile.mkdtemp(prefix="dsim3d-"))
    dest = parent / "src"
    # cwd is the new temp parent, never the clone
    run(["git", "clone", "--quiet", URL, str(dest)], parent)
    run(["git", "-C", str(dest), "checkout", "--quiet", PIN], parent)
    head = run(["git", "-C", str(dest), "rev-parse", "HEAD"], parent)
    assert head == PIN, head
    print(dest)


if __name__ == "__main__":
    main()
