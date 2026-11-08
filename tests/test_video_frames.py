"""VideoReader on a synthetic MJPG clip written at test time (phase 2)."""

import itertools

import numpy as np
import pytest

from alea.video.frames import (
    VideoError,
    VideoReader,
    analyze_timestamps,
    file_sha256,
    nearest_frame,
)

cv2 = pytest.importorskip("cv2")

N_FRAMES = 30
FPS = 30.0
W, H = 64, 48


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (W, H))
    if not writer.isOpened():
        pytest.skip("OpenCV build has no MJPG writer")
    for i in range(N_FRAMES):
        img = np.full((H, W, 3), i * 8, dtype=np.uint8)  # brightness encodes the frame index
        writer.write(img)
    writer.release()
    return path


def test_reports_size_count_fps(clip):
    with VideoReader(clip) as r:
        assert (r.info.width_px, r.info.height_px) == (W, H)
        assert r.frame_count == N_FRAMES
        assert r.info.fps_nominal == pytest.approx(FPS)


def test_seek_reads_requested_frame(clip):
    with VideoReader(clip) as r:
        f17 = r.read(17)
        assert f17.index == 17
        assert f17.image_bgr.shape == (H, W, 3)
        assert abs(float(f17.image_bgr.mean()) - 17 * 8) < 12  # JPEG tolerance
        assert f17.t_pts_s == pytest.approx(17 / FPS, abs=0.5 / FPS)
        assert r.read(2).index == 2  # backwards seek


def test_out_of_range(clip):
    with VideoReader(clip) as r:
        with pytest.raises(IndexError):
            r.read(N_FRAMES)
        with pytest.raises(IndexError):
            r.read(-1)


def test_timestamps_table(clip):
    with VideoReader(clip) as r:
        ts = r.timestamps_s()
        assert len(ts) == N_FRAMES
        assert all(b > a for a, b in itertools.pairwise(ts))
        stats = r.timestamp_stats()
        assert not stats.variable_frame_rate
        assert stats.fps_median == pytest.approx(FPS, rel=0.02)
        assert r.frame_at_time(ts[10]) == 10


def test_missing_and_corrupt(tmp_path):
    with pytest.raises(VideoError, match="does not exist"):
        VideoReader(tmp_path / "nope.mp4")
    bad = tmp_path / "bad.avi"
    bad.write_bytes(b"not a video")
    with pytest.raises(VideoError):
        VideoReader(bad)


def test_sha256(clip):
    with VideoReader(clip) as r:
        assert r.sha256() == file_sha256(clip)
        assert len(r.sha256()) == 64


# --- pure timestamp helpers (no video needed) -------------------------------------------------


def test_analyze_constant_rate():
    stats = analyze_timestamps([i / 30 for i in range(60)])
    assert not stats.variable_frame_rate
    assert stats.fps_median == pytest.approx(30.0)
    assert stats.n_duplicate == 0


def test_analyze_variable_rate_with_duplicate():
    t = [0.0, 0.033, 0.066, 0.066, 0.1, 0.2, 0.233]
    stats = analyze_timestamps(t)
    assert stats.variable_frame_rate
    assert stats.n_duplicate == 1


def test_nearest_frame():
    t = [0.0, 0.1, 0.25, 0.5]
    assert nearest_frame(t, -1.0) == 0
    assert nearest_frame(t, 0.12) == 1
    assert nearest_frame(t, 0.2) == 2
    assert nearest_frame(t, 9.0) == 3
    with pytest.raises(ValueError):
        nearest_frame([], 0.0)
