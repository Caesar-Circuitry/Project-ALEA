# alea.video

Field homography, click-and-log, tracking and detection for match video review.

**Roadmap phase:** 2

## Camera geometry (stage 2.1)

The camera is static within one video; it changes between events. Each video (camera setup)
gets its own calibration, fitted from whichever known field landmarks are visible in it. Clicks
from several frames of the same video may be pooled. Nothing assumes a shared camera pose.

- `landmarks.py`: named 3D landmarks (field corners, wall tops, hive pivots, hive frame box
  corners), all derived from `alea.game.biobuzz`. No game values live here. A hive frame box
  corner is a real post only where the CAD has a cube; click only what you can see.
  Ids match the click log's strings (`field_floor_corner_xlo_ylo`, `hive_red_pivot`,
  `hive_frame_corner_xlo_ylo_zhi`, `hive_blue_mouth_rear`, ...). Mouths are floor-plane only.
  `custom_<name>` ids have no coordinates in `alea.game`; `calibrate` ignores them with a warning.
- `geometry.py`: numpy-only camera model. Floor homography (normalised DLT, at least 4
  non-collinear floor points) -> pinhole (f, R, position; square pixels, centred principal
  point) -> Levenberg-Marquardt refinement over all landmarks. Per-point and leave-one-out
  residuals in px, a floor uncertainty ellipse in inches, degeneracy warnings. Elevated
  landmarks (wall tops, pivots, frame) pin the focal length; floor-only fits are flagged
  `pinhole_from_homography` (unrefined).
- `calibration.py`: `calibrate(clicks, video, camera_setup_id=...)` -> `Calibration`, JSON
  read/write (`schema_version`, camera setup id, landmark ids, residuals, ellipses).

### Accuracy upgrades (stage 2.1)

- **Lens distortion.** `Camera` carries Brown-Conrady `k1` (and `k2` with
  `distortion="k1k2"`), stored in the calibration JSON under `camera.distortion`;
  `Camera.distort_px` / `undistort_px` convert pixels. The fit estimates `k1` only when off-floor
  points or straight-edge clicks constrain it (`distortion="auto"`), under a weak zero prior
  (sigma 0.1), and warns when `k1` stays poorly constrained. It matters for wide cameras where
  the field fills the frame; for a telephoto view the field sits in the image centre and it
  changes nothing.
- **Straight edges.** Points clicked anywhere along a straight field edge constrain pose and
  distortion without naming a point on it. Edge ids: `edge_{floor|wall_top}_{xlo|xhi|ylo|yhi}`
  (see `landmarks.edge_table()`). They go in the same click list as landmark clicks (name = edge
  id, one record per point). The click log (`feature/2-click-log`) validates landmark ids
  strictly, so it must also accept these `edge_*` ids in `<stem>.landmarks.jsonl` before the UI
  can record them. `calibrate` warns when five or more clicks on one edge deviate more than 2 px
  from a straight line (distortion or a mis-click).
- **Robust loss.** A Cauchy loss with iterative reweighting (`robust=True`) stops one mis-click
  from dominating; leave-one-out residuals (computed without the robust weights) still flag it.
- **Pooling.** The same landmark clicked in several frames is several independent observations;
  `click_noise_px` in the JSON is the pooled scatter of repeated clicks (used for the floor
  ellipses when `sigma_px` is not given).
- **Sub-pixel snap.** `subpixel.snap_corner` (needs the `video` extra) refines a click to the
  local corner with `cv2.cornerSubPix`; optional.

Accuracy on synthetic cameras is asserted in `tests/test_video_geometry.py`,
`tests/test_video_distortion.py` and `tests/test_video_calibration.py` (no real footage is
committed). Read these numbers honestly:

- The plan's targets (RMS reprojection <= 1.5 px, focal error <= 3 %, floor error <= 2 in,
  error of a point at z = 49 in <= 2 in; 10 landmarks, 1 px click noise) are met on the **mean
  over noise seeds**, not on every single trial. The tests also enforce looser worst-case
  bounds: RMS <= 2.0 px, focal error <= 8 %, floor and airborne position error <= 4 in.
- For an oblique wide camera the airborne error stays around 1 to 3 in even with distortion
  modelled; a telephoto view or a camera square to the field does better.
- These are clean synthetic results: exact lens model, exact landmark coordinates, Gaussian
  click noise. Real footage (compression blur, tape and tile offsets, an imperfect lens model)
  will be worse.
