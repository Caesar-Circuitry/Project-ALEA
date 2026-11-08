"""python -m alea.analysis.reflection <log> [options] --out DIR  (or --synthetic SEED)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alea.analysis.reflection.baseline import Baseline
from alea.analysis.reflection.overlay_events import read_overlay_events, synth_overlay_events
from alea.analysis.reflection.prompt import build_prompt, estimate_tokens
from alea.analysis.reflection.report import build_report, render_markdown, write_report
from alea.analysis.reflection.timeline import build_timeline, launches_from_log
from alea.data import rlog
from alea.data.importer import read_log
from alea.data.synthetic import synth_match

SYNTH_OFFSET_S = 2.5  # the synthetic log starts this long before the synthetic match


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m alea.analysis.reflection", description=__doc__)
    ap.add_argument("log", nargs="?", help=".rlog or .wpilog robot log")
    ap.add_argument("--overlay-events", help="overlay events JSONL")
    ap.add_argument("--baseline", help="shot-study summary.csv (or its directory)")
    ap.add_argument("--alliance", choices=["red", "blue"])
    ap.add_argument("--team", type=int)
    ap.add_argument("--label", help="match label, e.g. Q7")
    ap.add_argument("--event-code")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--synthetic", type=int, metavar="SEED", help="use synthetic inputs")
    args = ap.parse_args(argv)

    alliance = args.alliance
    try:
        if args.synthetic is not None:
            alliance = alliance or "red"
            synth = synth_match(args.synthetic)
            data = rlog.decode(synth.data)
            events = synth_overlay_events(
                synth.launch_times_s,
                args.synthetic,
                alliance=alliance,
                offset_s=SYNTH_OFFSET_S,
                tip_times_match_s=(100.0,),
                match_label=args.label or "SYN",
            )
        elif args.log:
            data = read_log(args.log)
            events = read_overlay_events(args.overlay_events) if args.overlay_events else []
        else:
            ap.error("give a log or --synthetic SEED")
        if events and alliance is None:
            ap.error("--alliance is required with overlay events")
        baseline = Baseline.from_summary(args.baseline) if args.baseline else Baseline.placeholder()
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    launches, _ = launches_from_log(data)
    timeline = build_timeline(launches, events, alliance)
    meta = {
        "event_code": args.event_code,
        "match_label": args.label,
        "alliance": alliance,
        "team_number": args.team,
    }
    report = build_report(timeline, baseline, meta)
    prompt = build_prompt(report)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_report(report, out / "report.json")
    (out / "report.md").write_text(render_markdown(report), encoding="utf-8")
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"wrote report.json, report.md, prompt.txt to {out} (~{estimate_tokens(prompt)} tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
