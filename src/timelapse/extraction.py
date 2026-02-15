import logging
from datetime import datetime
from pathlib import Path
from typing import Generator, NamedTuple

import cv2
import numpy as np

from timelapse.sampling import SamplePlan

log = logging.getLogger("timelapse")


class ExtractedFrame(NamedTuple):
    image: np.ndarray
    timestamp: datetime
    source: Path


class _VideoHandle:
    """Caches an open VideoCapture to avoid reopening the same file."""

    def __init__(self):
        self._path: Path | None = None
        self._cap: cv2.VideoCapture | None = None
        self._frame_count: int = 0

    def get(self, path: Path) -> tuple[cv2.VideoCapture | None, int]:
        """Get a VideoCapture for the given path, reusing if same as last call."""
        if self._path == path and self._cap is not None:
            return self._cap, self._frame_count

        self.close()
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            log.warning("Cannot open %s", path.name)
            cap.release()
            return None, 0

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count <= 0:
            log.warning("No frames in %s", path.name)
            cap.release()
            return None, 0

        self._path = path
        self._cap = cap
        self._frame_count = frame_count
        return cap, frame_count

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._path = None
            self._frame_count = 0


def extract_frames(
    plans: list[SamplePlan],
    target_width: int,
    target_height: int,
) -> Generator[ExtractedFrame, None, None]:
    """Extract frames from videos. Caches the video handle so consecutive
    plans using the same video don't reopen the file.
    """
    handle = _VideoHandle()

    try:
        for plan in plans:
            cap, frame_count = handle.get(plan.video_path)
            if cap is None:
                continue

            target_frame = int(frame_count * plan.frame_fraction)
            target_frame = max(0, min(target_frame, frame_count - 1))

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()

            if not ret or frame is None:
                log.warning("Failed to read frame %d from %s", target_frame, plan.video_path.name)
                continue

            if frame.shape[1] != target_width or frame.shape[0] != target_height:
                frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)

            yield ExtractedFrame(
                image=frame,
                timestamp=plan.expected_timestamp,
                source=plan.video_path,
            )
    finally:
        handle.close()
