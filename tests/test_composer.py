from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from timelapse.composer import _burn_timestamp, _downsample
from timelapse.extraction import ExtractedFrame


class TestBurnTimestamp:
    def test_returns_same_shape(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = _burn_timestamp(frame, datetime(2023, 6, 15, 14, 30))
        assert result.shape == frame.shape

    def test_modifies_pixels(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = _burn_timestamp(frame.copy(), datetime(2023, 6, 15, 14, 30))
        # The timestamp text should change some pixels
        assert not np.array_equal(result, frame)


class TestDownsample:
    def _make_frames(self, count: int) -> list[ExtractedFrame]:
        return [
            ExtractedFrame(
                image=np.zeros((10, 10, 3), dtype=np.uint8),
                timestamp=datetime(2023, 1, 1) + timedelta(hours=i),
                source=Path(f"/v/{i}.mp4"),
            )
            for i in range(count)
        ]

    def test_no_downsample_needed(self):
        frames = self._make_frames(5)
        result = _downsample(frames, 10)
        assert len(result) == 5

    def test_downsample_to_target(self):
        frames = self._make_frames(100)
        result = _downsample(frames, 10)
        assert len(result) == 10

    def test_preserves_temporal_order(self):
        frames = self._make_frames(100)
        result = _downsample(frames, 10)
        timestamps = [f.timestamp for f in result]
        assert timestamps == sorted(timestamps)
