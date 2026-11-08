# alea.video

Match video review. A recording of a match and the robot's log go in; a CSV of per-launch exit
speed and launcher efficiency comes out. Design: [decision 0008](../../docs/decisions/0008-video-geometry-and-click-log.md).

Status: stubs only. Stage 2.0 adds the plan and the decision. Code lands in stages 2.1 to 2.6,
listed under "Phase 2: video review" in `.claude/ROADMAP.md`.

What goes here, by stage:

- 2.1: `landmarks.py` (field landmarks from `alea.game.biobuzz` only), `geometry.py` (floor
  homography, camera fit, refinement, residuals), `calibration.py` (calibration JSON).
- 2.2: `frames.py` (video reader), `clicklog.py` (JSONL click log, CSV export), `review.py` and
  `__main__.py` (matplotlib review UI).
- 2.3: `ballistics.py` (image-space fit), `sync.py` (video-to-log time offset), `efficiency.py`
  (efficiency columns for `launches.csv`).
- 2.4: a landmark diagram script goes in `tools/`, with its own README.
- 2.6: `track.py` (SAM 2 tracking), GPU only, behind the `track` dependency group.

Rules for this folder:

- Import `cv2` (from the `video` extra) lazily, so the rest of the package imports without it.
- Footage stays local in `data/raw/` (git-ignored). Never commit a clip, a screenshot of a
  spectator, or a derived per-team table.
- Game values come only from `alea/game/`. Units go in names: `_px`, `_in`, `_s`, `_deg`.

Planned commands (none work yet):

```
python -m alea.video review <video> --calibration cal.json --out shots.jsonl
python -m alea.video analyze shots.jsonl --log match.rlog --calibration cal.json
```

**Roadmap phase:** 2
