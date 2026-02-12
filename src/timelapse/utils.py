import json
import logging
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

log = logging.getLogger("timelapse")

# Regex patterns for common camera filename conventions
_TIMESTAMP_PATTERNS: list[tuple[re.Pattern, str]] = [
    # YYYYMMDD_HHMMSS or YYYYMMDD-HHMMSS
    (re.compile(r"(\d{4})([\-_]?)(\d{2})\2(\d{2})[\-_](\d{2})([\-_]?)(\d{2})\6(\d{2})"), None),
    # YYYY-MM-DDTHH:MM:SS (ISO 8601)
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})"), "iso"),
    # YYYY-MM-DD_HH-MM-SS
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})"), "iso"),
]

# Wyze SD card path pattern: /record/YYYYMMDD/HH/MM.mp4
_WYZE_PATH_RE = re.compile(r"record[/\\](\d{4})(\d{2})(\d{2})[/\\](\d{2})[/\\](\d{2})")

# 10-digit Unix timestamp in filename
_UNIX_TS_RE = re.compile(r"(?<!\d)(\d{10})(?!\d)")

# 13-digit Unix millisecond timestamp
_UNIX_MS_RE = re.compile(r"(?<!\d)(\d{13})(?!\d)")


def check_ffmpeg() -> None:
    """Verify ffmpeg and ffprobe are available. Raises SystemExit if not."""
    for cmd in ("ffmpeg", "ffprobe"):
        if shutil.which(cmd) is None:
            raise SystemExit(
                f"Error: '{cmd}' not found. Install ffmpeg: https://ffmpeg.org/download.html"
            )


def probe_creation_time(path: Path) -> datetime | None:
    """Extract creation_time from video container metadata via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        ts_str = data.get("format", {}).get("tags", {}).get("creation_time")
        if ts_str:
            # Handle common formats: 2023-04-15T14:35:22.000000Z
            ts_str = ts_str.replace("Z", "+00:00")
            return datetime.fromisoformat(ts_str).replace(tzinfo=None)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, OSError) as e:
        log.debug("ffprobe failed for %s: %s", path, e)
    return None


def parse_wyze_path(path: Path) -> datetime | None:
    """Parse Wyze-style directory structure for timestamp."""
    m = _WYZE_PATH_RE.search(str(path))
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)),
            )
        except ValueError:
            pass
    return None


def parse_filename_timestamp(name: str) -> datetime | None:
    """Try to extract a timestamp from a filename using common patterns."""
    # Try structured patterns first
    for pattern, fmt in _TIMESTAMP_PATTERNS:
        m = pattern.search(name)
        if not m:
            continue
        groups = m.groups()
        try:
            if fmt == "iso":
                return datetime(
                    int(groups[0]), int(groups[1]), int(groups[2]),
                    int(groups[3]), int(groups[4]), int(groups[5]),
                )
            else:
                # YYYYMMDD_HHMMSS with optional separators
                return datetime(
                    int(groups[0]), int(groups[2]), int(groups[3]),
                    int(groups[4]), int(groups[6]), int(groups[7]),
                )
        except ValueError:
            continue

    # Try Unix epoch (13-digit first, then 10-digit)
    m = _UNIX_MS_RE.search(name)
    if m:
        try:
            ts = int(m.group(1)) / 1000
            dt = datetime.fromtimestamp(ts)
            if 2015 <= dt.year <= 2030:
                return dt
        except (ValueError, OSError):
            pass

    m = _UNIX_TS_RE.search(name)
    if m:
        try:
            dt = datetime.fromtimestamp(int(m.group(1)))
            if 2015 <= dt.year <= 2030:
                return dt
        except (ValueError, OSError):
            pass

    return None


def get_timestamp(path: Path) -> datetime:
    """Determine when a video was recorded using a priority chain of strategies."""
    # Strategy 1: Wyze-style path (fast, no subprocess)
    ts = parse_wyze_path(path)
    if ts:
        return ts

    # Strategy 2: Filename patterns (fast, no subprocess)
    ts = parse_filename_timestamp(path.name)
    if ts:
        return ts

    # Strategy 3: Full path string (catches timestamps in parent dirs)
    ts = parse_filename_timestamp(str(path))
    if ts:
        return ts

    # Strategy 4: ffprobe metadata (slow, requires subprocess)
    ts = probe_creation_time(path)
    if ts:
        return ts

    # Strategy 5: Filesystem mtime (last resort)
    log.debug("Using mtime fallback for %s", path.name)
    return datetime.fromtimestamp(path.stat().st_mtime)


def setup_logging(verbose: bool) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )
