package main

import (
	"fmt"
	"image"
	"log"
	"path/filepath"

	"gocv.io/x/gocv"
)

// extractFrames runs through the sample plan, extracting one frame per plan entry
// using gocv (OpenCV). Sends ExtractedFrame values on the returned channel.
// The caller must drain the channel; it is closed when done.
func extractFrames(plans []SamplePlan, width, height int) <-chan ExtractedFrame {
	ch := make(chan ExtractedFrame, 4)
	go func() {
		defer close(ch)

		var currentVC *gocv.VideoCapture
		var currentPath string

		closeVC := func() {
			if currentVC != nil {
				currentVC.Close()
				currentVC = nil
				currentPath = ""
			}
		}
		defer closeVC()

		for _, plan := range plans {
			// Reuse open VideoCapture when consecutive plans share the same video.
			if plan.VideoPath != currentPath {
				closeVC()
				vc, err := gocv.OpenVideoCapture(plan.VideoPath)
				if err != nil {
					log.Printf("WARN: Cannot open %s: %v", filepath.Base(plan.VideoPath), err)
					continue
				}
				currentVC = vc
				currentPath = plan.VideoPath
			}

			// Get duration from total frame count and FPS.
			totalFrames := currentVC.Get(gocv.VideoCaptureFrameCount)
			fps := currentVC.Get(gocv.VideoCaptureFPS)
			if totalFrames <= 0 || fps <= 0 {
				log.Printf("WARN: Cannot read properties of %s, skipping",
					filepath.Base(plan.VideoPath))
				closeVC()
				continue
			}

			// Seek to target position in milliseconds.
			seekMs := plan.FrameFraction * (totalFrames / fps) * 1000.0
			currentVC.Set(gocv.VideoCapturePosMsec, seekMs)

			frame := gocv.NewMat()
			if ok := currentVC.Read(&frame); !ok || frame.Empty() {
				frame.Close()
				log.Printf("WARN: Failed to read frame from %s", filepath.Base(plan.VideoPath))
				continue
			}

			// Resize to target resolution.
			resized := gocv.NewMat()
			gocv.Resize(frame, &resized, image.Pt(width, height), 0, 0, gocv.InterpolationLinear)
			frame.Close()

			data := make([]byte, width*height*3)
			copy(data, resized.ToBytes())
			resized.Close()

			ch <- ExtractedFrame{
				Data:      data,
				Timestamp: plan.ExpectedTimestamp,
				Source:    plan.VideoPath,
			}
		}
	}()
	return ch
}

// durationSeconds returns the duration of a video in seconds using gocv.
// Falls back to ffprobe if gocv cannot open the file.
// Results are cached in the provided map.
func durationSeconds(path string, cache map[string]float64) (float64, bool) {
	if d, ok := cache[path]; ok {
		return d, true
	}
	vc, err := gocv.OpenVideoCapture(path)
	if err != nil {
		// Fall back to ffprobe
		return probeDuration(path, cache)
	}
	defer vc.Close()
	totalFrames := vc.Get(gocv.VideoCaptureFrameCount)
	fps := vc.Get(gocv.VideoCaptureFPS)
	if totalFrames <= 0 || fps <= 0 {
		return probeDuration(path, cache)
	}
	d := totalFrames / fps
	cache[path] = d
	return d, true
}

// durationCache maps video path → duration in seconds.
var durationCache = make(map[string]float64)

// probeDurationCached is the old ffprobe-based lookup, kept as a fallback.
// It delegates to probeDuration in discover.go.
func probeDurationCached(path string) (float64, bool) {
	return durationSeconds(path, durationCache)
}

// formatSeekTime formats a duration as HH:MM:SS.mmm for ffmpeg -ss argument.
// Kept for use in compose.go if needed.
func formatSeekTime(seconds float64) string {
	return fmt.Sprintf("%.6f", seconds)
}
