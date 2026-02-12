from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from timelapse.extraction import extract_frame
from timelapse.sampling import SamplePlan


class TestExtractFrame:
    def test_extract_frame_success(self):
        plan = SamplePlan(
            video_path=Path("/videos/test.mp4"),
            frame_fraction=0.5,
            expected_timestamp=datetime(2023, 6, 15),
        )

        mock_frame = np.zeros((240, 320, 3), dtype=np.uint8)

        with patch("timelapse.extraction.cv2") as mock_cv2:
            cap = MagicMock()
            mock_cv2.VideoCapture.return_value = cap
            cap.isOpened.return_value = True
            cap.get.return_value = 100.0  # 100 frames
            cap.read.return_value = (True, mock_frame)
            mock_cv2.resize.return_value = np.zeros((720, 1280, 3), dtype=np.uint8)
            mock_cv2.INTER_AREA = 3

            result = extract_frame(plan, 1280, 720)

        assert result is not None
        assert result.timestamp == datetime(2023, 6, 15)
        assert result.source == Path("/videos/test.mp4")
        cap.release.assert_called_once()

    def test_extract_frame_cannot_open(self):
        plan = SamplePlan(
            video_path=Path("/videos/bad.mp4"),
            frame_fraction=0.5,
            expected_timestamp=datetime(2023, 6, 15),
        )

        with patch("timelapse.extraction.cv2") as mock_cv2:
            cap = MagicMock()
            mock_cv2.VideoCapture.return_value = cap
            cap.isOpened.return_value = False

            result = extract_frame(plan, 1280, 720)

        assert result is None
        cap.release.assert_called_once()

    def test_extract_frame_read_failure(self):
        plan = SamplePlan(
            video_path=Path("/videos/corrupt.mp4"),
            frame_fraction=0.5,
            expected_timestamp=datetime(2023, 6, 15),
        )

        with patch("timelapse.extraction.cv2") as mock_cv2:
            cap = MagicMock()
            mock_cv2.VideoCapture.return_value = cap
            cap.isOpened.return_value = True
            cap.get.return_value = 100.0
            cap.read.return_value = (False, None)

            result = extract_frame(plan, 1280, 720)

        assert result is None
