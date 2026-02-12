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


class SamplePlan(NamedTuple):
    video_path: Path
    frame_fraction: float  # 0.0-1.0, where in the video to extract
    expected_timestamp: datetime


def _sample_segment(
    videos: list[VideoFile],
    timestamps: list[datetime],
    t_start: datetime,
    t_end: datetime,
    n_candidates: int,
) -> list[SamplePlan]:
    """Sample n_candidates frames evenly from a time segment."""
    seg_seconds = (t_end - t_start).total_seconds()
    if seg_seconds <= 0 or n_candidates <= 0:
        return []

    slot_duration = timedelta(seconds=seg_seconds / n_candidates)
    plan: list[SamplePlan] = []
    last_video_path: Path | None = None

    for i in range(n_candidates):
        slot_center = t_start + slot_duration * (i + 0.5)

        idx = bisect.bisect_left(timestamps, slot_center)

        best_video: VideoFile | None = None
        best_delta = timedelta.max

        for candidate_idx in (idx - 1, idx):
            if 0 <= candidate_idx < len(videos):
                delta = abs(videos[candidate_idx].timestamp - slot_center)
                if delta < best_delta:
                    best_delta = delta
                    best_video = videos[candidate_idx]

        if best_video is None:
            continue

        if best_delta > slot_duration * 2:
            continue

        if best_video.path == last_video_path:
            continue

        last_video_path = best_video.path

        plan.append(SamplePlan(
            video_path=best_video.path,
            frame_fraction=0.5,
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
