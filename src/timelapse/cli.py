import logging
from pathlib import Path

import click
from tqdm import tqdm

from timelapse import __version__
from timelapse.config import Config
from timelapse.utils import check_ffmpeg, setup_logging

log = logging.getLogger("timelapse")


def _parse_resolution(value: str) -> tuple[int, int]:
    """Parse 'WxH' string into (width, height)."""
    try:
        w, h = value.lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        raise click.BadParameter(f"Invalid resolution '{value}'. Use format WxH, e.g. 1280x720")


def _parse_duration(value: str) -> int:
    """Parse a duration string like '5m', '120s', '2m30s', '1h' into seconds."""
    import re
    value = value.strip().lower()

    # Try plain integer (seconds)
    if value.isdigit():
        return int(value)

    total = 0
    pattern = re.compile(r"(\d+)\s*(h|m|s)")
    matches = pattern.findall(value)
    if not matches:
        raise click.BadParameter(
            f"Invalid duration '{value}'. Use formats like: 30s, 5m, 2m30s, 1h"
        )
    for amount, unit in matches:
        n = int(amount)
        if unit == "h":
            total += n * 3600
        elif unit == "m":
            total += n * 60
        elif unit == "s":
            total += n
    return total


@click.command()
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default="timelapse.mp4",
              help="Output video file path.")
@click.option("-d", "--duration", type=str, default=None,
              help="Output video duration (e.g. 30s, 5m, 2m30s, 1h). Overrides --frames.")
@click.option("-n", "--frames", type=int, default=None,
              help="Target number of frames in output. Default: 3600 (2m at 30fps).")
@click.option("--fps", type=int, default=30, help="Output video frame rate.")
@click.option("--no-recursive", is_flag=True, help="Do not search subfolders.")
@click.option("--confidence", type=float, default=0.3,
              help="Person detection confidence threshold (0.0-1.0).")
@click.option("--resolution", type=str, default="1280x720", help="Output resolution WxH.")
@click.option("--timestamp/--no-timestamp", default=False,
              help="Burn timestamp overlay on frames.")
@click.option("--intro", type=str, default=None,
              help="Linger on the earliest footage (e.g. 15s, 1m). Slows time at the start.")
@click.option("--outro", type=str, default=None,
              help="Linger on the latest footage (e.g. 15s, 1m). Slows time at the end.")
@click.option("--oversample", type=float, default=3.0,
              help="Oversample factor for detection filtering.")
@click.option("--skip-detection", is_flag=True,
              help="Skip person detection (include all sampled frames).")
@click.option("--dry-run", is_flag=True, help="Show discovery and sampling stats without processing.")
@click.option("--workers", type=int, default=8, help="Parallel workers for video probing.")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.version_option(version=__version__)
def main(
    input_dir: Path,
    output: Path,
    duration: str | None,
    frames: int | None,
    fps: int,
    no_recursive: bool,
    confidence: float,
    resolution: str,
    timestamp: bool,
    intro: str | None,
    outro: str | None,
    oversample: float,
    skip_detection: bool,
    dry_run: bool,
    workers: int,
    verbose: bool,
) -> None:
    """Create a time-lapse video from baby monitor clips showing growth over time."""
    setup_logging(verbose)
    check_ffmpeg()

    width, height = _parse_resolution(resolution)

    # Resolve target frames from --duration, --frames, or default
    if duration is not None:
        seconds = _parse_duration(duration)
        target_frames = seconds * fps
        log.info("Duration %s → %d frames at %dfps", duration, target_frames, fps)
    elif frames is not None:
        target_frames = frames
    else:
        target_frames = 3600  # default: 2 minutes at 30fps

    # Resolve intro/outro durations
    intro_seconds = _parse_duration(intro) if intro else 0
    outro_seconds = _parse_duration(outro) if outro else 0
    linger_video_secs = intro_seconds + outro_seconds
    total_video_secs = target_frames / fps
    if linger_video_secs >= total_video_secs:
        raise click.UsageError(
            f"--intro ({intro_seconds}s) + --outro ({outro_seconds}s) = {linger_video_secs}s "
            f"which exceeds total video duration ({total_video_secs:.0f}s). "
            f"Use a longer --duration or shorter intro/outro."
        )

    config = Config(
        input_dir=input_dir,
        output=output,
        target_frames=target_frames,
        fps=fps,
        recursive=not no_recursive,
        confidence=confidence,
        width=width,
        height=height,
        timestamp_overlay=timestamp,
        intro_seconds=intro_seconds,
        outro_seconds=outro_seconds,
        oversample=oversample,
        skip_detection=skip_detection,
        dry_run=dry_run,
        workers=workers,
        verbose=verbose,
    )

    # Stage 1: Discovery
    from timelapse.discovery import discover_videos
    videos = discover_videos(config)

    # Stage 2: Sampling
    from timelapse.sampling import create_sample_plan
    plan = create_sample_plan(videos, config)

    if config.dry_run:
        secs = config.target_frames / config.fps
        mins, s = divmod(int(secs), 60)
        dur_str = f"{mins}m{s:02d}s" if mins else f"{s}s"
        click.echo(f"\nDry run complete. Would process {len(plan)} candidate frames.")
        click.echo(f"Target output: {config.target_frames} frames at {config.fps}fps = {dur_str}")
        if config.intro_seconds or config.outro_seconds:
            mid_secs = secs - config.intro_seconds - config.outro_seconds
            click.echo(f"  Intro (linger): {config.intro_seconds}s | "
                        f"Middle: {mid_secs:.0f}s | "
                        f"Outro (linger): {config.outro_seconds}s")
        return

    # Stage 3: Extract + Detect
    from timelapse.extraction import extract_frames

    def _process_frames():
        if config.skip_detection:
            log.info("Skipping person detection (--skip-detection)")
            yield from tqdm(
                extract_frames(plan, config.width, config.height),
                total=len(plan), desc="Extracting frames", unit="frame",
            )
        else:
            from timelapse.detection import has_person
            accepted = 0
            rejected = 0
            for ef in tqdm(
                extract_frames(plan, config.width, config.height),
                total=len(plan), desc="Extracting & detecting", unit="frame",
            ):
                if has_person(ef.image, config.confidence):
                    accepted += 1
                    yield ef
                else:
                    rejected += 1
            log.info("Detection: %d accepted, %d rejected (%.0f%% pass rate)",
                     accepted, rejected,
                     100 * accepted / max(1, accepted + rejected))

    # Stage 4: Compose
    from timelapse.composer import compose_video
    output_path = compose_video(_process_frames(), config)

    click.echo(f"\nTime-lapse saved to: {output_path}")
