import logging

import numpy as np

log = logging.getLogger("timelapse")

_model = None


def _get_model():
    """Lazy-load YOLOv8-nano model on first use."""
    global _model
    if _model is None:
        from ultralytics import YOLO
        log.info("Loading YOLOv8-nano model...")
        _model = YOLO("yolov8n.pt")
    return _model


def has_person(frame: np.ndarray, confidence: float = 0.3) -> bool:
    """Detect if a person is present in the frame using YOLOv8.

    Uses COCO class 0 (person) with configurable confidence threshold.
    Returns True if at least one person is detected.
    """
    model = _get_model()
    results = model.predict(
        frame,
        conf=confidence,
        classes=[0],  # class 0 = person in COCO
        verbose=False,
        imgsz=640,
    )
    return len(results[0].boxes) > 0


def has_persons_batch(frames: list[np.ndarray], confidence: float = 0.3) -> list[bool]:
    """Batch detect persons in multiple frames at once.

    Significantly faster than calling has_person() per frame because
    YOLO processes the entire batch in a single forward pass.
    """
    if not frames:
        return []
    model = _get_model()
    results = model.predict(
        frames,
        conf=confidence,
        classes=[0],
        verbose=False,
        imgsz=640,
        batch=len(frames),
    )
    return [len(r.boxes) > 0 for r in results]
