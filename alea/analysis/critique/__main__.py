"""`python -m alea.analysis.critique <log> [--json out.json] [--synthetic SEED]`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from alea.analysis.critique.features import compute_features
from alea.analysis.critique.signals import MatchSignals


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m alea.analysis.critique", description=__doc__)
    p.add_argument("log", nargs="?", type=Path, help=".rlog or .wpilog file")
    p.add_argument("--synthetic", type=int, metavar="SEED", help="use a synthetic match instead")
    p.add_argument("--json", type=Path, metavar="OUT", help="write the features as JSON")
    args = p.parse_args(argv)
    if (args.log is None) == (args.synthetic is None):
        p.error("give exactly one of <log> or --synthetic SEED")
    sig = (
        MatchSignals.from_synthetic(args.synthetic)
        if args.synthetic is not None
        else MatchSignals.from_log(args.log)
    )
    feat = compute_features(sig)
    for line in feat.summary_lines():
        print(line)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(feat.to_dict(), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
