import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

from timelapse.config import Config
from timelapse.extraction import ExtractedFrame

log = logging.getLogger("timelapse")


def _burn_timestamp(frame: np.ndarray, timestamp: datetime) -> np.ndarray:
    """Overlay a timestamp on the bottom-left of the frame."""
    text = timestamp.strftime("%Y-%m-%d %H:%M")
    h, w = frame.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = w / 1280  # scale relative to 1280px width
    thickness = max(1, int(2 * font_scale))
    position = (int(10 * font_scale), h - int(15 * font_scale))

    # Draw shadow for readability
    cv2.putText(frame, text, position, font, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(frame, text, position, font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
    return frame


def _downsample(frames: list[ExtractedFrame], target: int) -> list[ExtractedFrame]:
    """Uniformly downsample to target count, preserving temporal order."""
    if len(frames) <= target:
        return frames
    step = len(frames) / target
    return [frames[int(i * step)] for i in range(target)]


def compose_video(
    frames_iter: Iterator[ExtractedFrame],
    config: Config,
) -> Path:
    """Assemble frames into an MP4 video via ffmpeg subprocess."""
    # Collect frames (needed for potential downsampling)
    log.info("Collecting accepted frames...")
    frames = list(frames_iter)

    if not frames:
        raise SystemExit("Error: No frames passed detection. Try lowering --confidence or using --skip-detection.")

    log.info("Accepted %d frames", len(frames))

    # Downsample if we have more than target
    if len(frames) > config.target_frames:
        frames = _downsample(frames, config.target_frames)
        log.info("Downsampled to %d frames", len(frames))

    output = config.output
    output.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{config.width}x{config.height}",
        "-pix_fmt", "bgr24",
        "-r", str(config.fps),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output),
    ]

    log.info("Encoding %d frames at %dfps to %s...", len(frames), config.fps, output)

    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        for ef in frames:
            frame = ef.image
            if config.timestamp_overlay:
                frame = _burn_timestamp(frame.copy(), ef.timestamp)
            proc.stdin.write(frame.tobytes())

        proc.stdin.close()
        _, stderr = proc.communicate(timeout=120)

        if proc.returncode != 0:
            log.error("ffmpeg error:\n%s", stderr.decode(errors="replace"))
            raise SystemExit("Error: ffmpeg encoding failed")

    except BrokenPipeError:
        _, stderr = proc.communicate()
        log.error("ffmpeg pipe broken:\n%s", stderr.decode(errors="replace"))
        raise SystemExit("Error: ffmpeg encoding failed (broken pipe)")

    file_size = output.stat().st_size
    duration = len(frames) / config.fps
    log.info(
        "Output: %s (%.1f MB, %.1fs, %d frames)",
        output, file_size / (1024 * 1024), duration, len(frames),
    )

    return output
