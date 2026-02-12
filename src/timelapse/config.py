from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    input_dir: Path
    output: Path = Path("timelapse.mp4")
    target_frames: int = 3600
    fps: int = 30
    recursive: bool = True
    confidence: float = 0.3
    width: int = 1280
    height: int = 720
    timestamp_overlay: bool = False
    oversample: float = 3.0
    skip_detection: bool = False
    intro_seconds: int = 0
    outro_seconds: int = 0
    dry_run: bool = False
    workers: int = 8
    verbose: bool = False

    VIDEO_EXTENSIONS: tuple = (
        ".mp4", ".avi", ".mov", ".mkv", ".webm", ".ts", ".m4v",
    )
