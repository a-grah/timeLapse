from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from timelapse.extraction import extract_frames, _VideoHandle
from timelapse.sampling import SamplePlan


class TestVideoHandle:
    def test_reuses_same_path(self):
        with patch("timelapse.extraction.cv2") as mock_cv2:
            cap = MagicMock()
            mock_cv2.VideoCapture.return_value = cap
            cap.isOpened.return_value = True
            cap.get.return_value = 100.0

            handle = _VideoHandle()
            path = Path("/videos/test.mp4")

            handle.get(path)
            handle.get(path)  # same path, should reuse

            # VideoCapture should only be called once
            mock_cv2.VideoCapture.assert_called_once()
            handle.close()

    def test_closes_old_on_new_path(self):
        with patch("timelapse.extraction.cv2") as mock_cv2:
            cap1 = MagicMock()
            cap1.isOpened.return_value = True
            cap1.get.return_value = 100.0
            cap2 = MagicMock()
            cap2.isOpened.return_value = True
            cap2.get.return_value = 50.0
            mock_cv2.VideoCapture.side_effect = [cap1, cap2]

            handle = _VideoHandle()
            handle.get(Path("/videos/a.mp4"))
            handle.get(Path("/videos/b.mp4"))  # new path

            cap1.release.assert_called_once()  # old handle closed
            handle.close()

    def test_returns_none_on_bad_file(self):
        with patch("timelapse.extraction.cv2") as mock_cv2:
            cap = MagicMock()
            mock_cv2.VideoCapture.return_value = cap
            cap.isOpened.return_value = False

            handle = _VideoHandle()
            result, count = handle.get(Path("/videos/bad.mp4"))

            assert result is None
            assert count == 0
            handle.close()


class TestExtractFrames:
    def test_extracts_frames_in_order(self):
        plans = [
            SamplePlan(Path("/v/a.mp4"), 0.5, datetime(2023, 1, 1)),
            SamplePlan(Path("/v/b.mp4"), 0.5, datetime(2023, 1, 2)),
        ]

        mock_frame = np.zeros((240, 320, 3), dtype=np.uint8)

        with patch("timelapse.extraction.cv2") as mock_cv2:
            cap = MagicMock()
            mock_cv2.VideoCapture.return_value = cap
            cap.isOpened.return_value = True
            cap.get.return_value = 100.0
            cap.read.return_value = (True, mock_frame)
            mock_cv2.resize.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
            mock_cv2.INTER_AREA = 3

            results = list(extract_frames(plans, 1280, 720))

        assert len(results) == 2
        assert results[0].timestamp == datetime(2023, 1, 1)
        assert results[1].timestamp == datetime(2023, 1, 2)

    def test_skips_failed_reads(self):
        plans = [
            SamplePlan(Path("/v/bad.mp4"), 0.5, datetime(2023, 1, 1)),
        ]

        with patch("timelapse.extraction.cv2") as mock_cv2:
            cap = MagicMock()
            mock_cv2.VideoCapture.return_value = cap
            cap.isOpened.return_value = True
            cap.get.return_value = 100.0
            cap.read.return_value = (False, None)

            results = list(extract_frames(plans, 1280, 720))

        assert len(results) == 0
