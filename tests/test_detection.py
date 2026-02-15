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


class TestHasPersonsBatch:
    def test_batch_detection(self):
        frames = [np.zeros((640, 640, 3), dtype=np.uint8) for _ in range(3)]

        mock_model = MagicMock()
        r1 = MagicMock()
        r1.boxes = [MagicMock()]  # person
        r2 = MagicMock()
        r2.boxes = []  # no person
        r3 = MagicMock()
        r3.boxes = [MagicMock()]  # person
        mock_model.predict.return_value = [r1, r2, r3]

        with patch("timelapse.detection._model", mock_model):
            from timelapse.detection import has_persons_batch
            results = has_persons_batch(frames, confidence=0.3)

        assert results == [True, False, True]
        mock_model.predict.assert_called_once()

    def test_empty_batch(self):
        with patch("timelapse.detection._model", MagicMock()):
            from timelapse.detection import has_persons_batch
            assert has_persons_batch([], confidence=0.3) == []
