# alea/video/segment

Match segments: where each match sits in a local video file, who played, and how sure we are.
Schema, official-schedule loader and the bridge to the matches database.

**Roadmap phase:** 2 (stage 2.2b)

## What is here

| File | Purpose |
|---|---|
| `segments.py` | Match-segments schema v1 (frozen dataclasses, validation, atomic JSON write, flat CSV export). Raises `SegmentError`. |
| `schedule.py` | Reads a LOCAL FTCScout matches JSON; `label_for`, `expected_video_times`, `match_segments_to_schedule`, `fit_affine_utc_to_video`. No network. |
| `bridge.py` | `segments_to_matches_csv` (feeds `alea.data.matches.import_matches_csv`), `segment_for_label`, `segments_with_team`. |
| `__main__.py` | Standalone CLI. |

The overlay reader (clock glyphs, overlay events) lives in `alea/video/overlay/` and emits
segment dicts in this schema. See decision 0012.

## Schema (`kind: "match_segments"`, `schema_version: 1`)

Times are presentation times of the file (`*_pts_s`), like `t_pts_s` in the click log, and
`video.sha256`, `event.event_code`, `match_label` share the click-log names.

- `video`: `file, sha256, width_px, height_px, fps_nominal, duration_s, pts_origin`
- `event`: `event_code, season, schedule_source, schedule_sha256`
- `profile_id`, `diagnostics`
- `stream_clock` (or null): `stream_start_utc`, `affine_utc_to_video {a, b, n_anchors}` where
  `t_video_s = a * t_utc_s + b` and `t_utc_s` is seconds since `stream_start_utc`
- `segments[]`: `segment_id, match_label` (`Q6`), `match_label_raw`, `tournament_level, series,
  match_number, start_pts_s <= play_start_pts_s < play_end_pts_s <= end_pts_s`,
  `teams {red, blue}`, `score {red_final, blue_final}` or null, `schedule_match`,
  `confidence` in [0, 1], `needs_review`, `review {status, operator, changed_fields, original}`,
  `evidence` (free-form per-signal dict)

Playoff labels default to `SF1-2` (semis), `F1` (finals), `M3` (double elimination). This is a
proposal awaiting a user decision; pass `formats=` to `load_ftcscout_matches` to change it.

## CLI

```
python -m alea.video.segment list <segments.json>
python -m alea.video.segment validate <segments.json>
python -m alea.video.segment to-matches-csv <segments.json> <out.csv>
python -m alea.video.segment check-schedule <segments.json> <ftcscout.json>
```

`check-schedule` exits 1 if any segment disagrees with the schedule (label, team set, score) or
a played match has no segment.

To get a schedule file, once per event (the tool never fetches it):

```
curl -o ftcscout_CODE.json https://api.ftcscout.org/rest/v1/events/SEASON/CODE/matches
```

## Privacy and no-download rules

- Segment files hold team numbers, scores and times only (public data). No frames, no
  thumbnails, no audio.
- Footage shows minors: keep it local, never commit or upload it or frames from it.
- The tools take a local file. Do not download, scrape or capture streams; get the recording
  from the producer with permission.

## Needs real data

ROIs, clock glyphs and the overlay layout can only be tuned on a local stream file (the Athens
clip is on the user's machine only). Tests use synthetic data: `tests/data/ftcscout_sample_matches.json`
has invented teams 10001-10009 and invented times.
