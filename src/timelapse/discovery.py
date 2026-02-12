import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from tqdm import tqdm

from timelapse.config import Config
from timelapse.utils import get_timestamp

log = logging.getLogger("timelapse")


class VideoFile(NamedTuple):
    path: Path
    timestamp: datetime


def find_video_files(config: Config) -> list[Path]:
    """Walk the input directory and return video file paths."""
    input_dir = config.input_dir
    if not input_dir.is_dir():
        raise SystemExit(f"Error: '{input_dir}' is not a directory")

    files: list[Path] = []
    pattern = "**/*" if config.recursive else "*"
    for p in input_dir.glob(pattern):
        if p.is_file() and p.suffix.lower() in config.VIDEO_EXTENSIONS:
            files.append(p)

    if not files:
        raise SystemExit(
            f"Error: No video files found in '{input_dir}'"
            + (" (searched recursively)" if config.recursive else "")
        )

    return files


def _resolve_timestamp(path: Path) -> VideoFile:
    """Resolve timestamp for a single video file."""
    return VideoFile(path=path, timestamp=get_timestamp(path))


def discover_videos(config: Config) -> list[VideoFile]:
    """Find all video files and resolve their timestamps, sorted chronologically."""
    paths = find_video_files(config)
    log.info("Found %d video files, resolving timestamps...", len(paths))

    videos: list[VideoFile] = []
    workers = min(config.workers, len(paths))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_resolve_timestamp, p): p for p in paths}
        with tqdm(total=len(paths), desc="Scanning videos", unit="file") as pbar:
            for future in as_completed(futures):
                try:
                    videos.append(future.result())
                except Exception as e:
                    path = futures[future]
                    log.warning("Skipping %s: %s", path.name, e)
                pbar.update(1)

    videos.sort(key=lambda v: v.timestamp)

    t_start = videos[0].timestamp
    t_end = videos[-1].timestamp
    span = t_end - t_start
    log.info(
        "Discovered %d videos spanning %s to %s (%.1f days)",
        len(videos),
        t_start.strftime("%Y-%m-%d"),
        t_end.strftime("%Y-%m-%d"),
        span.total_seconds() / 86400,
    )

    return videos
