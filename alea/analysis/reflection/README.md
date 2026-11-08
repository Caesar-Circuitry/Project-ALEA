# alea.analysis.reflection

Post-match reflection: build a structured timeline of one match from the robot log, overlay
score events and a sim baseline, then a prompt a large model can answer ("what could the drivers
improve?"). Design: [decision 0011](../../../docs/decisions/0011-match-reflection-pipeline.md).

**Roadmap phase:** 5

## Pipeline

```
robot log (.rlog/.wpilog) --> launches (alea.data.launches) + nearest Aim sample --+
overlay events (.jsonl)   --> score steps, tips, match clock -----------------------+--> MatchTimeline
                                                                                    |  (clock aligned)
sim baseline (summary.csv or placeholder) --> make probability by distance -------->+
                                                                                    v
                                              build_report -> report.json / report.md
                                              build_prompt -> prompt.txt  (text for a large model)
```

Nothing here calls a model or the network. You paste `prompt.txt` where you choose.

## Run

```
python -m alea.analysis.reflection <log> [--overlay-events x.jsonl] [--baseline summary.csv]
    [--alliance red] [--team 24331] [--label Q7] --out DIR
python -m alea.analysis.reflection --synthetic 3 --out DIR
```

`--alliance` is required with overlay events. Output: `report.json` (schema_version 1: match,
summary, metrics, timeline, findings, gaps), `report.md`, `prompt.txt`.

## Files

- `overlay_events.py`: JSONL reader/writer for overlay events and a seeded synthetic generator.
- `timeline.py`: `MatchTimeline`, `align_log_to_match`, idle gaps, cadence, phase constants.
- `baseline.py`: `Baseline` (from `alea.sim.results.load_summary`, read-only, or `placeholder()`)
  and `expected_points`.
- `report.py`: `build_report`, `validate_report`, `write_report`, `render_markdown`.
- `prompt.py`: `build_prompt`, `estimate_tokens`.

## Privacy

Inputs are logs, overlay-event JSONL and sim baselines only. No frames or images are read or
stored (minors appear on match video). The prompt holds the match label, alliance and team number
you pass and no file names or paths. Do not put names of people in `--label`.

## `inferred` tagging

Every metric, timeline entry and finding has `source`: `measured` (straight from a log value or
an overlay event) or `inferred` (anything filled in: placeholder baseline curve, log assumed to
start with the match, phases from nominal durations, a launch with no Aim sample). The `gaps`
list says what is missing and whether it was filled in.

## Needs real data

- A real log of a streamed match (launch detector thresholds and the 1 s score lag are tuned on
  synthetic data).
- Overlay events read from the user's clip (`alea.video.overlay`).
- A real study baseline; the study's `summary.csv` has no distance column, so only its level is used.
- Game values (2 points per made ball, 20 per tip, phase lengths) are placeholders until they
  move into `alea.game` through a physics-reviewed PR.
