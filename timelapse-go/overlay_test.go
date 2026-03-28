package main

import (
	"bytes"
	"testing"
	"time"
)

func TestBurnTimestamp_PreservesDimensions(t *testing.T) {
	w, h := 1280, 720
	size := w * h * 3
	data := make([]byte, size)
	ts := time.Date(2023, 4, 15, 14, 35, 0, 0, time.Local)

	out := burnTimestamp(data, w, h, ts)

	if len(out) != size {
		t.Errorf("output length %d != expected %d", len(out), size)
	}
}

func TestBurnTimestamp_ModifiesPixels(t *testing.T) {
	w, h := 1280, 720
	data := make([]byte, w*h*3) // all zeros (black frame)
	ts := time.Date(2023, 4, 15, 14, 35, 0, 0, time.Local)

	out := burnTimestamp(data, w, h, ts)

	// The rendered text should have changed at least some pixels
	if bytes.Equal(data, out) {
		t.Error("burnTimestamp did not modify any pixels")
	}
}

func TestBurnTimestamp_DoesNotPanic_SmallFrame(t *testing.T) {
	// Small frame: should clamp pixel coordinates without panicking
	w, h := 64, 48
	data := make([]byte, w*h*3)
	ts := time.Now()
	_ = burnTimestamp(data, w, h, ts)
}
