from datetime import datetime
from pathlib import Path

import numpy as np

from timelapse.composer import _burn_timestamp


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
