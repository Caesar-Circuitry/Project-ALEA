"""Standalone CLI: ``python -m alea.video.overlay <command>`` (roadmap phase 2, stage 2.2b).

Commands: ``profile-init``, ``learn-glyphs``, ``clock``, ``events``. Local files only; nothing
is downloaded and no frame is written anywhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from alea.video.frames import VideoReader
from alea.video.overlay.clock import (
    extract_runs,
    read_clock_series,
    refine_run,
    runs_to_segments,
)
from alea.video.overlay.events import (
    extract_events,
    final_scores,
    write_events_jsonl,
    write_series_csv,
)
from alea.video.overlay.glyphs import GlyphSet, binarise, segment_glyphs
from alea.video.overlay.locate import roi_pixels, to_gray
from alea.video.overlay.profile import (
    AnchorTemplate,
    OverlayProfile,
    default_template_profile,
)

SEGMENTS_KIND = "match_segments_draft"
SCHEMA_VERSION = 1


def _step_frames(reader: VideoReader, step_s: float) -> int:
    fps = reader.info.fps_nominal
    return max(1, round(step_s * (fps if fps == fps else 30.0)))


def _need_glyphs(profile: OverlayProfile) -> GlyphSet:
    if not profile.glyphs:
        raise SystemExit("profile has no glyph templates; run `learn-glyphs` first")
    return GlyphSet.from_entries(profile.glyphs)


def cmd_profile_init(args: argparse.Namespace) -> int:
    prof = default_template_profile(args.profile_id)
    with VideoReader(args.video) as reader:
        if args.anchor_roi:
            x0, y0, x1, y1 = (int(v) for v in args.anchor_roi.split(","))
            gray = to_gray(reader.read(args.anchor_frame).image_bgr)
            prof.anchor = AnchorTemplate.from_frame(gray, (x0, y0, x1, y1))
        print(f"video {reader.info.width_px}x{reader.info.height_px}")
    prof.write(args.out)
    print(f"wrote template profile {args.out}; edit the ROI fractions by eye, then learn-glyphs")
    return 0


def cmd_learn_glyphs(args: argparse.Namespace) -> int:
    prof = OverlayProfile.read(args.profile)
    frames = [int(f) for f in args.frames.split(",")]
    labels = args.labels.split(",")
    if len(frames) != len(labels):
        raise SystemExit("--frames and --labels need the same number of entries")
    crops = []
    with VideoReader(args.video) as reader:
        for fi, text in zip(frames, labels, strict=True):
            gray = to_gray(reader.read(fi).image_bgr)
            x0, y0, x1, y1 = roi_pixels(prof, args.roi, gray.shape)
            binary = binarise(gray[y0:y1, x0:x1])
            boxes = segment_glyphs(binary)
            if len(boxes) != len(text):
                raise SystemExit(
                    f"frame {fi}: found {len(boxes)} glyphs but label {text!r} has {len(text)}; "
                    "fix the ROI first"
                )
            crops += [
                (binary[y : y + h, x : x + w], ch)
                for (x, y, w, h), ch in zip(boxes, text, strict=True)
            ]
    gs = GlyphSet()
    gs.learn(crops)
    prof.glyphs = prof.glyphs + gs.to_entries()
    prof.write(args.out or args.profile)
    print(f"learned {len(set(c for _, c in crops))} characters into {args.out or args.profile}")
    return 0


def cmd_clock(args: argparse.Namespace) -> int:
    prof = OverlayProfile.read(args.profile)
    glyphs = _need_glyphs(prof)
    with VideoReader(args.video) as reader:
        series = read_clock_series(reader, prof, glyphs, _step_frames(reader, args.step_s))
        runs = extract_runs(series)
        if not args.no_refine:
            runs = [refine_run(reader, prof, glyphs, r) for r in runs]
        segs = runs_to_segments(runs, pad_end_s=args.pad_end_s)
        for seg in segs:
            seg["score"] = {
                f"{k}_final": v for k, v in final_scores(reader, prof, glyphs, seg).items()
            }
        info = reader.info
        doc: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "kind": SEGMENTS_KIND,
            "video": {
                "file": Path(args.video).name,
                "sha256": reader.sha256(),
                "width_px": info.width_px,
                "height_px": info.height_px,
                "fps_nominal": info.fps_nominal,
                "pts_origin": "first_frame",
            },
            "profile_id": prof.profile_id,
            "segments": segs,
            "diagnostics": {
                "n_clock_samples": len(series),
                "n_unreadable": sum(1 for s in series if s.clock_s is None),
            },
        }
    Path(args.out).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"{len(segs)} draft segments -> {args.out}")
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    prof = OverlayProfile.read(args.profile)
    glyphs = _need_glyphs(prof)
    doc = json.loads(Path(args.segments).read_text(encoding="utf-8"))
    out = Path(args.out)
    all_events = []
    all_rows: list[dict[str, Any]] = []
    with VideoReader(args.video) as reader:
        sha = reader.sha256()
        for seg in doc["segments"]:
            events, rows = extract_events(
                reader, prof, glyphs, seg, sample_hz=args.sample_hz, video_sha256=sha
            )
            all_events += events
            all_rows += rows
    write_events_jsonl(out, all_events)
    series_path = out.with_suffix(".series.csv")
    write_series_csv(series_path, all_rows)
    print(f"{len(all_events)} events -> {out}; raw series -> {series_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m alea.video.overlay", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("profile-init", help="write a template profile to edit by hand")
    s.add_argument("video")
    s.add_argument("--out", required=True)
    s.add_argument("--profile-id", default="template-v1")
    s.add_argument("--anchor-roi", help="x0,y0,x1,y1 pixels of a static logo to use as anchor")
    s.add_argument("--anchor-frame", type=int, default=0)
    s.set_defaults(func=cmd_profile_init)

    s = sub.add_parser("learn-glyphs", help="teach glyph templates from labelled frames")
    s.add_argument("video")
    s.add_argument("--profile", required=True)
    s.add_argument("--frames", required=True, help="comma-separated frame indices")
    s.add_argument("--labels", required=True, help='comma-separated texts, e.g. "2:30,2:29"')
    s.add_argument("--roi", default="clock")
    s.add_argument("--out", help="default: overwrite --profile")
    s.set_defaults(func=cmd_learn_glyphs)

    s = sub.add_parser("clock", help="find match runs from the clock; write draft segments")
    s.add_argument("video")
    s.add_argument("--profile", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--step-s", type=float, default=1.0)
    s.add_argument("--pad-end-s", type=float, default=10.0)
    s.add_argument("--no-refine", action="store_true")
    s.set_defaults(func=cmd_clock)

    s = sub.add_parser("events", help="extract overlay score/tips/lock events per segment")
    s.add_argument("video")
    s.add_argument("--profile", required=True)
    s.add_argument("--segments", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--sample-hz", type=float, default=5.0)
    s.set_defaults(func=cmd_events)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
