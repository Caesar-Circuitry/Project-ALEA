# alea.video.field

Classical, local field-state extraction from static-camera match video: field mask, top-down
view, background, movers with floor positions. State only; identity, hive state and intent are
for a detector or the large model (decision `docs/decisions/0013-field-extraction.md`).

**Roadmap phase:** 2 (field extraction follow-up)

## Pipeline

1. Calibrate the video (`alea.video.calibration`, from clicks) to get a `Camera`.
2. `fieldmask.py`: `floor_polygon_px`, `floor_mask`, `prism_mask` (floor plus a z = 0..20 in
   hull for robot bodies, optional margin for people at the edge and exclusion rectangles for
   posts and hive houses), `overlay_band_mask` (stream scoreboard).
3. `background.py`: `median_background` (streaming reservoir of at most `max_samples` frames,
   so memory is bounded), `windowed_median_background` (adaptive, for parked robots),
   `camera_static_check` (phase correlation on a fixed strip; max |dx|, |dy| in px).
4. `movers.py`: `foreground_mask` -> `blobs` -> `classify_blob` (`ClassifierConfig` rules:
   touches frame edge, contact outside the field, height over 30 in, else robot if wide enough,
   else small mover) -> `floor_position_in`; `yellow_ball_candidates` + `ball_position_in`;
   `MoverRecord` CSV; `occupancy_fraction` over top-down masks.
5. `topdown.py`: `TopDownGrid`, `warp_topdown` (`cv2.remap`, lens distortion included),
   `topdown_to_field_in` / `field_to_topdown_px`, `draw_field_outline`.
6. `synth.py`: synthetic scenes for tests (tiled floor, cube robot, balls, person box).

CLI (`python -m alea.video.field ...`): `background VIDEO --calibration cal.json --out bg.png`,
`movers VIDEO --calibration cal.json --background bg.png --out movers.csv [--topdown-dir DIR]`,
`static-check VIDEO --out report.json`. Needs the `video` extra. `_iter_frames` in `__main__.py`
is private; switch it to `alea.video.frames.VideoReader` once the click-log branch merges.

Inputs: a video, a calibration JSON. Outputs: numbers (CSV, JSON) plus operator images
(`bg.png`, top-down PNGs) that must stay out of git.

## Accuracy, honestly

- Clean segmentation, good calibration: 2 to 4 in on the floor (spike, eyeballed calibration,
  not verified against ground truth).
- Merged, shadowed or reflected blobs: 5 to 10 in.
- The contact point is the blob's bottom edge. A robot centre is 6 to 9 in further from the
  camera, and this is not corrected.
- Robots or people that stay still for more than half of the clip enter the median background
  and vanish; occupancy is then an underestimate. Use a windowed median or an empty-field image.
- Synthetic tests (noise-free, exact camera) show the geometry is right: robot contact within
  1.5 in, balls within 0.4 in, top-down placement within 3 in. Real footage will be worse.

## Privacy

Frames never leave the machine and none are committed. Only numbers are written by default.

## Not game values

Flower posts and tape lines are not in `alea.game`; this package adds no constants for them.
Callers pass pixel exclusion rectangles. Field and pollen sizes come from `alea.game.biobuzz`.

## Needs real data

The team's clicked calibration of the Athens clip, and a few hundred hand-labelled frames
(robot footprint corners, wheel contact, person, ball) to measure accuracy and train a detector.
Opt-in smoke test: set `ALEA_LOCAL_CLIP` to a local video path.

## GPU queue entry: field detector training

Fine-tune a small YOLO-class detector (robot, person, ball, hive) on 300 to 600 hand-labelled
frames split by match, plus empty-field negatives. One NVIDIA L4, about 1 to 2 GPU hours, about
3 to 6 USD (estimate). Sketch (the trainer does not exist yet):
`uv run python -m alea.video.field.train_detector --data data/field_labels --model yolo-nano --epochs 80 --imgsz 640 --out results/field_detector`.
Outputs: `best.onnx`, per-class precision/recall on held-out matches, bottom-centre position
error in inches. Details in decision 0013.
