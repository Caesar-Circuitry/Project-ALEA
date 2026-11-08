# alea.video

Field homography, click-and-log, tracking and detection for match video review.

**Roadmap phase:** 2

## Click log and review UI (roadmap phase 2, stage 2.2)

| Module | What |
|---|---|
| `frames.py` | `VideoReader` over `cv2.VideoCapture` (headless): size, nominal fps, seek by frame index, presentation time (`t_pts_s`) of every frame, variable-frame-rate check. Never use index / fps for physics, only for seeking. |
| `clicklog.py` | Versioned JSONL schema (`schema_version` 1): `ShotObservation` (raw robot, launch, ball-track and landing clicks plus outcome), `LandmarkClick`, `VideoMeta`; validating readers and writers; CSV export. |
| `landmark_ids.py` | Landmark id strings (below). |
| `review.py` | Pure state machine (frame stepping, modes, click handling, undo, record building) plus the thin matplotlib app. matplotlib is imported lazily and a missing display gives a clear error. |
| `__main__.py` | `python -m alea.video review VIDEO [--calibration cal.json --camera-setup ID --out shots.jsonl ...]`, `info`, `validate`, `export-csv`. |

Raw clicks (frame, `u_px`, `v_px`, presentation time) are the truth. Shot, robot and ball clicks
never carry a calibration. The camera is static within a video, so a video has at most one
calibration: `VideoMeta` (`<out stem>.video.json`) stores a reference to it (path, its
`schema_version`, a camera-setup id), and analysis resolves it from there. Landmark clicks live in
their own file (`<out stem>.landmarks.jsonl`); clicks from any frame of the same video are pooled
when the calibration is fitted, and a later click on the same landmark and frame replaces the
earlier one. Derived values (inches, speeds, efficiency) are not stored here.

### Landmark id convention (shared with the camera geometry code)

An id names a known field point; it is never a coordinate. The world position is looked up from
`alea.game.biobuzz` by the fitting code. `alea.video.landmark_ids.known_landmark_ids()` lists them:

```
field_floor_corner_{xlo|xhi}_{ylo|yhi}            z = 0
field_wall_top_corner_{xlo|xhi}_{ylo|yhi}         z = WALL_HEIGHT_IN
hive_{red|blue}_pivot
hive_frame_corner_{xlo|xhi}_{ylo|yhi}_{zlo|zhi}
hive_{red|blue}_mouth_{audience|rear}             floor-plane use only
custom_<name>                                     marks not in alea.game (tile seam, tape line)
```

### Review keys

`left/right` +-1 frame, `down/up` +-10, `pagedown/pageup` +-100, `home/end`. Modes: `c` mark
landmarks (`[` / `]` choose the id, then click it), `r` robot, `l` launch, `b` ball track,
`d` landing (`1`..`6` landing kind), `o` outcome (`m` made, `x` miss, `u` unknown). `t` toggles the
robot click kind, `z` undoes the last click, `enter` saves the record (autosave, one JSONL line),
`delete` removes the last saved record, `q` quits. Not tested in CI: the window itself.

### Manual checklist (needs a desktop and a local clip; never commit footage)

1. `uv run python -m alea.video info clip.mp4` reports size, frame count and fps.
2. `uv run python -m alea.video review clip.mp4 --out shots.jsonl --operator you` opens a window.
3. Step with the arrow keys; the title shows frame, mode and counts.
4. Press `c`, `]`, click a field corner; `<out>.landmarks.jsonl` gains a line. `z` removes it.
5. Mark a robot, launch, 6 ball points and a landing, press `m`, then `enter`; `shots.jsonl` gains a line.
6. `python -m alea.video validate shots.jsonl` and `export-csv shots.jsonl --out-dir out` succeed.
7. Close and reopen: earlier shots and landmarks are kept.
