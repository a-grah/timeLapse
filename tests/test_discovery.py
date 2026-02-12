import os
from datetime import datetime
from pathlib import Path

import pytest

from timelapse.config import Config
from timelapse.discovery import VideoFile, find_video_files
from timelapse.utils import (
    parse_filename_timestamp,
    parse_wyze_path,
)


class TestParseFilenameTimestamp:
    def test_yyyymmdd_hhmmss_underscore(self):
        ts = parse_filename_timestamp("20230415_143522.mp4")
        assert ts == datetime(2023, 4, 15, 14, 35, 22)

    def test_yyyymmdd_hhmmss_dash(self):
        ts = parse_filename_timestamp("20230415-143522.mp4")
        assert ts == datetime(2023, 4, 15, 14, 35, 22)

    def test_iso_format(self):
        ts = parse_filename_timestamp("clip_2023-04-15T14:35:22.mp4")
        assert ts == datetime(2023, 4, 15, 14, 35, 22)

    def test_dash_separated(self):
        ts = parse_filename_timestamp("2023-04-15_14-35-22.mp4")
        assert ts == datetime(2023, 4, 15, 14, 35, 22)

    def test_unix_timestamp_10digit(self):
        # 1681569322 = 2023-04-15 14:35:22 UTC (approx)
        ts = parse_filename_timestamp("clip_1681569322.mp4")
        assert ts is not None
        assert ts.year == 2023

    def test_unix_timestamp_13digit(self):
        ts = parse_filename_timestamp("clip_1681569322000.mp4")
        assert ts is not None
        assert ts.year == 2023

    def test_no_timestamp(self):
        ts = parse_filename_timestamp("random_clip.mp4")
        assert ts is None

    def test_invalid_date(self):
        # Month 99 is invalid
        ts = parse_filename_timestamp("20239915_143522.mp4")
        assert ts is None


class TestParseWyzePath:
    def test_wyze_path(self):
        path = Path("/sd/record/20230415/14/35.mp4")
        ts = parse_wyze_path(path)
        assert ts == datetime(2023, 4, 15, 14, 35)

    def test_non_wyze_path(self):
        path = Path("/home/user/videos/clip.mp4")
        ts = parse_wyze_path(path)
        assert ts is None


class TestFindVideoFiles:
    def test_finds_video_files(self, tmp_dir):
        (tmp_dir / "a.mp4").touch()
        (tmp_dir / "b.avi").touch()
        (tmp_dir / "c.txt").touch()  # not a video

        config = Config(input_dir=tmp_dir)
        files = find_video_files(config)
        extensions = {f.suffix for f in files}
        assert extensions == {".mp4", ".avi"}

    def test_recursive(self, tmp_dir):
        sub = tmp_dir / "sub"
        sub.mkdir()
        (tmp_dir / "a.mp4").touch()
        (sub / "b.mp4").touch()

        config = Config(input_dir=tmp_dir, recursive=True)
        files = find_video_files(config)
        assert len(files) == 2

    def test_non_recursive(self, tmp_dir):
        sub = tmp_dir / "sub"
        sub.mkdir()
        (tmp_dir / "a.mp4").touch()
        (sub / "b.mp4").touch()

        config = Config(input_dir=tmp_dir, recursive=False)
        files = find_video_files(config)
        assert len(files) == 1

    def test_no_videos_found(self, tmp_dir):
        (tmp_dir / "readme.txt").touch()
        config = Config(input_dir=tmp_dir)
        with pytest.raises(SystemExit, match="No video files"):
            find_video_files(config)
