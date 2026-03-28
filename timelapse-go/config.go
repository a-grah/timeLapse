package main

import "time"

const (
	LingerFactor      = 3.0
	GapCapMultiplier  = 4.0
	MinGapCapSeconds  = 600.0
	MaxPicksPerVideo  = 8
	DefaultFPS        = 30
	DefaultWidth      = 1280
	DefaultHeight     = 720
	DefaultOversample = 3.0
	DefaultWorkers    = 8
	DefaultFrames     = 3600 // 2 minutes at 30fps
)

var videoExtensions = map[string]bool{
	".mp4":  true,
	".avi":  true,
	".mov":  true,
	".mkv":  true,
	".webm": true,
	".ts":   true,
	".m4v":  true,
}

// Config holds all settings for a timelapse run.
type Config struct {
	InputDir        string
	Output          string
	TargetFrames    int
	FPS             int
	Recursive       bool
	Width           int
	Height          int
	TimestampOverlay bool
	IntroSeconds    float64
	OutroSeconds    float64
	Oversample      float64
	SkipDetection   bool
	DryRun          bool
	Workers         int
	Verbose         bool
	Detector        string    // optional external detector command
}

// VideoFile pairs a path with its resolved recording timestamp.
type VideoFile struct {
	Path      string
	Timestamp time.Time
}

// SamplePlan describes one frame to extract.
type SamplePlan struct {
	VideoPath         string
	FrameFraction     float64   // 0.0–1.0 position within the video
	ExpectedTimestamp time.Time
}

// ExtractedFrame holds raw BGR24 pixel data for one frame.
type ExtractedFrame struct {
	Data      []byte    // W*H*3 bytes, BGR24
	Timestamp time.Time
	Source    string
}
