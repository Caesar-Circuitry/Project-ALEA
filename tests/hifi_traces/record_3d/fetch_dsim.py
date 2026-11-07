"""Clone dsim at the pinned commit into a NEW EMPTY temp directory and install its deps.

Run inside the alea-dev container only (dsim is untrusted). Prints the clone path.
Usage: python fetch_dsim.py <empty-or-new-parent-dir> [--install]
The clone is never used as a working directory; npm runs with --prefix and --ignore-scripts.
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
    run(["git", "clone", "--quiet", URL, str(dest)], parent)
    run(["git", "checkout", "--quiet", PIN], dest)
    head = run(["git", "rev-parse", "HEAD"], dest)
    assert head == PIN, head
    print(dest)


if __name__ == "__main__":
    main()
