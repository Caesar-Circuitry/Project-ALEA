# 0008: Video geometry and click log

**Status:** accepted (design), 2026-11-08. No phase 2 code exists yet. Each stage (2.1 to 2.6 in
`.claude/ROADMAP.md`) needs its own go-ahead, and 2.5 and 2.6 need more.

## Context

Phase 2 turns match video into two numbers per launch: exit speed (inches per second) and
launcher efficiency. The flywheel dip that `alea/data/launches.py` detects (decision 0007) gives
launch times but not ball speed. Video gives the speed.

Inputs the design has to work with:

- **Footage.** The team has no recording of its own yet. The FTC livestream is the only footage.
  It is produced by FIRST or the event host, so it is not ours to redistribute. Livestreams are
  often variable frame rate with duplicated frames. Within one video the camera is static. Its
  location differs from one event to the next. Clips stay local
  under `data/raw/` (git-ignored; `*.mp4`, `*.mov` and `*.mkv` are ignored too). Footage is never
  committed, documented or pasted into a PR. A team recording would be a new input later, not a
  change to this design.
- **Launcher.** The StarterBot launcher is 1:1 drive (the flywheel sits on the motor shaft),
  28 encoder ticks per revolution, and a 1.89 in wheel radius. Efficiency uses these numbers.
  Any gear ratio would multiply the denominator.
- **Geometry.** A floor homography maps floor pixels to floor inches. It cannot place an airborne
  ball or a ball in a hive cell 49 in up: those points land in the wrong place on the floor
  plane. Off-floor landmarks (wall tops, hive frame) are only 11 to 45 in high, so a raw 3x4
  projection matrix fitted from about a dozen hand clicks is poorly conditioned.
- **Clicks.** Each analysis needs the same clicks to be re-run when a calibration improves.
  Re-clicking a whole match after each fix is not acceptable.

## Decision

1. **One calibration per video (per camera setup).** The camera is static within a video, so
   one calibration covers the whole video. It is fitted from whichever known `alea.game`
   landmarks are visible in that setup. A floor homography needs at least 4 floor points. The
   pinhole refinement (focal length, rotation, position; square pixels, centred principal point,
   Gauss-Newton) uses more points, including wall tops and hive frame corners. Landmark clicks
   may come from any frames of the same video and are pooled into one fit. Each event gets its
   own calibration file. No shared camera pose is assumed across events. The calibration reports
   per-landmark and leave-one-out residuals. Airborne and hive points are refused unless the
   pinhole camera was recovered.
2. **Landmarks come only from `alea.game`.** Phase 2 adds no game values. Tile seams and tape
   lines are not in `alea.game`. Adding them is a separate change to `alea/game/`, with a
   physics review, and it is not approved.
3. **Manual landmark clicks only.** The operator clicks known landmarks in any frames of the
   video. Frame-to-frame propagation is not part of v1, because the camera is static within a
   video. A panning camera is out of scope for v1. Supporting one would need a separate decision.
4. **Exit speed from an image-space ballistic fit.** Fit the flight heading, launch point and
   launch velocity directly in pixels, with gravity from `alea.game` and the video's own frame
   times, using the video's one calibration. Launch time is not a fit parameter. Read the
   exit speed where the fitted trajectory crosses the launcher-exit height. The log heading and
   the robot click enter as soft priors.
5. **Raw clicks are the truth.** A click log is JSONL. It has a landmark-click record type
   (frame, landmark id, `u_px`, `v_px`), which feeds the fit, and shot, robot and ball-track
   clicks (frame, `u_px`, `v_px`, presentation time). Clicks never bake in a calibration.
   Inches, speeds and efficiency are derived by `analyze` from the clicks and one calibration
   JSON per video. The metadata references that file. A better calibration never means
   re-clicking. CSV files are flat exports for spreadsheets and notebooks.
6. **JSONL before a database.** Phase 2 stays in JSON files until the format has been tested on
   real matches. Importing into the database (stage 2.5, Alembic `0003`) waits for the user's
   go-ahead after the first real match is logged.
7. **Matplotlib UI for now.** The operator clicks in a matplotlib window (`alea/video/review.py`),
   with keyboard modes, a mark-landmarks mode, and autosave. A web UI waits for phase 6. The UI is tested with injected events on the Agg
   backend. It cannot run in `alea-dev`, which has no display, so the user checks it on the host.
8. **Tracking and detection only on GPU machines, as an optional group.** SAM 2 and torch
   (stage 2.6) go in a uv dependency group `track`, not an extra. Use platform markers so the
   group installs only on Linux x86-64. The group stays out of `just sync`, `--all-extras` and
   CI. Its tests carry the `gpu` marker. Machines: Brev now, a later Alabama cluster. Any work
   on this group, including the `uv.lock` change, a GPU run and a checkpoint download, needs a
   fresh user approval first.
9. **Efficiency with stated assumptions.** Two numbers are reported: `efficiency_op` (against
   the flywheel speed before the dip) and `efficiency_phys` (against the mean of the speeds before
   and at the dip minimum). The CSV header states the assumptions: 1:1 drive, 28 ticks per
   revolution, 1.89 in wheel radius.

## Consequences

- Calibration can be redone or improved without touching the clicks. One set of clicks feeds
  many analyses. Adding landmark clicks from more frames refits the same video's calibration.
- Operators click the visible landmarks once per video (or per setup), plus a ball track of at
  least 6 points per launch. The review UI is the largest piece of work in stage 2.2.
- Livestream-only footage lowers the accuracy expectations. Variable frame rate, lens
  distortion, and landmarks that are only partly visible all add error that the synthetic tests
  do not contain. Error bars on real launches will be wide, and each launch reports its own. No
  real-footage accuracy figure is promised until one has been measured on real livestream clips.
- Out of scope for v1: a panning or zooming camera. If the livestream production camera moves
  within a video, a separate decision is needed before any work on it.
- The fit assumes square pixels and no lens distortion in v1. Residuals show when that is wrong.
  Livestream lenses may need a distortion term later.
- Accuracy is a target on synthetic cameras only: a floor position within 2 in and a speed error
  within 3 % at 1 px click noise, with a static camera. Those targets do not transfer to real
  livestream footage until it is measured.
- Livestream frame timing: the fit uses presentation timestamps, never frame index times the
  nominal frame rate, because variable frame rate and duplicated frames break the second method.
- Open items, not decided here: the robot's top-plate height for `click_z_in` (to be measured),
  the landing height for hive cells (49.13 in, to be confirmed on the real hive), the heading
  prior's sign convention, and whether tile-seam landmarks are wanted at all.
- Phase 3 gets a measured efficiency per launch. It can then replace the fixed 0.45 in the sim.

Amended by 0009 (2026-11-08): reflection-first; calibration via hive-shot-lab.
