# 0001: Scope and stack

**Status:** accepted, 2026-11-07

## Context

Team 24331 needed to know how often its robot scores under real-world error. Practice shots
cannot answer that, dsim is for driving and the Java Code Sim tests one run at a time. The
first ALEA results (72 million shots in 72 seconds on one GPU) came from a Warp simulator that
agrees with the Code Sim on 10,000 of 10,000 golden shots.

## Decision

- ALEA is a Python 3.12 platform in `alea/`, with the shot simulator on NVIDIA Warp. It also
  runs on CPU so every platform can develop and test it.
- Physics stays identical to the Java Code Sim. `tests/golden/golden_shots.npy` holds the Java
  answers and the self-test must agree on at least 99.9 % of them.
- Game values live only in `alea/game/`. Java lives only in `robot/`.
- The platform grows in phases (match data, robot logs, video review, driver critique, match
  simulation, web app), each in its own `alea/` subfolder.
- Source of truth for numbers and results is the [knowledge base](../knowledge-base.md).
  Results are simulated, and error sizes are estimates, until confirmed on the real robot.

## Consequences

- Any physics change needs the self-test and a physics review.
- CPU and GPU share one code path, so CI can check it without a GPU.
- Later decisions (0002 onward) refine this one.
