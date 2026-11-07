# Project ALEA: Technical Binder

Team 24331 Caesar Circuitry

We built **Project ALEA** because some questions just can't be answered with a few practice shots. So we wrote our own simulator, ran **72 million shots in 72 seconds** on an NVIDIA GPU, and let the data settle it. It ended up changing four things about how we play:

- Our drivers now **stop before every shot**. Moving while shooting dropped us from 88% to 48%.
- Our flywheel controller has to hold speed **within 2%**, or we start missing.
- We **kept our curved 72.2° hood**. It can score from 1,000 spots on the field; a flat one, from just 3.
- We found an **aim bug**: two spots where our robot fires but never scores.

## Why we built it

Robot time is precious, and ten practice shots can't tell you how often you'll score in a real match, with real aim error and a flywheel that's never perfectly on speed. We were already using two great community tools, but neither one answers that question. So we made our own.

| Tool | Who made it | What we use it for |
| --- | --- | --- |
| dsim | The FTC community | Driver practice |
| Code Sim (FTCodeSim) | The community, plus our field physics | Testing our code after every change |
| **Project ALEA** | **Us** | **Figuring out what actually scores** |

We named it *Alea*, Latin for "dice", after Caesar's famous line "the die is cast". It fits our team name, and it's basically what ALEA does: roll the dice millions of times and count how often we score.

## How it works

ALEA is a **Monte Carlo** simulation. Instead of calculating one perfect shot, it takes a huge number of slightly imperfect ones and counts how many go in. Every simulated shot follows the same steps our real robot does:

1. **Pick a spot** somewhere on our side of the field where the robot could actually be.
2. **Aim** at the hive and look up the flywheel speed in our lookup table, just like our TeleOp code. If the robot's out of range, it holds fire.
3. **Add some real-world mess:** a little aim error, a little flywheel error, and sometimes the robot still moving.
4. **Fly the ball** with gravity and air drag, bouncing off a hive we built from FIRST's official field CAD.
5. **Count it**, and add it to a field map of where we score.

We tested **72 different versions of our robot** (more or less aim error, flywheel error, moving or not, bigger or bouncier balls) with **a million shots each**. On a rented NVIDIA L4 GPU, the whole simulation took 72 seconds. That's about a million shots per second. (The full run was 9 min 52 s once you count setup and the self-test.)

## Results

The big surprise was how much moving hurts. Every other kind of error cost us 10 points or less, but shooting on the move cut our scoring almost in half.

| One change from our normal robot | Shots that score |
| --- | --- |
| Flywheel error 1% | 90.6% |
| Aim error 0.5° | 88.3% |
| **Normal robot** | **87.6%** |
| Bouncier ball (0.60) | 87.6% |
| Bigger ball (2.9 in) | 87.3% |
| Aim error 2° | 82.7% |
| Flywheel error 3% | 78.1% |
| **Moving at 10 in/s** | **48.1%** |

| What ALEA told us | What we did about it |
| --- | --- |
| Moving at 10 in/s cuts our scoring nearly in half | Our drivers stop before every shot |
| 3% flywheel error costs us about 10 points | We tune our PIDF to hold within 2% |
| Aiming within 0.5° is barely better than 1° | We kept our faster 1° aim tolerance |
| Worn or bouncier balls hardly matter | We don't worry about them |
| 97.5% of shots from our auto start pose score | We kept our start pose |
| A flat 36° hood scores from 3 spots; ours from 1,000 of 1,610 | We kept our curved hood |
| Our robot fires from 2 spots where it always misses | We're tightening our aim limit (should take us from 88% to 94%) |

## How we know it's right

A simulator is only useful if you can trust it, so we checked ALEA against something real at every step.

| What we checked | How | What we found |
| --- | --- | --- |
| The field | Compared it to FIRST's official CAD and the game manual | Within 0.13 in |
| Real shots | Watched match videos of other teams' goBILDA StarterBots | Our sim matched the footage |
| The GPU version | Ran the same shots through it and our Code Sim | 10,000 out of 10,000 matched |
| The aiming | Compared it to our actual robot code | 4,000 out of 4,000 matched |
| Consistency | Ran it twice, and on a laptop vs. the GPU | Same answers (87.7% vs. 87.6%) |

We also made ALEA test itself before every run. If it ever disagrees with our Code Sim, it refuses to start.

## The math

**Will the ball get there?** Before trusting ALEA, we did the projectile math by hand. Here h₀ is the launch height (8.5 in), θ is the hood angle and v is the launch speed:

**z(x) = h₀ + x · tan θ − g · x² / (2 · v² · cos² θ)**

For a shot to go in, the ball has to be coming down when it reaches the cell's mouth, 53.5 to 65.6 in off the ground. A flat 36° hood only gets the ball that high from 75+ in away. Our 72.2° hood does it from just 24 in. ALEA found the same thing.

**How many shots is enough?** If you measure a hit rate p from n shots, your answer is accurate to about:

**± 1.96 × √( p × (1 − p) / n )**

We wanted every spot on our field map to be right within about 3%. That takes about 1,000 shots per spot, and our side has about 1,000 spots, so we ran a million shots per version of the robot. Running more wouldn't make the answer more true; checking it against reality does.

## Limits and lessons learned

ALEA isn't the real robot, and we know it. It doesn't simulate other robots or balls, the hive swinging, or the flywheel spinning up. None of those change whether one shot goes in, so we left them out to keep it fast. The error sizes we tested are our best estimates, and measuring them on our robot is next on our list.

We also made plenty of mistakes building it, and every one taught us something:

| What went wrong | How we noticed | What we changed |
| --- | --- | --- |
| Our first model said we **couldn't score at all** | We'd watched StarterBots score in match videos | We'd modeled the wrong part. We measured the real **72.2° hood** in Onshape, and then the sim matched the videos |
| The sim let the **lowered cell** hold balls | We re-read the game manual | Now only the raised cell holds balls |
| Our robot fired from **2 spots where it always misses** | We spotted red strips on ALEA's field map | We're tightening our aim limit near the hive |

**Our biggest takeaway:** a simulation is only as good as its validation. Every bug we found, we found by comparing the model to something real.

**What's next:** test the results on our own robot (shooting stopped vs. moving), then use ALEA to plan full autonomous routines.
