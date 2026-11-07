# EP Page 13: Simulation - Think (current text)

**Problem:** Robot time is limited, and testing every idea on the real robot is slow. Like NASA and Formula 1, we test in simulation first, so we catch bugs and make decisions with math before we ever touch the robot.

## How We Use Simulation

| Tool | Question | When | Process | Output |
| --- | --- | --- | --- | --- |
| Code Sim | "Does our code work?" | After every code change | Runs our real robot code in the sim | Bugs fixed before robot time |
| Project ALEA | "What's our best play?" | When the robot changes | Monte Carlo: 72M shots on GPU | Advice for drivers and designers |

## ALEA Results: Stop Before Launch

Heat-map titles: "Robot stopped: 87.6% of shots score" / "Robot still moving (10 in/s): 48.1% score"

72 million shots in 72 seconds on an NVIDIA L4 cloud GPU (72 conditions × 1,000,000 each). Shooting while moving drops scoring from 88% to 48%, so drivers stop before every shot. Flywheel error matters too: PIDF must hold within 2%. Our 1° aim tolerance and ball wear each cost under 1 point.

## Hood Angle Analysis

ALEA swept every reachable spot at every flywheel speed. A flat 36° shot scores from only 3 of 1,610 spots; our 72.2° curved hood scores from 1,000 (62%). Decision: keep the curved hood.

## Math: Projectile Motion

z(x) = h₀ + x · tan θ − g · x² / (2 · v² · cos² θ)

To score, the ball has to be coming down when it reaches the cell's mouth (53.5–65.6 in up). A 36° hood only gets it that high from 75+ in away. Ours does it from 24 in. Our hand math matched ALEA.

## Risk Mitigation & Lessons Learned

We only trust the sim when it matches reality. The field comes from FIRST's official CAD, and we checked our shots against match videos of other goBILDA StarterBots. Lesson learned: the videos showed robots scoring where our sim said they couldn't, which led us to a wrong hood angle. After fixing it, the sim matched the footage. ALEA also caught our robot firing from 2 spots that always miss, so we tightened our aim limit.

Suggested bold: FIRST's official CAD · match videos of other goBILDA StarterBots · Lesson learned: · wrong hood angle · the sim matched the footage · 2 spots that always miss · tightened our aim limit
