package main

import (
	"bytes"
	"fmt"
	"log"
	"os/exec"
	"strings"
)

// detectPerson runs the user-supplied detector command for a single frame.
// The command receives the raw BGR24 frame on stdin and two extra args: width height.
// Exit code 0 = person detected; any other exit code = no person.
// Returns true if a person is detected.
func detectPerson(detectorCmd string, frame []byte, width, height int) bool {
	parts := strings.Fields(detectorCmd)
	if len(parts) == 0 {
		return true
	}

	args := append(parts[1:], fmt.Sprintf("%d", width), fmt.Sprintf("%d", height))
	cmd := exec.Command(parts[0], args...)
	cmd.Stdin = bytes.NewReader(frame)

	err := cmd.Run()
	return err == nil // exit 0 = person found
}

// filterWithDetector takes an input frame channel and returns a new channel
// containing only frames where the detector reports a person.
// If detectorCmd is empty, all frames pass through.
func filterWithDetector(
	in <-chan ExtractedFrame,
	detectorCmd string,
	width, height int,
	total int,
) <-chan ExtractedFrame {
	out := make(chan ExtractedFrame, 4)
	go func() {
		defer close(out)

		if detectorCmd == "" {
			for ef := range in {
				out <- ef
			}
			return
		}

		accepted, rejected := 0, 0
		prog := newProgress("Detecting persons", total)

		for ef := range in {
			prog.increment()
			if detectPerson(detectorCmd, ef.Data, width, height) {
				accepted++
				out <- ef
			} else {
				rejected++
			}
		}
		prog.done()

		total := accepted + rejected
		rate := float64(0)
		if total > 0 {
			rate = float64(accepted) / float64(total) * 100
		}
		log.Printf("INFO: Detection: %d accepted, %d rejected (%.0f%% pass rate)",
			accepted, rejected, rate)
	}()
	return out
}
