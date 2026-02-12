from unittest.mock import MagicMock, patch

import numpy as np


class TestHasPerson:
    def test_person_detected(self):
        frame = np.zeros((640, 640, 3), dtype=np.uint8)

        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.boxes = [MagicMock()]  # one detection
        mock_model.predict.return_value = [mock_result]

        with patch("timelapse.detection._model", mock_model):
            from timelapse.detection import has_person
            assert has_person(frame, confidence=0.3) is True

        mock_model.predict.assert_called_once_with(
            frame, conf=0.3, classes=[0], verbose=False, imgsz=640,
        )

    def test_no_person_detected(self):
        frame = np.zeros((640, 640, 3), dtype=np.uint8)

        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.boxes = []  # no detections
        mock_model.predict.return_value = [mock_result]

        with patch("timelapse.detection._model", mock_model):
            from timelapse.detection import has_person
            assert has_person(frame, confidence=0.3) is False
