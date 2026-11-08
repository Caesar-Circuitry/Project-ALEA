# alea.video.overlay

Reads the scoring overlay of an FTC livestream recording: finds the matches from the countdown
clock and extracts score, tip and lock changes with frame-exact times. No OCR engine; OpenCV
and numpy only.

**Roadmap phase:** 2 (stage 2.2b)

## What is here

| File | Purpose |
|---|---|
| `profile.py` | `OverlayProfile` JSON: ROIs as frame fractions, per-phase overrides, banner anchor, glyph templates |
| `locate.py` | `locate_anchor` (`cv2.matchTemplate`, scales 0.8 to 1.25), `roi_pixels`, `overlay_present` |
| `glyphs.py` | Otsu binarise, glyph segmentation, `GlyphSet` (12x20 templates, normalised cross-correlation), `read_number` |
| `clock.py` | `read_clock_series`, `extract_runs` (robust fit), `refine_edge` / `refine_run`, `runs_to_segments` |
| `events.py` | `extract_events` (debounce, bisection, increment decomposition), JSONL and CSV writers |
| `synth.py` | Synthetic overlay streams and truth for tests and demos |
| `__main__.py` | `profile-init`, `learn-glyphs`, `clock`, `events` |

## How the profile works

All ROIs are fractions of the frame, so one profile serves 720p and 1080p. A base layout names
`banner_anchor`, `clock`, `label`, `red_score`, `blue_score`, `red_tips`, `blue_tips`,
`red_lock`, `blue_lock`, `red_teams`, `blue_teams`. The overlay changes widgets between phases
(an AUTO robot icon becomes a TELEOP gamepad icon and pushes the score sideways), so a profile
may override any ROI for `auto`, `teleop`, `endgame` or `post`; the transition uses the TELEOP
layout. If the profile carries an anchor template (a small crop of a static logo), every frame
is searched for it and the ROIs follow its shift and scale.

Each numeral ROI must hold only the number ("2" of "2 /4" for the tips counter; the "/4" stays
outside). Glyph templates are taught once from a labelled countdown:

```
python -m alea.video.overlay profile-init match.mp4 --out profile.json --anchor-roi 10,5,90,40
# edit profile.json by eye, then teach the glyphs from frames whose clock text you know
python -m alea.video.overlay learn-glyphs match.mp4 --profile profile.json --frames 1200,1230 --labels "2:30,2:00"
python -m alea.video.overlay clock match.mp4 --profile profile.json --out segments.json
python -m alea.video.overlay events match.mp4 --profile profile.json --segments segments.json --out overlay_events.jsonl
```

`clock` writes a `match_segments_draft` JSON (plain dicts in the plan's section 4.2 shape,
consumed by `alea.video.segment` on its branch). `events` writes `overlay_events.jsonl` (schema
version 1) and `overlay_events.series.csv`, the raw 5 Hz readings for audit.

## Rules

- Local files only. The recording is never downloaded by this code.
- No frames, thumbnails or crops are committed or written; minors are visible on streams. A
  profile holds one small logo crop and 12x20 glyph shapes, nothing else.
- Game point values in `events.py` are a placeholder table; they belong in `alea/game` via a
  physics-reviewed change.

## Accuracy targets and measured (synthetic)

Targets from the plan: match boundary error median <= 0.5 s, p95 <= 1.5 s. Measured on a
synthetic 2-match 10 fps stream: coarse fit at 0.7 s sampling about 0.05 s, after native-rate
refinement 0 s (one frame). Tip events are found within one frame of the truth.

## What needs real data (INFERRED or UNVERIFIED until the user's local Athens clip is used)

- ROI fractions and glyph templates for the real overlay (tune on the local clip).
- Clock behaviour across the 8 s transition (assumed: it holds at 2:00; if it jumps or is
  continuous the single-line fit is used) and its rounding (assumed `ceil` of seconds left).
- The house icon "N /4" being hive tips and the lock icon being nectar still locked.
- Whether the displayed score includes penalties, and the penalty values.
- Phase boundaries from the clock: auto 150 to 120 s, teleop, endgame the last 30 s.
