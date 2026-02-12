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


def extract_frame(
    plan: SamplePlan,
    target_width: int,
    target_height: int,
) -> ExtractedFrame | None:
    """Extract a single frame from a video at the planned position."""
    cap = cv2.VideoCapture(str(plan.video_path))
    try:
        if not cap.isOpened():
            log.warning("Cannot open %s", plan.video_path.name)
            return None

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count <= 0:
            log.warning("No frames in %s", plan.video_path.name)
            return None

        # Pick frame from middle third
        mid_start = frame_count // 3
        mid_end = (frame_count * 2) // 3
        target_frame = max(0, (mid_start + mid_end) // 2)
        target_frame = int(frame_count * plan.frame_fraction)
        target_frame = max(0, min(target_frame, frame_count - 1))

        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()

        if not ret or frame is None:
            log.warning("Failed to read frame %d from %s", target_frame, plan.video_path.name)
            return None

        # Resize to target output resolution
        if frame.shape[1] != target_width or frame.shape[0] != target_height:
            frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)

        return ExtractedFrame(
            image=frame,
            timestamp=plan.expected_timestamp,
            source=plan.video_path,
        )

    except Exception as e:
        log.warning("Error extracting from %s: %s", plan.video_path.name, e)
        return None
    finally:
        cap.release()


def extract_frames(
    plans: list[SamplePlan],
    target_width: int,
    target_height: int,
) -> Generator[ExtractedFrame, None, None]:
    """Extract frames from videos according to the sample plan. Yields one at a time."""
    for plan in plans:
        frame = extract_frame(plan, target_width, target_height)
        if frame is not None:
            yield frame
