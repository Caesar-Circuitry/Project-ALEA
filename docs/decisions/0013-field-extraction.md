# 0013: Field extraction from match video

Status: accepted (classical front end only); detector training proposed.

## Context

A feasibility spike ran a classical pipeline on one livestream clip (Q7, Athens Qualifier,
1280x714, 5 fps, 808 frames). The calibration was eyeballed, not clicked, so every number below
is order-of-magnitude until the team's clicked calibration and hand-labelled frames exist.

What worked:

- A calibrated floor mask (floor polygon plus a 20 in tall prism for robot bodies).
- A top-down remap of the floor through the camera model, lens distortion included.
- A static-camera check by phase correlation on a strip of rail (at most 1.2 px drift).
- A median background over the clip, and frame differencing against it.
- Yellow pollen balls as small colour blobs on the grey floor.
- Floor positions of about 2 to 4 in when the segmentation is clean.

What failed:

- Telling robots from people and from stationary things. Geometry rules (touches the frame
  edge, contact point outside the field, height over 30 in) caught most people; the rest leaked.
- Merged blobs: two robots next to each other became one 53 in wide blob; shadows and
  reflections pushed the contact point several inches off (one measured case about 7 in).
- Robots parked for more than half the clip are absorbed into the median background and vanish.
- Hive state (tilt, balls inside) is above the floor and was not extracted at all.
- Identity: nothing says which robot is which team.

## Decision

Keep a local, classical front end in `alea/video/field/` that produces field STATE only: a
field mask, a background image, movers with floor positions, and top-down images. It is cheap
(about 100 ms per frame on one CPU), deterministic and testable on synthetic scenes.

Everything above state goes elsewhere:

- Identity, robot versus person in crowded scenes, merged robots, parked robots, hive state: a
  trained detector (GPU queue entry below) or the large model reading selected frames, with
  results tagged `inferred` so they are never mistaken for measurements.
- Intent and driver critique stay with later phases and use the state this module emits.

Privacy: no frame, crop or thumbnail leaves the machine and none goes into git. The tools
write only numbers (CSV, JSON) by default; background and top-down images are written only to
paths the user names and are git-ignored by convention. Anything sent to a hosted model is a
separate, explicit step that the user approves per clip.

Flower posts and tape lines are not in `alea.game`, so this module adds no constants for them;
they are passed as pixel exclusion rectangles.

## Consequences

- Downstream code (tracking, occupancy, shot attribution) can rely on `MoverRecord` rows and
  top-down grids without a GPU.
- Position accuracy is bounded by the calibration. The contact point is the blob's bottom
  edge, so a robot centre is 6 to 9 in further from the camera than the reported point.
- The median background underestimates occupancy where robots or people stand still. A windowed
  median and a pre-match empty-field image reduce this; a detector removes it.
- `_iter_frames` in `__main__.py` is a private stand-in until `alea.video.frames.VideoReader`
  (click-log branch) merges.

## Needs real data

- The team's clicked calibration of the Athens clip (floor corners, wall tops, edge clicks on
  both frames, ideally a second frame with a clearer left side).
- A few hundred hand-labelled frames from the click log: robot footprint corners, wheel contact,
  person, ball. They measure the real accuracy and train the detector.
- Tape line and flower post positions in field inches, if they are to become landmarks.

## GPU queue entry: field detector training

- What: fine-tune a small YOLO-class detector (nano or small) for classes robot, person, ball,
  hive on labelled match frames; export to ONNX for CPU inference at 5 fps.
- Data: 300 to 600 hand-labelled frames from the click log, split by match (not by frame) 80/20,
  plus 2 to 3 hundred empty-field frames as negatives. Frames stay on the machine that holds
  the footage; the job runs on a rented GPU only after the user approves uploading the labelled
  set (private, delete after the run).
- GPU: one NVIDIA L4 (24 GB) is plenty; a T4 also works.
- Time and cost: about 1 to 2 GPU hours including 3 seeds, about 3 to 6 USD at typical L4
  rates (estimate, not measured).
- Command sketch (the `detect` subcommand does not exist yet; this is the plan):

```
uv run python -m alea.video.field.train_detector --data data/field_labels \
    --model yolo-nano --epochs 80 --imgsz 640 --seed 0 --out results/field_detector
```

- Expected outputs: `best.onnx`, per-class precision/recall on the held-out matches, a CSV of
  position error of box bottom-centre against hand-labelled wheel contact (inches, via the
  calibration), and the confusion between robot and person. Accept only if robot/person
  recall is at least 0.9 on held-out matches.
