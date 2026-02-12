import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_frame():
    """A 1280x720 BGR numpy array simulating a video frame."""
    return np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)


@pytest.fixture
def create_test_video(tmp_dir):
    """Factory fixture that creates a short test video file."""
    def _create(name: str = "test.mp4", frames: int = 30, fps: int = 30) -> Path:
        path = tmp_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Create a minimal video with ffmpeg using lavfi test source
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"testsrc=duration={frames / fps}:size=320x240:rate={fps}",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(path),
            ],
            capture_output=True,
            timeout=30,
        )
        return path
    return _create
