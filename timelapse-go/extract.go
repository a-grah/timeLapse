package main

import (
	"fmt"
	"io"
	"log"
	"os/exec"
	"path/filepath"
)

// durationCache maps video path → duration in seconds to avoid repeated ffprobe calls.
var durationCache = make(map[string]float64)

// extractFrames runs through the sample plan, extracting one frame per plan entry
// via ffmpeg. Sends ExtractedFrame values on the returned channel.
// The caller must drain the channel; it is closed when done.
func extractFrames(plans []SamplePlan, width, height int) <-chan ExtractedFrame {
	ch := make(chan ExtractedFrame, 4)
	go func() {
		defer close(ch)
		frameSize := width * height * 3 // BGR24

		for _, plan := range plans {
			duration, ok := probeDuration(plan.VideoPath, durationCache)
			if !ok {
				log.Printf("WARN: Cannot determine duration of %s, skipping",
					filepath.Base(plan.VideoPath))
				continue
			}

			seekTime := duration * plan.FrameFraction

			cmd := exec.Command(
				"ffmpeg",
				"-ss", fmt.Sprintf("%.6f", seekTime),
				"-i", plan.VideoPath,
				"-frames:v", "1",
				"-s", fmt.Sprintf("%dx%d", width, height),
				"-f", "rawvideo",
				"-pix_fmt", "bgr24",
				"pipe:1",
			)

			stdout, err := cmd.StdoutPipe()
			if err != nil {
				log.Printf("WARN: stdout pipe for %s: %v", filepath.Base(plan.VideoPath), err)
				continue
			}
			if err := cmd.Start(); err != nil {
				log.Printf("WARN: ffmpeg start for %s: %v", filepath.Base(plan.VideoPath), err)
				continue
			}

			data := make([]byte, frameSize)
			_, err = io.ReadFull(stdout, data)
			// Drain remaining output so ffmpeg can exit cleanly
			io.Copy(io.Discard, stdout)
			cmd.Wait()

			if err != nil {
				log.Printf("WARN: Failed to read frame from %s: %v",
					filepath.Base(plan.VideoPath), err)
				continue
			}

			ch <- ExtractedFrame{
				Data:      data,
				Timestamp: plan.ExpectedTimestamp,
				Source:    plan.VideoPath,
			}
		}
	}()
	return ch
}
