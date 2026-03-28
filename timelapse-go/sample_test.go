package main

import (
	"fmt"
	"sort"
	"testing"
	"time"
)

func makeVideos(count int, start time.Time, interval time.Duration) []VideoFile {
	videos := make([]VideoFile, count)
	for i := 0; i < count; i++ {
		videos[i] = VideoFile{
			Path:      fmt.Sprintf("/videos/clip_%04d.mp4", i),
			Timestamp: start.Add(interval * time.Duration(i)),
		}
	}
	return videos
}

func defaultCfg() *Config {
	return &Config{
		InputDir:      "/videos",
		TargetFrames:  10,
		FPS:           30,
		Oversample:    2.0,
		SkipDetection: false,
		Workers:       4,
	}
}

// --- TestCreateSamplePlan ---

func TestCreateSamplePlan_Basic(t *testing.T) {
	videos := makeVideos(100, time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC), time.Hour)
	cfg := defaultCfg()
	cfg.TargetFrames = 10
	cfg.Oversample = 2.0
	plan := createSamplePlan(videos, cfg)

	if len(plan) == 0 {
		t.Fatal("expected non-empty plan")
	}
	if len(plan) > 20 { // 10 * 2.0
		t.Errorf("plan length %d exceeds target*oversample (20)", len(plan))
	}
}

func TestCreateSamplePlan_TemporalSpread(t *testing.T) {
	videos := makeVideos(1000, time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC), time.Hour)
	cfg := defaultCfg()
	cfg.TargetFrames = 50
	cfg.Oversample = 1.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)

	timestamps := make([]time.Time, len(plan))
	for i, s := range plan {
		timestamps[i] = s.ExpectedTimestamp
	}

	first := timestamps[0]
	last := timestamps[len(timestamps)-1]
	span := last.Sub(first).Seconds()
	totalSpan := videos[len(videos)-1].Timestamp.Sub(videos[0].Timestamp).Seconds()

	if span/totalSpan < 0.8 {
		t.Errorf("temporal spread %.2f < 0.8 (first=%v last=%v)", span/totalSpan, first, last)
	}
}

func TestCreateSamplePlan_SkipDetectionNoOversample(t *testing.T) {
	videos := makeVideos(100, time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC), time.Hour)
	cfg := defaultCfg()
	cfg.TargetFrames = 10
	cfg.Oversample = 3.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)

	if len(plan) > 10 {
		t.Errorf("skip_detection=true should not oversample: got %d frames, want ≤10", len(plan))
	}
}

func TestCreateSamplePlan_SingleTimestamp(t *testing.T) {
	ts := time.Date(2023, 6, 15, 12, 0, 0, 0, time.UTC)
	videos := make([]VideoFile, 50)
	for i := range videos {
		videos[i] = VideoFile{Path: fmt.Sprintf("/v/clip_%d.mp4", i), Timestamp: ts}
	}
	cfg := defaultCfg()
	cfg.TargetFrames = 10
	plan := createSamplePlan(videos, cfg)

	if len(plan) == 0 {
		t.Error("expected non-empty plan for single-timestamp videos")
	}
}

func TestCreateSamplePlan_RepeatedVideosDifferentFrames(t *testing.T) {
	videos := makeVideos(5, time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC), 24*time.Hour)
	cfg := defaultCfg()
	cfg.TargetFrames = 100
	cfg.Oversample = 1.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)

	byVideo := map[string][]float64{}
	for _, s := range plan {
		byVideo[s.VideoPath] = append(byVideo[s.VideoPath], s.FrameFraction)
	}
	for path, fracs := range byVideo {
		if len(fracs) <= 1 {
			continue
		}
		unique := map[float64]bool{}
		for _, f := range fracs {
			unique[f] = true
		}
		if len(unique) <= 1 {
			t.Errorf("%s picked %d times but all at same frame fraction", path, len(fracs))
		}
	}
}

func TestCreateSamplePlan_IntroOutroOrdered(t *testing.T) {
	videos := makeVideos(1000, time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC), time.Hour)
	cfg := defaultCfg()
	cfg.TargetFrames = 9000
	cfg.FPS = 30
	cfg.IntroSeconds = 30
	cfg.OutroSeconds = 30
	cfg.Oversample = 1.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)

	if len(plan) == 0 {
		t.Fatal("expected non-empty plan")
	}
	timestamps := make([]time.Time, len(plan))
	for i, s := range plan {
		timestamps[i] = s.ExpectedTimestamp
	}
	if !sort.SliceIsSorted(timestamps, func(i, j int) bool {
		return timestamps[i].Before(timestamps[j])
	}) {
		t.Error("intro/outro plan is not chronologically ordered")
	}
}

func TestCreateSamplePlan_IntroOnly(t *testing.T) {
	videos := makeVideos(500, time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC), time.Hour)
	cfg := defaultCfg()
	cfg.TargetFrames = 3000
	cfg.FPS = 30
	cfg.IntroSeconds = 15
	cfg.Oversample = 1.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)
	if len(plan) == 0 {
		t.Error("expected non-empty plan with intro only")
	}
}

func TestCreateSamplePlan_OutroOnly(t *testing.T) {
	videos := makeVideos(500, time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC), time.Hour)
	cfg := defaultCfg()
	cfg.TargetFrames = 3000
	cfg.FPS = 30
	cfg.OutroSeconds = 15
	cfg.Oversample = 1.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)
	if len(plan) == 0 {
		t.Error("expected non-empty plan with outro only")
	}
}

// --- TestGapCompression ---

func TestGapCompression_ReducesDuplicates(t *testing.T) {
	base := time.Date(2023, 1, 1, 8, 0, 0, 0, time.UTC)
	var videos []VideoFile
	for i := 0; i < 10; i++ {
		videos = append(videos, VideoFile{
			Path:      fmt.Sprintf("/v/a_%d.mp4", i),
			Timestamp: base.Add(time.Duration(i*6) * time.Minute),
		})
	}
	for i := 0; i < 10; i++ {
		videos = append(videos, VideoFile{
			Path:      fmt.Sprintf("/v/b_%d.mp4", i),
			Timestamp: base.Add(13*time.Hour + time.Duration(i*6)*time.Minute),
		})
	}
	sort.Slice(videos, func(i, j int) bool {
		return videos[i].Timestamp.Before(videos[j].Timestamp)
	})

	cfg := defaultCfg()
	cfg.TargetFrames = 100
	cfg.Oversample = 1.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)

	uniqueVideos := map[string]bool{}
	pickCount := map[string]int{}
	for _, s := range plan {
		uniqueVideos[s.VideoPath] = true
		pickCount[s.VideoPath]++
	}
	if len(uniqueVideos) < 15 {
		t.Errorf("expected ≥15 unique videos, got %d", len(uniqueVideos))
	}
	for path, count := range pickCount {
		if count > MaxPicksPerVideo {
			t.Errorf("%s picked %d times, exceeds MAX_PICKS_PER_VIDEO=%d", path, count, MaxPicksPerVideo)
		}
	}
}

func TestGapCompression_PreservesChronologicalOrder(t *testing.T) {
	base := time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC)
	days := []int{0, 0, 0, 1, 1, 5, 5, 5, 5, 10, 10, 15}
	videos := make([]VideoFile, len(days))
	for i, d := range days {
		videos[i] = VideoFile{
			Path:      fmt.Sprintf("/v/clip_%d_%d.mp4", d, i),
			Timestamp: base.Add(time.Duration(d)*24*time.Hour + time.Duration(i)*time.Hour),
		}
	}

	cfg := defaultCfg()
	cfg.TargetFrames = 30
	cfg.Oversample = 1.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)

	timestamps := make([]time.Time, len(plan))
	for i, s := range plan {
		timestamps[i] = s.ExpectedTimestamp
	}
	if !sort.SliceIsSorted(timestamps, func(i, j int) bool {
		return timestamps[i].Before(timestamps[j])
	}) {
		t.Error("plan is not chronologically ordered")
	}
}

func TestGapCompression_FewVideosFallback(t *testing.T) {
	videos := makeVideos(2, time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC), 5*time.Hour)
	cfg := defaultCfg()
	cfg.TargetFrames = 10
	cfg.Oversample = 1.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)
	if len(plan) == 0 {
		t.Error("expected non-empty plan for 2 videos")
	}
}

func TestGapCompression_UniformVideosSpread(t *testing.T) {
	videos := makeVideos(100, time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC), time.Hour)
	cfg := defaultCfg()
	cfg.TargetFrames = 50
	cfg.Oversample = 1.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)

	timestamps := make([]time.Time, len(plan))
	for i, s := range plan {
		timestamps[i] = s.ExpectedTimestamp
	}
	span := timestamps[len(timestamps)-1].Sub(timestamps[0]).Seconds()
	totalSpan := videos[len(videos)-1].Timestamp.Sub(videos[0].Timestamp).Seconds()
	if span/totalSpan < 0.8 {
		t.Errorf("uniform videos: span %.2f < 0.8 of total", span/totalSpan)
	}
}

func TestGapCompression_WithIntroOutro(t *testing.T) {
	base := time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC)
	var videos []VideoFile
	for i := 0; i < 20; i++ {
		videos = append(videos, VideoFile{
			Path:      fmt.Sprintf("/v/a_%d.mp4", i),
			Timestamp: base.Add(time.Duration(i*5) * time.Minute),
		})
	}
	for i := 0; i < 20; i++ {
		videos = append(videos, VideoFile{
			Path:      fmt.Sprintf("/v/b_%d.mp4", i),
			Timestamp: base.Add(11*time.Hour + time.Duration(i*5)*time.Minute),
		})
	}
	sort.Slice(videos, func(i, j int) bool {
		return videos[i].Timestamp.Before(videos[j].Timestamp)
	})

	cfg := defaultCfg()
	cfg.TargetFrames = 3000
	cfg.FPS = 30
	cfg.IntroSeconds = 15
	cfg.OutroSeconds = 15
	cfg.Oversample = 1.0
	cfg.SkipDetection = true
	plan := createSamplePlan(videos, cfg)

	if len(plan) == 0 {
		t.Fatal("expected non-empty plan")
	}
	timestamps := make([]time.Time, len(plan))
	for i, s := range plan {
		timestamps[i] = s.ExpectedTimestamp
	}
	if !sort.SliceIsSorted(timestamps, func(i, j int) bool {
		return timestamps[i].Before(timestamps[j])
	}) {
		t.Error("intro/outro gap compression plan is not ordered")
	}
}
