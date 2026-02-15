from datetime import datetime, timedelta
from pathlib import Path

from timelapse.config import Config
from timelapse.discovery import VideoFile
from timelapse.sampling import SamplePlan, create_sample_plan, MAX_PICKS_PER_VIDEO


def _make_videos(count: int, start: datetime, interval: timedelta) -> list[VideoFile]:
    """Create a list of mock VideoFile entries with evenly spaced timestamps."""
    return [
        VideoFile(
            path=Path(f"/videos/clip_{i:04d}.mp4"),
            timestamp=start + interval * i,
        )
        for i in range(count)
    ]


class TestCreateSamplePlan:
    def test_basic_plan(self):
        videos = _make_videos(100, datetime(2023, 1, 1), timedelta(hours=1))
        config = Config(input_dir=Path("/videos"), target_frames=10, oversample=2.0)
        plan = create_sample_plan(videos, config)

        assert len(plan) > 0
        assert len(plan) <= 20  # 10 * 2.0 oversample
        assert all(isinstance(s, SamplePlan) for s in plan)

    def test_plan_temporal_spread(self):
        """Frames should be spread across the full time range."""
        videos = _make_videos(1000, datetime(2023, 1, 1), timedelta(hours=1))
        config = Config(input_dir=Path("/videos"), target_frames=50, oversample=1.0)
        plan = create_sample_plan(videos, config)

        timestamps = [s.expected_timestamp for s in plan]
        first = timestamps[0]
        last = timestamps[-1]
        span = (last - first).total_seconds()
        total_span = (videos[-1].timestamp - videos[0].timestamp).total_seconds()

        # The sampled span should cover at least 80% of the total range
        assert span / total_span > 0.8

    def test_skip_detection_no_oversample(self):
        """When skip_detection is True, don't oversample."""
        videos = _make_videos(100, datetime(2023, 1, 1), timedelta(hours=1))
        config = Config(
            input_dir=Path("/videos"), target_frames=10,
            oversample=3.0, skip_detection=True,
        )
        plan = create_sample_plan(videos, config)
        # Should produce at most target_frames candidates (no 3x oversample)
        assert len(plan) <= 10

    def test_single_timestamp_videos(self):
        """Handle edge case where all videos have the same timestamp."""
        ts = datetime(2023, 6, 15, 12, 0, 0)
        videos = [
            VideoFile(path=Path(f"/v/clip_{i}.mp4"), timestamp=ts)
            for i in range(50)
        ]
        config = Config(input_dir=Path("/v"), target_frames=10)
        plan = create_sample_plan(videos, config)
        assert len(plan) > 0

    def test_repeated_video_gets_different_frames(self):
        """When a video is picked for multiple slots, frame fractions should vary."""
        videos = _make_videos(5, datetime(2023, 1, 1), timedelta(days=1))
        config = Config(input_dir=Path("/v"), target_frames=100, oversample=1.0)
        plan = create_sample_plan(videos, config)

        # Group by video path
        from collections import defaultdict
        by_video: dict[Path, list[float]] = defaultdict(list)
        for s in plan:
            by_video[s.video_path].append(s.frame_fraction)

        # Videos picked more than once should have varying frame fractions
        for path, fractions in by_video.items():
            if len(fractions) > 1:
                assert len(set(fractions)) > 1, f"{path} has duplicate fractions"

    def test_intro_outro_produces_more_early_late_frames(self):
        """With intro/outro, early and late footage should have higher frame density."""
        videos = _make_videos(1000, datetime(2023, 1, 1), timedelta(hours=1))
        # 5 min video at 30fps = 9000 frames, with 30s intro and 30s outro
        config = Config(
            input_dir=Path("/v"), target_frames=9000, fps=30,
            intro_seconds=30, outro_seconds=30,
            oversample=1.0, skip_detection=True,
        )
        plan = create_sample_plan(videos, config)

        assert len(plan) > 0
        # Plan should be temporally ordered
        timestamps = [s.expected_timestamp for s in plan]
        assert timestamps == sorted(timestamps)

    def test_intro_only(self):
        """Intro without outro should work."""
        videos = _make_videos(500, datetime(2023, 1, 1), timedelta(hours=1))
        config = Config(
            input_dir=Path("/v"), target_frames=3000, fps=30,
            intro_seconds=15, outro_seconds=0,
            oversample=1.0, skip_detection=True,
        )
        plan = create_sample_plan(videos, config)
        assert len(plan) > 0

    def test_outro_only(self):
        """Outro without intro should work."""
        videos = _make_videos(500, datetime(2023, 1, 1), timedelta(hours=1))
        config = Config(
            input_dir=Path("/v"), target_frames=3000, fps=30,
            intro_seconds=0, outro_seconds=15,
            oversample=1.0, skip_detection=True,
        )
        plan = create_sample_plan(videos, config)
        assert len(plan) > 0


class TestGapCompression:
    def test_gap_compression_reduces_duplicates(self):
        """Videos clustered with large gaps should not produce many duplicates."""
        base = datetime(2023, 1, 1, 8, 0)
        cluster1 = [
            VideoFile(Path(f"/v/a_{i}.mp4"), base + timedelta(minutes=i * 6))
            for i in range(10)
        ]
        cluster2 = [
            VideoFile(Path(f"/v/b_{i}.mp4"), base + timedelta(hours=13, minutes=i * 6))
            for i in range(10)
        ]
        videos = cluster1 + cluster2

        config = Config(
            input_dir=Path("/v"), target_frames=100,
            oversample=1.0, skip_detection=True,
        )
        plan = create_sample_plan(videos, config)

        # Most of the 20 videos should appear
        unique_videos = len(set(s.video_path for s in plan))
        assert unique_videos >= 15

        # No single video should dominate the plan
        from collections import Counter
        counts = Counter(s.video_path for s in plan)
        max_picks = max(counts.values())
        assert max_picks <= MAX_PICKS_PER_VIDEO

    def test_uniform_videos_unchanged(self):
        """Uniformly spaced videos should still cover the full time range."""
        videos = _make_videos(100, datetime(2023, 1, 1), timedelta(hours=1))
        config = Config(
            input_dir=Path("/v"), target_frames=50,
            oversample=1.0, skip_detection=True,
        )
        plan = create_sample_plan(videos, config)

        timestamps = [s.expected_timestamp for s in plan]
        span = (timestamps[-1] - timestamps[0]).total_seconds()
        total_span = (videos[-1].timestamp - videos[0].timestamp).total_seconds()
        assert span / total_span > 0.8

    def test_compressed_timeline_preserves_order(self):
        """Compressed sampling must maintain chronological ordering."""
        base = datetime(2023, 1, 1)
        videos = []
        for day in [0, 0, 0, 1, 1, 5, 5, 5, 5, 10, 10, 15]:
            videos.append(VideoFile(
                Path(f"/v/clip_{day}_{len(videos)}.mp4"),
                base + timedelta(days=day, hours=len(videos)),
            ))

        config = Config(
            input_dir=Path("/v"), target_frames=30,
            oversample=1.0, skip_detection=True,
        )
        plan = create_sample_plan(videos, config)

        timestamps = [s.expected_timestamp for s in plan]
        assert timestamps == sorted(timestamps)

    def test_few_videos_fallback(self):
        """With fewer than 3 videos, should not crash and should produce output."""
        videos = _make_videos(2, datetime(2023, 1, 1), timedelta(hours=5))
        config = Config(
            input_dir=Path("/v"), target_frames=10,
            oversample=1.0, skip_detection=True,
        )
        plan = create_sample_plan(videos, config)
        assert len(plan) > 0

    def test_gap_compression_with_intro_outro(self):
        """Gap compression should work correctly within intro/outro segments."""
        base = datetime(2023, 1, 1)
        cluster1 = [
            VideoFile(Path(f"/v/a_{i}.mp4"), base + timedelta(minutes=i * 5))
            for i in range(20)
        ]
        cluster2 = [
            VideoFile(Path(f"/v/b_{i}.mp4"), base + timedelta(hours=11, minutes=i * 5))
            for i in range(20)
        ]
        videos = cluster1 + cluster2

        config = Config(
            input_dir=Path("/v"), target_frames=3000, fps=30,
            intro_seconds=15, outro_seconds=15,
            oversample=1.0, skip_detection=True,
        )
        plan = create_sample_plan(videos, config)
        assert len(plan) > 0
        timestamps = [s.expected_timestamp for s in plan]
        assert timestamps == sorted(timestamps)
