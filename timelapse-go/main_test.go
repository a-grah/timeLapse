package main

import "testing"

// --- parseDuration ---

func TestParseDuration_Seconds(t *testing.T) {
	n, err := parseDuration("30s")
	if err != nil || n != 30 {
		t.Errorf("30s: got %d, err %v", n, err)
	}
}

func TestParseDuration_Minutes(t *testing.T) {
	n, err := parseDuration("5m")
	if err != nil || n != 300 {
		t.Errorf("5m: got %d, err %v", n, err)
	}
}

func TestParseDuration_Hours(t *testing.T) {
	n, err := parseDuration("1h")
	if err != nil || n != 3600 {
		t.Errorf("1h: got %d, err %v", n, err)
	}
}

func TestParseDuration_Mixed(t *testing.T) {
	n, err := parseDuration("2m30s")
	if err != nil || n != 150 {
		t.Errorf("2m30s: got %d, err %v", n, err)
	}
}

func TestParseDuration_PlainInt(t *testing.T) {
	n, err := parseDuration("120")
	if err != nil || n != 120 {
		t.Errorf("120: got %d, err %v", n, err)
	}
}

func TestParseDuration_Invalid(t *testing.T) {
	_, err := parseDuration("abc")
	if err == nil {
		t.Error("expected error for invalid duration")
	}
}

// --- parseResolution ---

func TestParseResolution_Valid(t *testing.T) {
	w, h, err := parseResolution("1280x720")
	if err != nil || w != 1280 || h != 720 {
		t.Errorf("1280x720: got %dx%d, err %v", w, h, err)
	}
}

func TestParseResolution_Uppercase(t *testing.T) {
	w, h, err := parseResolution("1920X1080")
	if err != nil || w != 1920 || h != 1080 {
		t.Errorf("1920X1080: got %dx%d, err %v", w, h, err)
	}
}

func TestParseResolution_Invalid(t *testing.T) {
	_, _, err := parseResolution("badformat")
	if err == nil {
		t.Error("expected error for bad resolution format")
	}
}

func TestParseResolution_ZeroDimension(t *testing.T) {
	_, _, err := parseResolution("0x720")
	if err == nil {
		t.Error("expected error for zero width")
	}
}
