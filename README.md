# timelapse

Create time-lapse videos from a collection of video clips.

Takes a folder of video clips, evenly samples across the full time range, and outputs an MP4 time-lapse. The Python version also detects which frames have a person present using YOLOv8. Works well with security cameras, trail cams, dashcams, or any source that produces many short clips over time.

Two implementations are available:

| | Python | Go |
|---|---|---|
| Person detection | YOLOv8-nano (built-in) | Optional via `--detector` hook |
| External deps | click, opencv, ultralytics, tqdm | None (stdlib only) |
| Requires | Python 3.10+, ffmpeg | ffmpeg |
| Binary | `timelapse` (via venv) | Single static binary |

## Requirements

- [ffmpeg](https://ffmpeg.org/download.html) (`brew install ffmpeg` on macOS, `winget install ffmpeg` on Windows)

## Installation

### Python

```bash
git clone <repo-url> && cd timeLapse
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

To make the command available globally:

```bash
ln -s "$(pwd)/.venv/bin/timelapse" /usr/local/bin/timelapse
```

### Go

```bash
cd timelapse-go
make build          # produces ./timelapse
```

Or without make:

```bash
cd timelapse-go
go build -ldflags "-X main.version=$(git describe --tags --always --dirty)" -o timelapse .
```

Copy the binary anywhere on your PATH. No other files needed.

## Usage

Both versions share the same interface (Python uses `--flag`, Go accepts both `-flag` and `--flag`):

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

# Higher resolution, more frames
timelapse -d 10m --resolution 1920x1080 /path/to/clips

# Only top-level folder (no subfolders)
timelapse --no-recursive /path/to/clips
```

### Person detection (Python only, built-in)

```bash
# Lower detection confidence for dark/IR footage
timelapse --confidence 0.2 /path/to/clips
```

### Person detection (Go, external hook)

The Go version accepts any external command as a detector. The command receives a raw BGR24 frame on stdin and the frame dimensions as arguments; exit 0 means a person was detected.

```bash
# Use the bundled Python+YOLO detector script
timelapse --detector "python3 detect.py" /path/to/clips
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
| `--resolution` | `1280x720` | Output resolution (`WxH`) |
| `--timestamp` | off | Burn date overlay on frames |
| `--skip-detection` | off | Include all frames without person detection |
| `--no-recursive` | off | Don't search subfolders |
| `--oversample` | `3.0` | Oversample factor for detection filtering |
| `--workers` | `8` | Parallel workers for video probing |
| `--dry-run` | off | Show stats without processing |
| `-v, --verbose` | off | Debug logging |
| `--confidence` | `0.3` | *(Python only)* YOLO detection threshold (0.0–1.0) |
| `--detector` | off | *(Go only)* External detector command |

## How it works

1. **Discovery** — Recursively finds video files and extracts timestamps from filenames, directory structure, video metadata, or file modification time
2. **Sampling** — Divides the full time range into equal slots and picks the nearest video for each slot, with gap compression to prevent long idle periods from dominating. Extracts multiple frames from the same clip at different positions when needed
3. **Detection** — Filters frames to those containing a person (Python: YOLOv8-nano built-in; Go: optional external command)
4. **Composition** — Streams accepted frames directly to ffmpeg for H.264 encoding (constant memory usage)

The `--intro` and `--outro` options create a "linger" effect where the beginning and end of the time-lapse play 3× slower than the middle.

## Benchmarks

Measured on 60 synthetic 1280×720 clips with `--skip-detection` (no person detection), macOS arm64.

| Stage | Python | Go |
|---|---|---|
| Discovery + sampling (`--dry-run`) | 0.24s | 0.52s |
| 60-frame full run | 4.6s | 5.1s |
| 300-frame full run | 9.9s | 20.4s |

**Python is ~2× faster at frame extraction** because OpenCV opens video files in-process and seeks natively. The Go version spawns one `ffmpeg` subprocess per frame (required to avoid external Go dependencies), which adds ~50–60ms overhead per frame.

The Go version's advantage is distribution: a single ~7 MB binary with no Python, NumPy, or OpenCV required.

## About

This project was vibe coded with [Claude Code](https://claude.ai/code) for my personal use. If anyone else finds it useful, I'd be thrilled!

## License

This work is licensed under a [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).
