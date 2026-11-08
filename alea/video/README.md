# alea.video

Match video review. A recording of a match and the robot's log go in; a CSV of per-launch exit
speed and launcher efficiency comes out. Design: [decision 0008](../../docs/decisions/0008-video-geometry-and-click-log.md).

Status: stubs only. Stage 2.0 adds the plan and the decision. Code lands in stages 2.1 to 2.6,
listed under "Phase 2: video review" in `.claude/ROADMAP.md`.

Footage is the FTC livestream. The camera is static within a video, but its location differs
from one event to the next. So each video gets one calibration, fitted from the known field
landmarks visible in that setup. Each event gets its own calibration file. Expect wide error
bars on livestream footage: variable frame rate and partly visible landmarks add error. Panning
or zooming cameras are out of scope for v1.

What goes here, by stage:

- 2.1: `landmarks.py` (field landmarks from `alea.game.biobuzz` only), `geometry.py` (floor
  homography, pinhole refinement, residuals), `calibration.py` (one calibration JSON per video,
  fitted from landmark clicks pooled across that video's frames).
- 2.2: `frames.py` (video reader), `clicklog.py` (JSONL click log: landmark clicks, which feed
  the fit, and shot, robot and ball clicks, none of them baking in a calibration; flat CSV
  export), `review.py` and `__main__.py` (matplotlib review UI with a mark-landmarks mode).
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
edge_{floor|wall_top}_{xlo|xhi|ylo|yhi}           one point anywhere along a straight field edge
custom_<name>                                     marks not in alea.game (tile seam, tape line)
```

#### Edge clicks in `landmarks.jsonl`

A record whose `landmark_id` is an `edge_*` id is ONE clicked point lying somewhere on that
straight edge (not a corner); the fit uses it to constrain pose and lens distortion. Several
points per edge and per frame are expected. The de-duplication rule (`latest_landmark_clicks`) is:
point landmarks keep the last click per (frame, landmark id); edge clicks are never collapsed, every
line is an independent observation, in file order. Fix a wrong edge point with undo (`z`) in the
review window, not by re-clicking. The ids are additive, so old files stay valid and
`schema_version` stays 1. In the review window, `[` / `]` cycle through all ids including the edges,
and the title shows the point count of the selected edge (all frames pooled).

`--click-z-in` (robot top-plate height, default 16.0 in) is a placeholder: measure the StarterBot
top-plate height and pass the real value, because the analyzer back-projects robot clicks onto
that height.

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
