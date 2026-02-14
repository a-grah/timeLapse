# timelapse

Create time-lapse videos from a collection of video clips.

Takes a folder of video clips, detects which frames have a person present using YOLOv8, evenly samples across the full time range, and outputs an MP4 time-lapse. Works well with security cameras, trail cams, dashcams, or any source that produces many short clips over time.

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/download.html) (`brew install ffmpeg` on macOS)

## Installation

```bash
git clone <repo-url> && cd timeLapse
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

To make the command available globally:

```bash
ln -s "$(pwd)/.venv/bin/timelapse" /usr/local/bin/timelapse
```

## Usage

```bash
# Basic — 2 minute time-lapse from a folder of clips
timelapse /path/to/video/clips

# Set output duration and filename
timelapse -d 5m -o output.mp4 /path/to/clips

# Linger on early and late footage (slows time at start/end)
timelapse -d 5m --intro 20s --outro 20s /path/to/clips

# Burn the date onto each frame
timelapse --timestamp /path/to/clips

# Preview what would be processed without generating video
timelapse --dry-run /path/to/clips

# Skip person detection (include all sampled frames)
timelapse --skip-detection /path/to/clips

# Lower detection confidence for dark/IR footage
timelapse --confidence 0.2 /path/to/clips

# Higher resolution, more frames
timelapse -d 10m --resolution 1920x1080 /path/to/clips

# Only top-level folder (no subfolders)
timelapse --no-recursive /path/to/clips
```

## Options

| Option | Default | Description |
|---|---|---|
| `-o, --output` | `timelapse.mp4` | Output file path |
| `-d, --duration` | `2m` | Output video duration (e.g. `30s`, `5m`, `2m30s`, `1h`) |
| `-n, --frames` | `3600` | Target frame count (alternative to `--duration`) |
| `--fps` | `30` | Output frame rate |
| `--intro` | off | Linger on earliest footage (e.g. `15s`, `1m`) |
| `--outro` | off | Linger on latest footage (e.g. `15s`, `1m`) |
| `--confidence` | `0.3` | YOLO person detection threshold (0.0-1.0) |
| `--resolution` | `1280x720` | Output resolution (`WxH`) |
| `--timestamp` | off | Burn date overlay on frames |
| `--skip-detection` | off | Include all frames without person detection |
| `--no-recursive` | off | Don't search subfolders |
| `--oversample` | `3.0` | Oversample factor for detection filtering |
| `--workers` | `8` | Parallel workers for video probing |
| `--dry-run` | off | Show stats without processing |
| `-v, --verbose` | off | Debug logging |

## How it works

1. **Discovery** — Recursively finds video files and extracts timestamps from filenames, directory structure, video metadata, or file modification time
2. **Sampling** — Divides the full time range into equal slots and picks the nearest video for each slot, extracting multiple frames from the same clip when needed to hit the target duration
3. **Detection** — Runs YOLOv8-nano person detection on each extracted frame, filtering out frames with no people (skip with `--skip-detection`)
4. **Composition** — Streams accepted frames directly to ffmpeg for H.264 encoding (constant memory usage)

The `--intro` and `--outro` options create a "linger" effect where the beginning and end of the time-lapse play 3x slower than the middle, letting you savor the earliest and latest moments.

## About

This project was vibe coded with [Claude Code](https://claude.ai/code) for my personal use. If anyone else finds it useful, I'd be thrilled!

## License

This work is licensed under a [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).
