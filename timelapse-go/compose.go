package main

import (
	"bytes"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
)

// composeVideo pipes frames to ffmpeg and encodes an H.264 MP4.
// frames is a channel of ExtractedFrame (already filtered/detected).
// Returns the output path on success.
func composeVideo(frames <-chan ExtractedFrame, cfg *Config) (string, error) {
	output := cfg.Output

	// Ensure parent directory exists
	if dir := filepath.Dir(output); dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0755); err != nil {
			return "", fmt.Errorf("cannot create output directory: %w", err)
		}
	}

	ffmpegCmd := exec.Command(
		"ffmpeg", "-y",
		"-f", "rawvideo",
		"-vcodec", "rawvideo",
		"-s", fmt.Sprintf("%dx%d", cfg.Width, cfg.Height),
		"-pix_fmt", "bgr24",
		"-r", fmt.Sprintf("%d", cfg.FPS),
		"-i", "-",
		"-c:v", "libx264",
		"-preset", "medium",
		"-crf", "23",
		"-pix_fmt", "yuv420p",
		"-movflags", "+faststart",
		output,
	)

	stdin, err := ffmpegCmd.StdinPipe()
	if err != nil {
		return "", fmt.Errorf("stdin pipe: %w", err)
	}
	ffmpegCmd.Stdout = nil
	// Capture stderr to show on failure; in verbose mode also stream it live.
	var stderrBuf bytes.Buffer
	if cfg.Verbose {
		ffmpegCmd.Stderr = os.Stderr
	} else {
		ffmpegCmd.Stderr = &stderrBuf
	}

	log.Printf("INFO: Encoding to %s (streaming)...", output)
	if err := ffmpegCmd.Start(); err != nil {
		return "", fmt.Errorf("ffmpeg start: %w", err)
	}

	frameCount := 0
	var writeErr error
	for ef := range frames {
		frame := ef.Data
		if cfg.TimestampOverlay {
			frame = burnTimestamp(frame, cfg.Width, cfg.Height, ef.Timestamp)
		}
		if _, err := stdin.Write(frame); err != nil {
			writeErr = err
			// Drain channel so producer goroutine doesn't block
			for range frames {
			}
			break
		}
		frameCount++
	}

	stdin.Close()
	waitErr := ffmpegCmd.Wait()

	if writeErr != nil {
		os.Remove(output)
		return "", fmt.Errorf("ffmpeg pipe broken: %w", writeErr)
	}
	if waitErr != nil {
		os.Remove(output)
		if stderrBuf.Len() > 0 {
			return "", fmt.Errorf("ffmpeg encoding failed: %w\n%s", waitErr, stderrBuf.String())
		}
		return "", fmt.Errorf("ffmpeg encoding failed: %w", waitErr)
	}
	if frameCount == 0 {
		os.Remove(output)
		return "", fmt.Errorf("no frames passed detection — try --skip-detection or lower --confidence")
	}

	info, _ := os.Stat(output)
	sizeMB := float64(0)
	if info != nil {
		sizeMB = float64(info.Size()) / (1024 * 1024)
	}
	duration := float64(frameCount) / float64(cfg.FPS)
	log.Printf("INFO: Output: %s (%.1f MB, %.1fs, %d frames)",
		output, sizeMB, duration, frameCount)

	return output, nil
}
