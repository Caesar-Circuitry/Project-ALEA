"""Bridge from match segments to the existing match importer and robot-log lookups."""

from __future__ import annotations

import csv
from pathlib import Path

from alea.video.segment.segments import MatchSegment, SegmentError, SegmentFile

MATCHES_CSV_COLUMNS = ("event_code", "event_name", "label", "red_score", "blue_score")


def segments_to_matches_csv(
    segment_file: SegmentFile, path: Path | str, event_name: str = ""
) -> Path:
    """Write ``event_code,event_name,label,red_score,blue_score`` for ``import_matches_csv``.

    Scores are blank when a segment has none. Duplicate labels (a replay) raise, because the
    importer keys matches on (event, label); resolve them in review first.
    """
    labels = [s.match_label for s in segment_file.segments]
    dupes = sorted({lab for lab in labels if labels.count(lab) > 1})
    if dupes:
        raise SegmentError(f"duplicate match labels, resolve before export: {', '.join(dupes)}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(MATCHES_CSV_COLUMNS)
        for s in segment_file.segments:
            writer.writerow(
                [
                    segment_file.event.event_code,
                    event_name,
                    s.match_label,
                    "" if s.score is None else s.score.red_final,
                    "" if s.score is None else s.score.blue_final,
                ]
            )
    return path


def segment_for_label(segment_file: SegmentFile, label: str) -> MatchSegment | None:
    """The first segment with this ``match_label`` (None if absent)."""
    for s in segment_file.segments:
        if s.match_label == label:
            return s
    return None


def segments_with_team(segment_file: SegmentFile, team_number: int) -> list[MatchSegment]:
    """Segments in which ``team_number`` played, in video order."""
    hits = [s for s in segment_file.segments if s.has_team(team_number)]
    return sorted(hits, key=lambda s: s.play_start_pts_s)
