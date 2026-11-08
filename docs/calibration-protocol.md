# Launcher calibration protocol

How to film one launcher shot so that `hive-shot-lab` can measure its exit speed.
Students and mentors run this. It takes about an hour per setup.

**Roadmap phase:** 3 (stage 3.3). The importer it uses is built in stage 3.1.

Decision: [0009](decisions/0009-reflection-first-rescope.md).

## Equipment

- A phone that films at 120 or 240 fps. Check the slow-motion setting before you start.
- A tripod.
- A green screen, or a plain backdrop with nothing yellow in it.
- One printed AprilTag, family `tag36h11`. Write its side length on the sheet, for example
  6.5 in. Measure it with a tape measure after printing. Do not trust the printer scale.
- A tape measure.
- Eye protection for everyone in the room.

## Setup

1. Put the camera square to the flight plane. The lens faces the side of the shot, not the
   front. Write the camera distance in inches on the sheet.
2. Put the tag in the ball plane, on the robot centreline.
3. Make sure nothing else in view is yellow. Remove yellow tape and yellow parts.
4. Use even light. Do not film against a window.
5. Clear the landing zone. Only the people running the test stand near the robot.

## Filming checklist

- [ ] Record the original file. Do not share a re-encoded copy.
- [ ] Write the fps and the resolution on the sheet.
- [ ] Shoot 10 to 20 shots per flywheel setpoint.
- [ ] Shoot in bursts of 1 to 3 shots, with a short pause between bursts.
- [ ] Note the hood angle for each setpoint.

## Sync cue

The video and the robot log must share one moment. Use one of these two methods.

1. **Preferred.** Clap, or flash an LED, where the camera can see it. At the same moment, put a
   marked event in the robot log. The log must contain `HardwareMap/launcher/velocity` and the
   `Alea/Aim/*` keys from [the robot interface](robot-interface.md).
2. **Fallback.** If there is no cue, the importer matches bursts by the gaps between shots.
   Write down that you used this method.

## Session sheet

Fill one sheet per session.

- Date (YYYY-MM-DD)
- Robot name
- Setup id (for example `S1`)
- Flywheel setpoints in ticks per second
- Tag side length in inches
- Camera distance in inches
- Camera fps and resolution
- Hood angle for each setpoint
- File names for the videos and the log

## File naming

Video files:

```
YYYY-MM-DD_<robot>_<setup>_<fps>fps_<nn>.mov
```

Example: `2026-11-14_starterbot_S1_240fps_03.mov`.

Save the robot log in the same folder, with the same date and setup in its name.

## Run hive-shot-lab and export the CSV

`hive-shot-lab` is an external tool (Apache-2.0, v1.0.0, github.com/boltonftc/hive-shot-lab).
Install it on your own computer. ALEA does not include it.

1. Open the video in `hive-shot-lab`.
2. Check the tag is found. Check the tag size matches the sheet.
3. Mark each shot.
4. Export the results as CSV.

## Import into ALEA

Run this from the repo root. The importer is built in stage 3.1
(`feature/3-hivelab-import`), so it may not exist yet on your copy.

```
uv run python -m alea.analysis hivelab-import <csv> --log <log> --out measurements.csv
```

The output goes to a separate `measurements.csv`. It never changes the launch table.

## Efficiency

For each shot:

```
efficiency = v_exit_in_s / (flywheel_ticks_per_s / 28 * 2 * pi * 1.89)
```

- `v_exit_in_s` is the measured exit speed in inches per second.
- `flywheel_ticks_per_s` is the launcher velocity from the log at the shot time.
- 28 is the ticks per revolution (1:1 drive, StarterBot launcher).
- 1.89 is the wheel radius in inches.

The sim assumes an efficiency of **0.45**. Stage 3.2 compares the measured value with 0.45.
A single session does not change the sim. Only a fit with an interval, reviewed by a person,
can.

## Safety

- Everyone wears eye protection.
- Keep the landing zone clear. Stand behind the robot, not in front.
- Stop the flywheel before you reach into the robot.

## Privacy

- Only team members appear in frame. Turn the camera away from spectators.
- Keep the footage on the team's machines. Do not upload it.
- Share only the CSV and the reports, never the video.

## Troubleshooting

- **The tag is not found.** Check the light. Check the tag is flat and in the ball plane.
- **The shot times do not line up with the log.** Use the burst-gap method and write it on the sheet.
- **The fps is wrong.** Check the phone setting. Re-shoot the session.
- **The tag size on the sheet does not match the measurement.** Measure the printed tag again.
  Use the measured value.
- **The log has no `HardwareMap/launcher/velocity` key.** Check the robot logging setup
  against [the robot interface](robot-interface.md).
