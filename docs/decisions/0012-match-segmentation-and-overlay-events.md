# 0012: Match segmentation and overlay events

Status: proposed, 2026-11-08. Roadmap phase 2, stage 2.2b.

## Context

Event livestreams are hours long and hold perhaps one hour of match play. The click log needs
to know, for each match, where it starts and ends in the video, who played, and which `Match`
row it belongs to. A wrong boundary silently misaligns every launch in the join with the robot
log. The streams carry a fixed broadcast overlay with a large match clock, the match label,
team numbers and scores. The official schedule (FTCScout, or the FIRST Events API) lists
teams, scores and wall-clock start times, but not video positions. The footage shows minors,
and platform terms restrict downloading.

## Decision

- **Primary detector: a clock-driven ROI reader.** Read the overlay clock in a configured
  region by glyph template matching and fit video time against the falling clock. This gives
  sub-second boundaries even from sparse sampling. Label, teams and scores come from the same
  overlay.
- **The official schedule is a prior and a validator, not a source of boundaries.** It is read
  from a local JSON file. Its `actualStartTime` predicts where to look; label, team set and
  final scores are compared with what the overlay says, and disagreements are reported, never
  silently corrected. An affine map from wall-clock to video time is fitted from confirmed
  matches, and a jump larger than 30 s flags a stream restart.
- **Never download or scrape streams.** Tools take a local file path only. There is no URL
  option and no yt-dlp integration. Fetching a schedule is a separate, explicit, one-request
  action and is not part of any test or default path.
- **Local-only footage and thumbnails.** Minors are visible. Footage, frames, thumbnails and
  audio clips are never committed or uploaded. Segment files hold team numbers, scores and
  times only.
- **Shared conventions with the click log.** The segment schema uses `video.sha256`
  (`video_sha256` in CSV), `event_code`, `match_label` and `*_pts_s` presentation times, plus
  `schema_version` with a hard mismatch error. `needs_review` and `review.original` keep a
  human in the loop.
- **Overlay events** are emitted as JSONL by the overlay reader (research note section 2.5:
  clock value, overlay-present flag and other per-sample observations with confidence), and a
  later fusion step turns them into segments. Segments emitted by the reader use this schema.
- **Bridge to the database** reuses `alea.data.matches.import_matches_csv` through a small CSV
  writer instead of adding a second importer.

Open user decision: the playoff label convention in `Match.label`. The proposed default is
`Q6`, `SF1-2`, `F1`, `M3`; see `alea/video/segment/schedule.py`.

## Consequences

- Streams without the overlay clock produce no automatic segments. Fallbacks (schedule-only
  windows plus a human click) are slower but possible.
- Tuning the ROIs and glyphs needs a real local stream; CI uses synthetic data only.
- Every segment is reviewable and every schedule disagreement is visible, at the cost of an
  operator pass per event.
- The segment schema becomes a contract: changing it needs a new `schema_version`.
