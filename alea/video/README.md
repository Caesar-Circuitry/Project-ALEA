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

Lens distortion is not modelled; check the residuals. Accuracy on synthetic cameras is
asserted in `tests/test_video_geometry.py` (no real footage is committed).
