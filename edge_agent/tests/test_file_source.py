from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import pytest

from edge_agent.video.file_source import FileVideoSource


@pytest.fixture
def tiny_video(tmp_path):
    p = tmp_path / "t.avi"
    w = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48))
    if not w.isOpened():
        pytest.skip("no MJPG encoder available")
    for _ in range(5):
        w.write(np.zeros((48, 64, 3), dtype=np.uint8))
    w.release()
    return p


def test_file_source_timestamps_follow_video_time_base(tiny_video):
    t0 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    src = FileVideoSource(tiny_video, start_ts=t0)
    frames = list(src.frames())
    src.close()
    assert len(frames) == 5
    assert (frames[0].width, frames[0].height) == (64, 48)
    assert frames[3].ts == t0 + timedelta(seconds=0.3)
    assert frames[3].image.shape == (48, 64, 3)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        FileVideoSource(tmp_path / "nope.mp4")
