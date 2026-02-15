import bisect
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from timelapse.config import Config
from timelapse.discovery import VideoFile

log = logging.getLogger("timelapse")

# Intro/outro sections show 3x more frames per unit of source time than the middle.
# This makes early/late footage feel like time is passing more slowly.
LINGER_FACTOR = 3.0

# Gap compression: gaps > median * multiplier are capped to reduce repetitive frames
# from inactive periods (overnight, empty room, etc.)
GAP_CAP_MULTIPLIER = 4.0
MIN_GAP_CAP_SECONDS = 600.0  # 10 minutes — never compress gaps shorter than this
MAX_PICKS_PER_VIDEO = 8      # safety cap on repeated picks of a single video


class SamplePlan(NamedTuple):
    video_path: Path
    frame_fraction: float  # 0.0-1.0, where in the video to extract
    expected_timestamp: datetime


def _build_compressed_timeline(
    seg_videos: list[VideoFile],
    t_start: datetime,
    t_end: datetime,
) -> tuple[list[float], float]:
    """Build a compressed timeline where large inter-video gaps are capped.

    Active periods (with many closely spaced clips) retain their full
    duration, while inactive gaps (hours with no recordings) are compressed.

    Returns:
        compressed_positions: compressed-time position for each video
        total_compressed: total duration in compressed time
    """
    if len(seg_videos) < 3:
        # Too few videos to compute meaningful gap statistics; use real time.
        positions = [
            (v.timestamp - t_start).total_seconds() for v in seg_videos
        ]
        total = (t_end - t_start).total_seconds()
        return positions, total

    # Compute inter-video gaps
    gaps = []
    for i in range(len(seg_videos) - 1):
        gap_secs = (seg_videos[i + 1].timestamp - seg_videos[i].timestamp).total_seconds()
        gaps.append(gap_secs)

    # Cap = max(median * multiplier, floor) — adaptive to recording cadence
    sorted_gaps = sorted(gaps)
    median_gap = sorted_gaps[len(sorted_gaps) // 2]
    gap_cap = max(median_gap * GAP_CAP_MULTIPLIER, MIN_GAP_CAP_SECONDS)

    log.debug(
        "Gap compression: median=%.0fs, cap=%.0fs (%.1f min)",
        median_gap, gap_cap, gap_cap / 60,
    )

    # Build compressed position for each video
    leading_gap = max((seg_videos[0].timestamp - t_start).total_seconds(), 0)
    compressed_positions = [min(leading_gap, gap_cap)]

    for i in range(1, len(seg_videos)):
        real_gap = max(
            (seg_videos[i].timestamp - seg_videos[i - 1].timestamp).total_seconds(), 0,
        )
        compressed_positions.append(compressed_positions[-1] + min(real_gap, gap_cap))

    trailing_gap = max((t_end - seg_videos[-1].timestamp).total_seconds(), 0)
    total_compressed = compressed_positions[-1] + min(trailing_gap, gap_cap)

    return compressed_positions, total_compressed


def _sample_segment(
    videos: list[VideoFile],
    timestamps: list[datetime],
    t_start: datetime,
    t_end: datetime,
    n_candidates: int,
) -> list[SamplePlan]:
    """Sample n_candidates frames from a time segment using gap-compressed timeline.

    Large gaps between videos are compressed so that active periods (with many
    clips) receive proportionally more frames than inactive gaps.
    When multiple slots map to the same video, extracts different frames
    from it (spread across the full clip).
    """
    seg_seconds = (t_end - t_start).total_seconds()
    if seg_seconds <= 0 or n_candidates <= 0:
        return []

    # Find videos relevant to this segment.
    # Use bisect_left for start (include videos at t_start) and
    # bisect_right for end (include videos at t_end).
    # Don't expand beyond boundaries — with multi-segment sampling
    # (intro/mid/outro), boundary overlap causes ordering violations.
    seg_start_idx = bisect.bisect_left(timestamps, t_start)
    seg_end_idx = bisect.bisect_right(timestamps, t_end)

    # If no videos fall within [t_start, t_end], include the nearest one
    if seg_start_idx >= seg_end_idx:
        nearest_idx = min(seg_start_idx, len(videos) - 1)
        seg_start_idx = nearest_idx
        seg_end_idx = nearest_idx + 1

    seg_videos = videos[seg_start_idx:seg_end_idx]

    if not seg_videos:
        return []

    # Build compressed timeline for gap-aware sampling
    compressed_positions, total_compressed = _build_compressed_timeline(
        seg_videos, t_start, t_end,
    )

    if total_compressed <= 0:
        return []

    slot_duration = total_compressed / n_candidates

    plan: list[SamplePlan] = []

    # Track how many times each video has been picked to vary frame position
    video_hit_count: dict[Path, int] = {}

    for i in range(n_candidates):
        slot_center = slot_duration * (i + 0.5)

        # Find nearest video in compressed space
        idx = bisect.bisect_left(compressed_positions, slot_center)

        best_video: VideoFile | None = None
        best_delta = float("inf")

        for candidate_idx in (idx - 1, idx):
            if 0 <= candidate_idx < len(seg_videos):
                delta = abs(compressed_positions[candidate_idx] - slot_center)
                if delta < best_delta:
                    best_delta = delta
                    best_video = seg_videos[candidate_idx]

        if best_video is None:
            continue

        # Per-video safety cap
        hits = video_hit_count.get(best_video.path, 0)
        if hits >= MAX_PICKS_PER_VIDEO:
            continue

        video_hit_count[best_video.path] = hits + 1

        # Vary frame position across the video (0.1-0.9)
        # so repeated picks of the same video yield different frames
        if hits == 0:
            frame_fraction = 0.5
        else:
            total_hits = hits + 1
            frame_fraction = 0.1 + (0.8 * (hits / total_hits))

        plan.append(SamplePlan(
            video_path=best_video.path,
            frame_fraction=frame_fraction,
            expected_timestamp=best_video.timestamp,
        ))

    return plan


def create_sample_plan(
    videos: list[VideoFile],
    config: Config,
) -> list[SamplePlan]:
    """Create a temporally stratified sampling plan.

    When intro/outro are set, the source timeline is split into 3 segments.
    Intro and outro segments get more frames per unit of source time (the
    "linger" effect), making early and late footage feel slower.
    """
    oversample = config.oversample if not config.skip_detection else 1.0

    t_start = videos[0].timestamp
    t_end = videos[-1].timestamp
    total_seconds = (t_end - t_start).total_seconds()

    if total_seconds <= 0:
        log.warning("All videos have the same timestamp")
        n_candidates = int(config.target_frames * oversample)
        step = max(1, len(videos) // n_candidates)
        return [
            SamplePlan(v.path, 0.5, v.timestamp)
            for v in videos[::step]
        ][:n_candidates]

    timestamps = [v.timestamp for v in videos]

    intro_secs = config.intro_seconds
    outro_secs = config.outro_seconds
    total_video_secs = config.target_frames / config.fps

    if intro_secs or outro_secs:
        # Allocate video time to each segment
        mid_video_secs = total_video_secs - intro_secs - outro_secs

        # Calculate source time each segment covers.
        # Linger sections cover less source time (they're slower).
        # We solve: intro_src/LINGER + mid_src/1 + outro_src/LINGER = total_src (weighted)
        # Such that the frame density ratio is LINGER_FACTOR:1.
        #
        # Frame density = video_seconds / source_seconds
        # intro_density = intro_video_secs / intro_source_secs
        # mid_density   = mid_video_secs / mid_source_secs
        # We want: intro_density = LINGER_FACTOR * mid_density
        #
        # With total_source = total_seconds, allocate source time proportionally:
        # intro_src + mid_src + outro_src = total_seconds
        # intro_src / intro_video_secs = mid_src / (mid_video_secs * LINGER_FACTOR)
        # outro_src / outro_video_secs = mid_src / (mid_video_secs * LINGER_FACTOR)
        #
        # Simplify: each second of intro/outro video covers 1/LINGER_FACTOR as much
        # source time as each second of middle video.

        # Weighted video seconds (normalizing linger sections)
        weighted_total = intro_secs / LINGER_FACTOR + mid_video_secs + outro_secs / LINGER_FACTOR
        source_per_weighted_sec = total_seconds / weighted_total

        intro_source_secs = (intro_secs / LINGER_FACTOR) * source_per_weighted_sec
        outro_source_secs = (outro_secs / LINGER_FACTOR) * source_per_weighted_sec

        t_intro_end = t_start + timedelta(seconds=intro_source_secs)
        t_outro_start = t_end - timedelta(seconds=outro_source_secs)

        # Ensure segments don't overlap
        if t_intro_end >= t_outro_start:
            log.warning("Intro/outro source spans overlap; falling back to uniform sampling")
            intro_secs = 0
            outro_secs = 0

    if not intro_secs and not outro_secs:
        # Simple uniform sampling (no intro/outro)
        n_candidates = int(config.target_frames * oversample)
        plan = _sample_segment(videos, timestamps, t_start, t_end, n_candidates)
    else:
        # Three-segment sampling
        intro_frames = int(intro_secs * config.fps * oversample)
        outro_frames = int(outro_secs * config.fps * oversample)
        mid_frames = int(mid_video_secs * config.fps * oversample)

        log.info(
            "Linger sampling: intro %.0fs source → %ds video | "
            "middle → %.0fs video | outro %.0fs source → %ds video",
            intro_source_secs, intro_secs,
            mid_video_secs,
            outro_source_secs, outro_secs,
        )

        plan_intro = _sample_segment(videos, timestamps, t_start, t_intro_end, intro_frames)
        plan_mid = _sample_segment(videos, timestamps, t_intro_end, t_outro_start, mid_frames)
        plan_outro = _sample_segment(videos, timestamps, t_outro_start, t_end, outro_frames)
        plan = plan_intro + plan_mid + plan_outro

    log.info(
        "Sampling plan: %d candidate frames from %d videos "
        "(%.1f slots/day, target=%d final frames)",
        len(plan),
        len(set(s.video_path for s in plan)),
        len(plan) / max(1, total_seconds / 86400),
        config.target_frames,
    )

    return plan
