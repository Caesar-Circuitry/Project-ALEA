# ALEA roadmap

Where the repo is, what each pull request delivers, and where the project goes after setup.
Read this before starting a PR. Update the status table when a PR merges (the `/pr` skill
reminds you).

Last updated: 2026-11-08.

## Setup PRs: status

| # | Branch | Scope | Status | Blocked on |
|---|---|---|---|---|
| 1 | `setup/01-skeleton` | Folder tree, `pyproject.toml`, `uv.lock`, pre-commit, `justfile`, CODEOWNERS | merged (GitHub #1) | |
| 2 | `setup/02-claude-workflow` | `.claude/` agents, hooks, skills, rules, `CLAUDE.md`, decision 0003 | merged (#2) | |
| 3 | `setup/03-ci` | CI on ubuntu, macOS, Windows; Dependabot; PR template | merged (#3), **partial** | |
| 3b | `setup/03b-ci-complete` | Finish PR 3, see below | merged (#8): four runners, Windows 11 ARM dropped; Dependabot PRs resolved 2026-11-07 (#4, #5, #10, #11 merged; #6, #9 closed; Gradle pinned to v5 in #17) | |
| 4 | `setup/04-move-sim` | Move the shot sim in, physics frozen | merged (#16) | |
| 5 | `setup/05-robot-contract` | `docs/robot-interface.md`, sample robot, contract test | merged (#19) | |
| 6 | `setup/06-data-importers` | SQLAlchemy models, `.rlog` reader, `.wpilog` reader | merged (#24) | |
| 7a | `setup/07a-devcontainer` | CPU dev container, agent shell sandbox, guard_container hook, decision 0006 | merged (#23) | |
| 7 | `setup/07-dev-env-docs` | Dev containers, `hpc/`, MkDocs site, notebook, README | merged (#26); Pages needs a one-time manual setting: Settings > Pages > Source: GitHub Actions | |
| 8 | `setup/08-hifi-stub` | `alea/hifi` stub, `fidelity` switch, decision 0005, delete `_incoming/` | merged (#27) | |

PRs 4 to 8 need the source the user copies from `~/Downloads/alea_project` into `_incoming/`.
If `_incoming/` is missing, stop and ask; do not reconstruct the source.

## What each PR must deliver

### 3b: finish CI
Merged PR 3 runs three runners and has no docs or robot job. Remaining:
- Add `ubuntu-24.04-arm` to the matrix (all four targets from
  `[tool.uv].required-environments`). Run pyright once, on ubuntu.
- `robot` job on `robot/**` changes: Temurin JDK 17, Gradle cache, `./gradlew assembleDebug`.
- `docs` job: `mkdocs build --strict`, deploy Pages on `main`. Add it in PR 7 if `mkdocs.yml`
  does not exist yet.
- `.github/workflows/gpu-tests.md`, issue templates (`bug.yml`, `feature.yml`), Gradle in
  Dependabot, `docs/decisions/0004-branch-protection.md`.
- Merge or close the open Dependabot branches (checkout 7, setup-uv 7, warp-lang 1.19.0). Done 2026-11-07.
- Done when: CI green on all four runners.
- Dropped for now: Windows 11 ARM (win32/ARM64). cryptography, pyarrow, protobuf and debugpy
  lack win_arm64 wheels. Revisit when they ship them.

### Before 4: import the original ALEA code
The original Java-validated Warp code is not in this repo yet. Clone it into the git-ignored
`_incoming/` folder from the repo root:

```
git clone https://github.com/Caesar-Circuitry/alea-original.git _incoming/alea_project
git -C _incoming/alea_project rev-parse HEAD
```

The HEAD must be `7e2334bc8d09a7dc64e825c0838658ae7e91a9af`. The code lives in
`_incoming/alea_project/code/`.

Run the self-test with the repo venv. Do not pass `-I` to Python: the script imports
sibling modules.

```
just sync
uv run python _incoming/alea_project/code/selftest.py cpu
```

At that commit, 100.000 % of the 10,000 golden shots agree. The bar is at least 99.9 %.

Current hashes of the frozen files in the repo. `tests/test_frozen_files.py` enforces the SHA-1
values in CI.

| File | SHA-1 (`shasum -a 1`) | Git blob (`git hash-object`) |
|---|---|---|
| `alea/sim/shotsim.py` | `a2e96d19db3f3f0d9f72653a939fa8513883c974` | `b0ef01c353787dd74fee7a25dfb72b27c105c8c9` |
| `alea/sim/study.py` | `fd903a17a229e6c2b8c6e272be99bfb5421c203a` | `df8fed7170a8fbb9bfaf20618c5533f46d614caf` |
| `tests/golden/golden_shots.npy` | `2a13bb587528795e350fc0577e40fb2f7d36bcf4` | `0c8b180cd40808351b2278ff9050c86519c58fd4` |

```
shasum -a 1 alea/sim/shotsim.py
git hash-object alea/sim/shotsim.py
```

`study.py` differs from the original in `_incoming/` (SHA-1 `e2f14e2854c7647fa2a7f0126b84244f25df7549`)
only in its import line: `from shotsim import` became `from alea.sim.shotsim import`.

Windows: `certutil -hashfile <file> SHA1`.

Copying `shotsim.py`, `study.py` or `golden_shots.npy` into the repo is a physics change. It
needs the user's approval through `/physics-change`. Never regenerate `golden_shots.npy`. If
it is missing, stop and ask.

### 4: move the sim (physics frozen)
- Record the SHA-1 of `shotsim.py` and `study.py` in the PR body before anything moves.
- Move the sim files into `alea/sim/` with `git mv`. Only import lines may change in the two
  frozen files.
- Game constants into `alea/game/biobuzz.py` with `# source:` comments. Snapshot them in
  `tests/golden/game_constants_snapshot.json` and test equality.
- Verification scripts into `alea/sim/verification/`. `golden_shots.npy` into `tests/golden/`;
  if it is missing, stop and ask, never regenerate.
- `conf/study/brev72.yaml`; `run_study` keeps `--shots --device` and gains `--config`.
- `tests/test_selftest.py` asserts at least 99.9 % agreement.
- Agents: `implementer` moves, `physics-reviewer` signs off on the diff.
- Done when: `just selftest` passes and `just study` writes `summary.csv`.

### 5: robot contract
- `docs/robot-interface.md` first: PsiKit key, type, units, rate, source. All keys under
  `Alea/`. Motor current needs `FtcLogTuning.logMotorCurrent=true`.
- `robot/`: TeamCode-only Gradle project on FTC SDK v12.0 with PsiKit from
  `repo.dairy.foundation` (check the actual version on the Maven index).
- `tests/test_robot_contract.py` checks the Java keys and constants against the doc and
  `alea.game`. Decision 0002.
- Done when: contract test passes and `./gradlew assembleDebug` is green in CI.

### 6: data importers
- `alea/data/models.py` (Team, Event, Match, Robot, LogFile, Shot) and Alembic; default
  `sqlite:///alea.db`.
- `alea/data/rlog.py`: pure-Python RLOG revision 2 decoder, the format PsiKit writes. A tiny
  golden `.rlog` in `tests/golden/`.
- `.wpilog` reader behind the `logs` extra, same key contract.
- Done when: a sample log imports into SQLite with every contract key.

### 7: dev environment and docs
- `.devcontainer/cpu/` landed in 7a. `.devcontainer/cuda/`, `hpc/brev`, `hpc/slurm` and
  `hpc/apptainer` landed in PR 7 (untested without a GPU).
- `docs` CI job and `.github/workflows/pages.yml` (deploy on push to `main`) landed in PR 7.
- `mkdocs.yml` and docs text from `_incoming/`; decision 0001.
- Notebook paired with jupytext; root README with a per-OS install table.
- Done when: `just docs` is clean and Pages is live.

### 8: hifi stub
- `alea/hifi/` README, `DSIM_VERSION`, `fidelity: fast | hifi` (hifi raises
  `NotImplementedError`), decision 0005 with the dsim port plan.
- Delete `_incoming/`; no file over 1 MB outside `tests/golden/`.
- Done when: the end-to-end checks in the setup plan pass from a fresh clone.

### Phase 2: video review

Phase 2 is done when an operator takes a recording of one of our matches and the robot's log,
and gets a CSV of per-launch exit speed with an uncertainty and launcher efficiency, using only
`python -m alea.video`. The accuracy is proven on synthetic cameras in `tests/`. No real footage
is committed. Tracking stays optional and GPU-only. Design: decision 0008.

Inputs: the team has no recording of its own yet, so the FTC livestream is the starting footage.
The launcher is the StarterBot: 1:1 drive, 28 ticks per revolution, 1.89 in wheel radius.

Every phase 2 PR also meets the setup rules: `pathlib`, units in names, a `README.md` in every
new folder, no file over 1 MB outside `tests/golden/`, no footage or secrets in git, and
`just lint` and `just test` green. Agents run shell work through `just dev`.

### 2.0: roadmap and decision record (`docs/2-video-plan`)
- Deliver: this phase 2 section; decision 0008 (one calibration per video, floor homography plus pinhole refinement, raw
  clicks as truth, JSONL before a database, GPU tracking behind a dependency group); the phase 2
  lines in `alea/video/README.md` and `docs/README.md`; 0008 in `mkdocs.yml` and
  `docs/decisions/README.md`.
- Done when: `just docs` is clean and this roadmap names every 2.x stage with its done-when list.
- Blocked on: nothing. PRs #38 and #39 are merged.

### 2.1: camera geometry (`feature/2-camera-geometry`)
- Deliver: `alea/video/landmarks.py`, named 3D field landmarks built only from
  `alea.game.biobuzz` (field corners at z = 0 and at the wall top, hive pivots, hive frame
  corners that are occupied); `alea/video/geometry.py`, with `fit_homography` (floor, at least 4
  points, normalised DLT), `camera_from_homography` (focal length, rotation, position; square
  pixels, centred principal point), `refine_camera` (Gauss-Newton on every visible landmark,
  floor and off-floor), `project`, `ray`, `point_on_plane_z`, per-landmark and leave-one-out
  residuals, a floor uncertainty ellipse per point and degeneracy warnings;
  `alea/video/calibration.py`, a `Calibration` with one camera per video (the setup is static
  within a video). It is fitted from landmark clicks pooled from any frames of that video, using
  whichever known landmarks are visible: a floor homography from at least 4 floor points, and
  the pinhole refinement when wall-top or hive-frame points are also clicked. JSON read and
  write, and a `schema_version`. Each event gets its own calibration file.
- Out of scope for v1: a panning or zooming camera, frame-to-frame propagation of landmarks, and
  any extrapolation flag. A panning camera would need a separate decision.
- Tests: `tests/test_video_geometry.py`, `tests/test_video_landmarks.py`,
  `tests/test_video_calibration.py` (pooling clicks from several frames, JSON round-trip).
- Done when: on a synthetic 1080p broadcast camera with 10 landmarks and 1 px click noise, RMS
  reprojection is at most 1.5 px, floor position error at most 2 in, focal length within 3 %, and
  a point at z = 49 in within 2 in; fewer than 4 floor points, or collinear floor points, raise;
  landmark clicks taken from different synthetic frames of one video give the same calibration
  as clicks from a single frame; the suite stays green without the `video` extra
  (`pytest.importorskip("cv2")`). These synthetic targets are for a static camera; real
  livestream footage is measured in 2.4 and has wider error bars.
- Blocked on: 2.0 merged.

### 2.2: click log and review UI (`feature/2-click-log`)
- Deliver: `alea/video/frames.py`, `VideoReader` over `cv2.VideoCapture` (fps, frame count, seek
  by frame index, presentation time of each frame); `alea/video/clicklog.py`, JSONL read and
  write with a record type for each click kind: landmark clicks (frame, landmark id, `u_px`,
  `v_px`) and shot, robot and ball-track clicks (frame, `u_px`, `v_px`, presentation time).
  Landmark clicks feed the fit in 2.1. Clicks never bake in a calibration. Each video's metadata
  references one calibration JSON, and derived inches are never stored in the click log. Flat
  CSV export (`launches.csv`, `track_points.csv`) from the same records; `alea/video/review.py`
  and `alea/video/__main__.py`, a matplotlib UI run as
  `python -m alea.video review <video> --calibration cal.json --out shots.jsonl`, with keyboard
  modes for mark-landmarks, robot, launch, ball track, landing and outcome, plus undo and
  autosave after every record; the manual checklist goes in `alea/video/README.md`.
- Tests: `tests/test_video_clicklog.py`, `tests/test_video_frames.py`,
  `tests/test_video_review_ui.py`.
- Done when: a schema round-trip passes for every record type, and a mismatched `schema_version`
  is rejected; a landmark-click record and a shot record that cites a calibration JSON both
  round-trip, and no record stores inches; a 30-frame MJPG clip written at test time reads back
  with 30 frames and seeks to frame 17; the UI state machine passes injected matplotlib events on
  the Agg backend, including mark-landmarks; the user has run the manual checklist on a local
  clip.
- Blocked on: 2.0 merged. Can run in parallel with 2.1 in a separate worktree.

### 2.2b: match segmenter and overlay events (`feature/2-segment-schema`, `feature/2-overlay-reader`)
- Deliver: on `feature/2-segment-schema`, `alea/video/segments.py`, a JSON schema for match
  segments (match start and end, in seconds from the video's presentation timestamps) with read
  and write. On `feature/2-overlay-reader`, `alea/video/overlay.py`, which reads the on-screen
  score and tip events from a broadcast overlay. Both branches stack on `feature/2-click-log`.
  Decision 0012.
- Tests: `tests/test_video_segments.py`, `tests/test_video_overlay.py`, on a synthetic stream
  made at test time.
- Done when: on a synthetic stream every match start and end is within 1.5 s of the truth, the
  overlay tip events are recovered, and no real footage is committed.
- Blocked on: 2.2 merged (both branches stack on `feature/2-click-log`). No real footage needed.

### 2.3: ballistic fit, sync and efficiency (`feature/2-shot-fit`)
**Deprioritised, see decision 0009.** Calibration moves to the hive-shot-lab track in phase 3.
- Deliver: `alea/video/ballistics.py`, an image-space fit (unknowns: flight heading, launch
  point, two velocity components; gravity from `alea.game`; frame presentation times), soft
  priors from the log heading and the robot click, exit speed at the launcher-exit height with a
  1-sigma uncertainty, a linear-drag correction with `alea.game.AIR_DRAG`, and a ray-and-plane
  quick look as the starting guess; `alea/video/sync.py`, the offset between video time and log
  `t_s` from clicked launches and `alea.data.launches` results (1 ms scan, plus or minus 50 ms
  window, median refinement), a manual anchor fallback and an odometry cross-check;
  `alea/video/efficiency.py`, `efficiency_op` and `efficiency_phys` joined to `Launch` rows,
  written to `launches.csv`; and `python -m alea.video analyze shots.jsonl --log match.rlog
  --calibration cal.json`.
- Tests: `tests/test_video_ballistics.py`, `tests/test_video_sync.py`,
  `tests/test_video_efficiency.py`, `tests/test_video_end_to_end.py`. `/code-review` on the
  estimator.
- Done when: on 200 seeded synthetic trajectories at 30 fps, with 10 clicks, 1 px noise and a
  side-on camera, every exit-speed error is at most 3 % and the bias over the 200 is at most
  0.5 % (at most 6 % per trial at 2 px noise); the empirical scatter is within plus or minus 30 %
  of the predicted sigma; the degenerate view (ray within 10 degrees of the flight plane, 3 degree
  heading error) raises the warning and still fits within 3 %; sync recovers a known offset
  within 20 ms with one missed and one spurious launch; `launches.csv` has one row per launch with
  units in its column names.
- Blocked on: 2.1 and 2.2 merged.

### 2.4: operator guide (`docs/2-operator-guide`)
- Deliver: `docs/video-review.md` (what to record, which landmarks to click, the modes, what the
  CSV columns mean); a landmark diagram rendered from `alea.game` into `docs/assets/`
  (`field-landmarks.png`, well under 1 MB) by a script in `alea/video/tools/`; the nav entry in
  `mkdocs.yml`; the video line in `docs/knowledge-base.md` updated; `notebooks/video_review.py`
  (jupytext) plotting efficiency from synthetic data.
- Done when: `just docs` is clean, and a new operator can calibrate and log a synthetic clip
  from the guide alone.
- Blocked on: 2.3 merged.

### 2.5: video database (`feature/2-video-db`, later)
- Deliver: Alembic `0003_video.py` with `video_file`, `camera_calibration`, `shot_observation`,
  `ball_track_point` and `video_sync`; the edits to `alea/data/models.py` and `cli.py`;
  `python -m alea.data import-video shots.jsonl`; `alea/data/README.md` updated.
- Tests: `tests/test_video_db.py`.
- Done when: a JSONL from 2.2 and 2.3 imports and joins to `launch` rows, and re-import is
  idempotent (matched on sha256 and observation id).
- Blocked on: the user's go-ahead after the first real match is logged.

### 2.6: GPU tracking (`feature/2-tracking`, separate approval)
- Deliver: a uv dependency group `track` (torch, SAM 2) with Linux x86-64 platform markers, kept
  out of `just sync`, `--all-extras` and CI; `alea/video/track.py`, where SAM 2, seeded by the
  operator's first ball click, fills `ball_track` with `source: "sam2"`; `@pytest.mark.gpu`
  tests; a note in `hpc/brev/README.md`. Later: a detector for automatic launch detection.
- Tests: `tests/test_video_track_gpu.py`.
- Done when: on a GPU machine, a tracked ball matches hand clicks within one ball radius on a
  held-out clip; the CPU path is unchanged.
- Blocked on: the user's approval of the `uv.lock` change and of any GPU spend. Runs under the
  orchestrator only after its own approval.

### Re-scope 2026-11-08
Video review is now mainly for post-match reflection. A model reviews a match from the robot
logs, an overlay score timeline and a simulation baseline, and says what the drivers could have
improved. Launcher calibration is a separate, controlled track: a human slow-motion test, analysed
with the external tool hive-shot-lab (phase 3). Stage 2.3 is deprioritised. Phases 5, 6 and 7 get
their first stages. Reports are text and JSON only; no frames leave the machine. Data missing from
a report is tagged `inferred`. See decision 0009.

Every stage below runs on CPU with synthetic data. A large sweep goes on the GPU queue as its own
entry. Game point values are not in `alea/game/` yet; branches use documented placeholders until
a physics-reviewed PR adds them (open decision for the user).

Follow-up, not scheduled: `feature/2-field-extraction` (decision 0013). A local model extracts
field state from video (field mask, background model, robots, balls). A large model interprets it
and fills gaps as `inferred`. Blocked on a feasibility spike and the user's go-ahead.

### Phase 3-5: analysis

Phases 3 to 5 read robot logs and measured shots. They never change the frozen shot sim files.

#### 3.1: hive-shot-lab import (`feature/3-hivelab-import`)
- Deliver: `alea/analysis/hivelab.py`, an importer for the CSV that hive-shot-lab exports. The
  tool is external (Apache-2.0, v1.0.0) and is not vendored. The importer syncs video and log by
  a shared cue, or by matching burst gaps as a fallback. Measurement rows go to a separate file,
  `measurements.csv`. They never go into the launch table. Command:
  `python -m alea.analysis hivelab-import <csv> --log <log> --out measurements.csv`.
- Tests: `tests/test_analysis_hivelab.py`, on a synthetic CSV and a synthetic log.
- Done when: the synthetic CSV and log import with every shot matched to its cue; one missed and
  one spurious shot are reported, not dropped; a test shows the launch table is unchanged.
- Blocked on: nothing.

#### 3.2: efficiency estimate (`feature/3-efficiency-estimate`)
- Deliver: `alea/analysis/efficiency.py`, a bootstrap or Bayes estimate of launcher efficiency
  and of the drag term, from `measurements.csv`, with intervals. Efficiency is
  `v_exit_in_s / (flywheel_ticks_per_s / 28 * 2 * pi * 1.89)`. The estimate is compared with the
  sim's assumed 0.45 and with `AIR_DRAG` from `alea.game`. Output is a calibration report in text
  and JSON.
- Tests: `tests/test_analysis_efficiency.py`, on seeded synthetic shots with a known efficiency.
- Done when: on 100 seeded synthetic data sets, the 95 % interval covers the true efficiency in
  at least 93 of them; the report states whether 0.45 falls inside the interval.
- Blocked on: 3.1 merged. Any large seed sweep goes on the GPU queue.

#### 3.3: calibration protocol (`docs/calibration-protocol.md`, branch `docs/2-rescope`)
- Deliver: `docs/calibration-protocol.md`, the human slow-motion test for students and mentors:
  equipment, setup, filming checklist, sync cue, session sheet, file naming, the hive-shot-lab
  export, the import command, the efficiency formula, safety, privacy and troubleshooting. A nav
  entry under Guides.
- Tests: `just docs` (strict build).
- Done when: `just docs` is clean and a mentor can run one session from the page alone.
- Blocked on: nothing.

#### 4.1: driver critique (`feature/4-driver-critique`)
- Deliver: `alea/analysis/critique.py`, from robot logs only: cycle times, idle gaps between
  launches, shot cadence, and flywheel readiness (time from setpoint to ready before each launch).
  Output is a per-match CSV and a JSON summary, with units in the column names.
- Tests: `tests/test_analysis_critique.py`, on synthetic logs with planted idle gaps.
- Done when: every planted gap longer than 1.0 s is listed, and no other gap is.
- Blocked on: nothing. No video needed.

#### 5.1: match reflection (`feature/5-match-reflection`)
- Deliver: `alea/analysis/reflection.py`, a match timeline from the robot logs, the overlay
  score events from 2.2b and the sim baseline. It also writes the model prompt and a text and JSON
  report. Decision 0011 sets the prompt and report format. The prompt carries no image data.
  Missing items are tagged `inferred`.
- Tests: `tests/test_analysis_reflection.py`: the prompt has no image bytes; each missing item is
  tagged `inferred`; the JSON matches the report schema.
- Done when: a synthetic match gives a timeline and a report where every number names its source
  key, and a test fails if image bytes reach the prompt.
- Blocked on: 2.2b and 4.1 merged. The first live model call needs the user's go-ahead.

### Phase 6: web app

Streamlit, in `alea/web/`. The `web` extra already exists, so there is no dependency change.

#### 6.1: web skeleton (`feature/6-web-skeleton`)
- Deliver: `alea/web/app.py`, a Streamlit app with a shot-study explorer (reads `results/`) and a
  match and log viewer (reads the phase 0 database).
- Tests: `tests/test_web_smoke.py`, with `pytest.importorskip("streamlit")`, on a synthetic
  database.
- Done when: the app starts from a fresh clone and shows one study and one synthetic match.
- Blocked on: nothing beyond phase 0, which is merged.

#### 6.2: web video pages (`feature/6-web-video-pages`)
- Deliver: a read-only click-log viewer and calibration viewer in `alea/web/`. They read the
  JSONL click log and the calibration JSON. They never show footage.
- Tests: `tests/test_web_video.py`, on a synthetic click log.
- Done when: the viewer shows every record of the synthetic click log, and the calibration
  residuals.
- Blocked on: 2.2 and 6.1 merged.

#### 6.3: web reflection and efficiency (`feature/6-web-reflection-efficiency`)
- Deliver: a reflection report viewer (from 5.1) and a launcher-efficiency tracker over sessions
  (from 3.2).
- Tests: `tests/test_web_reflection.py`.
- Done when: the tracker plots efficiency per session with its interval and a line at 0.45, and
  the report viewer shows every `inferred` item in its own style.
- Blocked on: 3.2, 5.1 and 6.1 merged.

### Phase 7: match simulation

#### 7.1: match simulator core (`feature/7-matchsim-core`)
- Deliver: `alea/matchsim/core.py`, an abstract cycle-based match simulator on top of the shot
  sim. It has a pluggable shot-success model and a placeholder points table, documented in the
  branch and not in `alea/game/` (decision 0010). Every run is seeded.
- Tests: `tests/test_matchsim_core.py`.
- Done when: the same seed gives the same match; a match with no shots scores zero; every output
  labels the points table as a placeholder.
- Blocked on: nothing for placeholder runs. Real point values wait on the user's decision.

#### 7.2: match search (`feature/7-matchsim-search`)
- Deliver: `alea/matchsim/search.py`, a generic seeded optimiser for match plans. It has random
  search, grid search and cross-entropy.
- Tests: `tests/test_matchsim_search.py`, on a toy objective with a known maximum.
- Done when: each of the three methods finds the toy maximum within tolerance on fixed seeds.
- Blocked on: 7.1 merged.

## After setup: project phases

Each `alea/` subfolder belongs to a phase; its README says which.

| Phase | Area | Folder | Goal |
|---|---|---|---|
| 0 | Data contract | `robot/`, `alea/data/` | Every robot log and match result lands in one database |
| 1 | Shot simulator | `alea/sim/`, `alea/game/`, `conf/`, `hpc/` | Monte Carlo studies on Brev GPUs, results in notebooks |
| 1b | High fidelity | `alea/hifi/` | Port dsim hive tipping and ball contacts, validated against dsim traces |
| 2 | Video review | `alea/video/` | Camera calibration from field landmarks, click-and-log, exit speed and efficiency; tracking last, GPU only |
| 3-5 | Analysis | `alea/analysis/` | Calibrate the sim on real shots, driver critique, robot health |
| 6 | Web app | `alea/web/` | Streamlit for the team, FastAPI service later |
| 7 | Match simulation | `alea/matchsim/` | Full auto and match simulation on top of the shot sim |

**Phase 1b status (2026-11-08).** Merged: #33 (pin, inventory), #35 (2D traces), #36 (2D hive
logic), #37 (CAD evidence). In flight: `feature/1b-3d-port` (3D hive arithmetic and traces) and
`feature/1b-hifi-wire` (`fidelity: hifi` wiring, stacked on 3d-port). Remaining: the
engine/contacts decision for the user (Warp/NumPy rigid-body layer or stop at the table-driven
tip), and the open geometry and restitution items in `alea/hifi/PORTING.md`.

Phase work uses `feature/<phase>-<topic>` branches, one PR each. Large ports (the dsim port in
1b) are the kind of job `orchestrator` exists for, and only with the user's approval.

## Rules for agents using this file

- Pick work from the first row marked **next**. Do not start a PR whose "Blocked on" is not met.
- One PR per row. Do not fold a later PR's scope into an earlier one.
- When a PR merges, change its status and mark the following row **next**, in the same PR or
  right after it.
