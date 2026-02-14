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


def compose_video(
    frames_iter: Iterator[ExtractedFrame],
    config: Config,
) -> Path:
    """Assemble frames into an MP4 video via ffmpeg subprocess.

    Streams frames directly to ffmpeg — only one frame in memory at a time.
    """
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

    log.info("Encoding to %s (streaming)...", output)

    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    frame_count = 0
    try:
        for ef in frames_iter:
            frame = ef.image
            if config.timestamp_overlay:
                frame = _burn_timestamp(frame.copy(), ef.timestamp)
            proc.stdin.write(frame.tobytes())
            frame_count += 1

        proc.stdin.close()
        _, stderr = proc.communicate(timeout=300)

        if proc.returncode != 0:
            log.error("ffmpeg error:\n%s", stderr.decode(errors="replace"))
            raise SystemExit("Error: ffmpeg encoding failed")

    except BrokenPipeError:
        _, stderr = proc.communicate()
        log.error("ffmpeg pipe broken:\n%s", stderr.decode(errors="replace"))
        raise SystemExit("Error: ffmpeg encoding failed (broken pipe)")

    if frame_count == 0:
        output.unlink(missing_ok=True)
        raise SystemExit("Error: No frames passed detection. Try lowering --confidence or using --skip-detection.")

    file_size = output.stat().st_size
    duration = frame_count / config.fps
    log.info(
        "Output: %s (%.1f MB, %.1fs, %d frames)",
        output, file_size / (1024 * 1024), duration, frame_count,
    )

    return output
