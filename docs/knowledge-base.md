# Project ALEA: Knowledge Base

Team 24331 Caesar Circuitry · FTC season BIOBUZZ (2026–27) · last updated 2026-11-06

This is the master reference for Project ALEA. The code is in `alea/`, and the judge-facing write-up is the [technical binder](technical-binder.md).

---

## 1. What ALEA is

**Project ALEA** is the team's own Monte Carlo shot simulator. It runs a huge number of robot launches, each with small random errors like a real robot has, and counts how many score. It runs on an NVIDIA GPU.

- **Name:** *alea* is Latin for "dice", as in Caesar's "alea iacta est" ("the die is cast"). It fits the team name, and it describes the method: roll the dice millions of times and count.
- **Who built it:** the team (with AI coding assistance). It is the team's own tool. dsim and FTCodeSim are community tools.
- **Headline number:** **72 million launches in 72 seconds** on one NVIDIA L4 cloud GPU (rented through NVIDIA Brev). The full run, including setup and self-test, was 9 min 52 s.

### The three simulation tools

| Tool | Made by | Question it answers | When it runs |
| --- | --- | --- | --- |
| dsim | Community (genius0412, github.com/genius0412/dsim) | "Can our drivers handle the field?" | Driver practice |
| Code Sim | FTCodeSim (community) + the team's BIOBUZZ field physics | "Does our code work?" | After every code change (constant validation) |
| **Project ALEA** | **The team** | "What's our best play?" | When the robot or strategy changes (recommendations for drivers and designers) |

Both the Code Sim and ALEA use one field model built from FIRST's official field CAD. ALEA's physics was copied from the Code Sim and verified shot by shot against it.

---

## 2. How it works

Each simulated launch (one GPU thread) does what the robot's TeleOp code does:

1. **Pick a spot** at random on the red alliance half of the field (x 8.9–132.4 in, y 8.9–70.75 in) where the robot can actually stand (not on the hive frame's base rails; robot treated as a 17.8 in square).
2. **Aim** like `aimAssist`: point at the red-audience cell mouth target (58.0, 54.47). Distance = robot centre to target minus 6.1 in.
3. **Pick speed** from the lookup table (`launchLUT`), linear interpolation.
4. **Hold fire** if distance is outside the LUT (24–80 in) or the robot is more than 80° off-axis from straight out of the cell.
5. **Add error:** random aim error, flywheel speed error, optional robot motion (random direction).
6. **Fly the ball:** gravity, air drag, 2 ms steps, collisions with the hive cells (floor, side walls, peaked roof, pivot-side end wall, centre beam), the hive support frame (1-inch cubes from CAD), and the field walls.
7. **Count:** tries / fired / scored are added into a 2-inch heat-map grid on the GPU with atomic adds.

### Physics constants (BioBuzzConfig / SimLauncherConfig)

| Constant | Value |
| --- | --- |
| Field size | 141.3 in (Pedro coordinates, inches) |
| Field wall height | 11.64 in |
| Gravity | 386.09 in/s² |
| Air drag | 0.05 per second |
| Time step | 0.002 s, up to 1000 steps (2 s) |
| Ball (pollen) radius | 1.4 in (2.8 in diameter) |
| Restitution off hive/frame | 0.45 |
| Hive pivot height | 43.95 in |
| Hive rest tilt | 30° |
| Red hive pivot x / blue hive pivot x | 58.0 / 83.5 in, y 70.75 in |
| Cell along range | 9.38–21.46 in from pivot |
| Cell mouth height (raised cell) | 53.5–65.6 in off the floor |
| Launch (hood) angle | **72.2°** (measured in Onshape on the curved plate) |
| Launcher exit | 6.1 in behind robot centre (out the back), 8.5 in high |
| Ball speed from flywheel | v = ticks/s ÷ 28 × 2π × 1.89 in × 0.45 |

Only the **raised** cell can hold balls (the lowered cell can't; balls roll out). The goal is to tip the hive by filling the raised cell (official tip table: tipPollenByNectar {8,7,6,3,1,0}).

### Parallelism (how the GPU is used)

- One GPU thread = one complete shot. Shots are independent ("embarrassingly parallel").
- 1,000,000 threads launched per condition; 72 launches total.
- Each thread seeds its own random generator from the run seed + thread ID, so shots differ but the run is repeatable.
- Field data (hive boxes, frame cubes) is read-only shared memory.
- Results are counted on the GPU with atomic adds; only the small heat-map grid is copied back.
- NVIDIA L4: 7,424 CUDA cores, 58 SMs, up to ~89,000 threads in flight at once.
- Inefficiency: threads in a 32-thread warp wait for the slowest shot (held shots finish instantly, lobs take ~2 s simulated).

---

## 3. Validation (how we know it's right)

| Check | Against | Result |
| --- | --- | --- |
| Field geometry | FIRST official field CAD + game manual | Cell mouth within 0.13 in |
| Field geometry | dsim's CAD numbers | Agree |
| Real shots | Match videos of other teams' goBILDA StarterBots | Sim matched the footage (after the hood fix) |
| GPU physics | Java Code Sim, shot by shot (incl. moving robot, 2.9 in ball, 0.6 bounce) | 10,000 / 10,000 identical |
| Grid sweep | Java LutSweep, 16,160 shots | 105 / 105 scoring spots agree |
| Aim logic | Real robot code (`aimAssist` + `launchLUT`) | 4,000 / 4,000 spots identical |
| Randomness | Configured error sizes | Correct means and standard deviations |
| Counting | Recount of every shot | Exact |
| Repeatability | Same seed twice; CPU vs GPU | Identical; 87.7% vs 87.6% |

**Self-test:** `run_study.py` runs `selftest.py` first on the GPU against 10,000 saved Java answers (`golden_shots.npy`). Below 99.9% agreement it refuses to run.

---

## 4. The 72-million-shot study (Brev run)

72 conditions (3 × 3 × 2 × 2 × 2) × 1,000,000 shots each. **Bold** = the "normal" robot.

| Variable | Values |
| --- | --- |
| Aim error (1 s.d.) | 0.5°, **1°**, 2° |
| Flywheel speed error (1 s.d.) | 1%, **2%**, 3% |
| Robot moving when it shoots | **0**, 10 in/s |
| Ball diameter | **2.8 in**, 2.9 in |
| Ball bounce (restitution) | **0.45**, 0.60 |

Error sizes are team estimates, not measured. Each condition's hit rate is accurate to about ±0.1 points (95%).

### Key results (% of fired shots that score)

| Condition (one change from normal) | Score |
| --- | --- |
| Flywheel error 1% | 90.6% |
| Aim error 0.5° | 88.3% |
| **Normal robot** | **87.6%** |
| Bouncier ball (0.60) | 87.6% |
| Bigger ball (2.9 in) | 87.3% |
| Aim error 2° | 82.7% |
| Flywheel error 3% | 78.1% |
| **Moving at 10 in/s** | **48.1%** |
| Best condition (0.5°, 1%, stopped) | 91.0% |
| Worst condition | 41.7% |
| From the auto start pose (56, 10.5) | 97.5% |

The robot fires (in range and inside the aim cone) from about 56% of random field spots.

### Decisions made from ALEA

| Finding | Decision |
| --- | --- |
| Moving at 10 in/s cuts scoring nearly in half (87.6% → 48.1%) | Drivers stop before every launch |
| 3% flywheel error costs about 10 points | PIDF must hold within 2% |
| 0.5° aim is under 1 point better than 1° | Keep the faster 1° aim tolerance |
| Ball size/bounce change results by under 1 point | No special handling for worn balls |
| 97.5% from the start pose | Keep the auto start pose |
| 36° hood scores from 3 of 1,610 spots; 72.2° from 1,000 (62%) | Keep the curved hood |
| Robot fires from 2 strips near the hive's front corners where every shot misses (7% of fired shots) | Tighten the aim limit near the hive (projected 88% → 94%) |

### Hood angle sweep

Every reachable spot (1,610), every flywheel speed 600–2800 ticks/s, perfect aim. Spots where at least one speed scores:

| Hood angle | 36° | 45° | 55° | 65° | 72.2° (ours) |
| --- | --- | --- | --- | --- | --- |
| Scoring spots | 3 | 114 | 381 | 734 | 1,000 |

Hand math: to score, the ball must be coming down at the cell mouth (53.5–65.6 in up). A 36° shot only gets that high from 75+ in away; 72.2° from 24 in.

### Speed comparison

| Setup | 72 million shots |
| --- | --- |
| NVIDIA L4 GPU | 72 s (~1,000,000 shots/s) |
| ALEA code, 1 CPU core | ~1.4 h (~14,000 shots/s, estimated) |
| ALEA code, 8-core laptop | ~11 min (estimated) |
| Original Java simulator, 1 core | ~25 h (estimated) |

---

## 5. Lookup table (LUT)

Current table in `constants.java` (distance = robot centre to target minus 6.1 in):

```
LUT_DISTANCE_IN   = {  24,   28,   32,   36,   40,   44,   48,   52,   56,   60,   64,   68,   72,   76,   80}
LUT_TICKS_PER_SEC = {1180, 1110, 1100, 1100, 1120, 1140, 1160, 1180, 1200, 1230, 1260, 1290, 1310, 1340, 1360}
```

Update proposed from the old 72.2° sweep data (perfect aim, 4-inch grid):

```
LUT_TICKS_PER_SEC = {1160, 1120, 1120, 1120, 1120, 1140, 1160, 1200, 1220, 1240, 1280, 1300, 1320, 1360, 1380}
```

Brev hit rate with the current table, by distance: 24 in 46%, 28 in 70%, 32 in 85%, 36–48 in 91–95%, 52–80 in 88–96%. The close-range problem is the aim cone, not the speed.

A dedicated ALEA LUT study (same 1,500 realistic shots fired at every speed 900–1800 at each distance 20–90 in) was started on 2026-11-06; its results replace this section when done.

---

## 6. Math

- **Projectile motion:** z(x) = h₀ + x · tan θ − g · x² / (2 · v² · cos² θ), with h₀ = 8.5 in, g = 386 in/s².
- **Monte Carlo accuracy (95%):** ± 1.96 × √( p × (1 − p) / n ). About 1,000 shots per heat-map spot gives ±3% per spot; a whole condition (~560,000 fired shots) gives ±0.1 points.
- **Why 1,000,000 per condition:** ~1,000 spots × ~1,000 shots per spot. More shots don't make the answer more true; the bigger uncertainty is model vs. real robot.
- **Ball speed:** v = (ticks/s ÷ 28) × 2π × 1.89 in × 0.45.

---

## 7. Limits

- No other robots or balls, no hive swinging (held at rest), no flywheel spin-up timing.
- Floor or wall contact = miss (a ball that touches either can't get back up to the cell).
- Robot treated as an axis-aligned square for where it can stand.
- Error sizes are estimates; measuring them on the robot is a next step.
- Studies so far: red alliance, raised audience cell only.
- Random numbers: Warp's 32-bit generator; ~100 repeated shots per million (0.01%), negligible.

---

## 8. Lessons learned (building the sim)

| What went wrong | How we caught it | What we changed |
| --- | --- | --- |
| First model said the robot couldn't score at all | Match videos showed StarterBots scoring | Had modeled the wrong part (flat 36° plate); measured the real 72.2° curved hood in Onshape; sim then matched the videos |
| Shots scored that shouldn't have | Balls bounced back off a field wall with no top | Gave walls their real 11.64 in height |
| Sim let the lowered cell hold balls | Re-read the game manual | Only the raised cell holds balls; cells rebuilt as house shapes open at the outer end |
| Robot fires from 2 spots that always miss | Red strips on the ALEA heat map | Tighten the aim limit near the hive |

Biggest takeaway: a simulation is only as good as its validation.

---

## 9. How to run ALEA on NVIDIA Brev

1. Sign up at brev.nvidia.com; add payment/credits.
2. Mac: `brew install brevdev/homebrew-brev/brev` then `brev login`.
3. Create instance: 1× L4 (cheapest option, ~4 vCPU / 16 GB is plenty), **VM mode**, no startup script, name `alea`. Then `brev refresh`, `brev ls`.
4. Upload: `brev shell alea` → `mkdir -p ~/workspace && exit`; then `brev copy alea_gpu_study.zip alea:/home/ubuntu/workspace/`.
5. Setup (on the machine): `sudo apt-get update -y && sudo apt-get install -y unzip zip tmux python3-venv`; `cd ~/workspace && unzip alea_gpu_study.zip && cd alea_gpu_study && ./setup_brev.sh` (must print "OK: Warp sees NVIDIA L4").
6. Run: `tmux new -s alea`; `source .venv/bin/activate`; `python run_study.py --plan`; `python run_study.py` (must show SELF-TEST PASSED).
7. Results: `zip -r results.zip results`; on the Mac `brev copy alea:/home/ubuntu/workspace/alea_gpu_study/results.zip ~/Desktop/`.
8. Shut down: `brev delete alea` (or `brev stop alea`).

Edit `conditions.py` to change the study. Results: `summary.csv`, `heatmap_normal.png`, `heatmap_worst.png`, `effects.png`, `cond_XXX.npz`.

---

## 10. Future work and ideas

- Fix the aim limit near the hive; re-run to confirm ~94%.
- Real-robot test: 20 shots stopped vs. 20 moving, compare to 87.6% / 48.1%.
- Measure real aim and flywheel error; re-run with measured values.
- 2D lookup table (distance × angle); both hives and cells.
- Random-sampling design (all variables random per shot) + sensitivity analysis instead of full grids.
- Speed-ups: early exit for clear misses, skip frame checks far from the frame, multi-GPU split by condition.
- Bigger compute: Alabama Supercomputer Authority (free for Alabama public institutions; A100/H100 GPUs) when studies grow to billions of shots.
- Full autonomous-routine Monte Carlo.
- Match video analyzer: click-and-log (v1, a weekend) → SAM 2 tracking (v2) → auto launch detection (v3), possibly using Hive Vision's pollen detector (hivevision.dev) or Isaac Sim synthetic training data.
- Quantum computing: not useful here (the run already takes 72 s; real uncertainty is model vs. robot).

---

## 11. Glossary

| Term | Meaning |
| --- | --- |
| Monte Carlo | Repeating a random experiment many times and counting outcomes |
| LUT | Lookup table: flywheel speed for each shooting distance |
| PIDF | Controller that holds the flywheel at target speed |
| GPU | Graphics processor: thousands of small calculations at once |
| Kernel | A GPU function that runs as many parallel copies |
| Atomic add | A safe way for many threads to add to one counter |
| Homography | Math that maps video pixels on the floor to field inches |
| NVIDIA Brev | NVIDIA's cloud GPU rental service |
| NVIDIA Warp | Python library for writing GPU physics kernels |
