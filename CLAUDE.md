# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run

```bash
# Setup (requires Python 3.10+, ffmpeg, ffprobe)
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run
timelapse /path/to/video/clips -o output.mp4
timelapse -d 5m /path/to/clips                      # set output duration
timelapse -d 10m --intro 30s --outro 30s /path/to/clips  # linger effect
timelapse /path/to/clips --dry-run                   # stats only, no processing
timelapse /path/to/clips --skip-detection            # skip YOLO, include all frames

# Tests
python -m pytest tests/ -v
python -m pytest tests/test_sampling.py -v              # single module
python -m pytest tests/test_discovery.py::TestParseFilenameTimestamp  # single class
```

## Architecture

Python CLI tool that creates time-lapse videos from a collection of video clips with YOLO-based person detection to filter out frames with no people.

**4-stage pipeline** orchestrated in `cli.py`:

1. **Discovery** (`discovery.py`) — Recursive file walk, timestamp extraction via priority chain (Wyze path → filename regex → ffprobe metadata → mtime fallback), returns sorted `VideoFile` list
2. **Sampling** (`sampling.py`) — Temporal stratified sampling: divides time range into equal slots, picks nearest video per slot via `bisect`. When multiple slots map to the same video, extracts different frames at varying positions. Supports `--intro`/`--outro` linger effect (3x slower at start/end) via three-segment sampling
3. **Extraction + Detection** (`extraction.py`, `detection.py`) — Opens videos with `cv2.VideoCapture`, seeks to target frame, resizes. Lazy-loaded YOLOv8-nano singleton checks COCO class 0 ("person") at configurable confidence. Generator pattern keeps one frame in memory at a time
4. **Composition** (`composer.py`) — Streams frames directly to `ffmpeg` subprocess stdin for H.264 encoding (constant memory, no frame buffering). Optional timestamp overlay via `cv2.putText`

**Key files:**
- `config.py` — Frozen `Config` dataclass, single source of truth for all settings
- `utils.py` — Timestamp parsing regexes, ffprobe wrapper, ffmpeg availability check

**Performance design:** Timestamps are extracted from filenames/paths without subprocess calls. Only videos selected by the sampling plan get opened. ffprobe is a last-resort fallback, not called for every file. Frames stream directly to ffmpeg — memory usage is constant regardless of output length.
