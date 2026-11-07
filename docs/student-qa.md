# Project ALEA: Student Q&A prep

Short answers to the questions judges are most likely to ask.

**"Why did you build your own tool?"**
No existing tool could tell us how often our robot scores under real-world error. dsim is for driving, and the Code Sim tests one run at a time. We needed millions of shots.

**"How do you know it's right?"**
We checked every layer: the field against FIRST's CAD (within 0.13 in), the sim against match videos of other StarterBots, and the GPU version against our Code Sim on 10,000 of 10,000 shots. It won't even run unless it passes a self-test.

**"Why a million shots?"**
We wanted each heat-map spot accurate to about ±3%. That takes about 1,000 shots per spot, and there are about 1,000 spots. More shots wouldn't make the answer more true.

**"Why a GPU?"**
Every shot is independent, so a GPU can fly thousands at once. Our 72 million shots took 72 seconds on one NVIDIA L4, about a million shots per second. The same code on one CPU core would take about 1.5 hours, and our original Java simulator about a day.

**"How does it use the GPU?"**
Each shot gets its own GPU thread. We launch a million at a time; each has its own random errors, and they add their results straight into a shared heat map.

**"What's Monte Carlo?"**
Running a situation many times with random variation and counting the outcomes, like rolling dice millions of times to learn the odds. That's where the name ALEA (Latin for "dice") comes from.

**"What did ALEA change?"**
Drivers stop before every shot, our PIDF has to hold the flywheel within 2%, we kept the curved hood and our 1° aim tolerance, and we found a bug in our aim limit.

**"What would you improve?"**
Measure our real aim and flywheel error instead of estimating them, confirm the results with real shots, and extend ALEA to full autonomous routines.

**"What doesn't it model?"**
Robot timing, other balls and robots, and the hive swinging. None of these change whether a single shot scores.

**"Would a supercomputer or quantum computer help?"**
Not for this study: it already takes 72 seconds. A supercomputer would help when we add many more variables. Our real uncertainty is how well the model matches the robot, which only testing fixes.
