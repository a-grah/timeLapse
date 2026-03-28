package main

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

// --- parseFilenameTimestamp ---

func TestParseFilenameTimestamp_CompactUnderscore(t *testing.T) {
	ts, ok := parseFilenameTimestamp("20230415_143522.mp4")
	if !ok {
		t.Fatal("expected match")
	}
	want := time.Date(2023, 4, 15, 14, 35, 22, 0, time.Local)
	if !ts.Equal(want) {
		t.Errorf("got %v, want %v", ts, want)
	}
}

func TestParseFilenameTimestamp_CompactDash(t *testing.T) {
	ts, ok := parseFilenameTimestamp("20230415-143522.mp4")
	if !ok {
		t.Fatal("expected match")
	}
	want := time.Date(2023, 4, 15, 14, 35, 22, 0, time.Local)
	if !ts.Equal(want) {
		t.Errorf("got %v, want %v", ts, want)
	}
}

func TestParseFilenameTimestamp_ISO(t *testing.T) {
	ts, ok := parseFilenameTimestamp("clip_2023-04-15T14:35:22.mp4")
	if !ok {
		t.Fatal("expected match")
	}
	want := time.Date(2023, 4, 15, 14, 35, 22, 0, time.Local)
	if !ts.Equal(want) {
		t.Errorf("got %v, want %v", ts, want)
	}
}

func TestParseFilenameTimestamp_DashSeparated(t *testing.T) {
	ts, ok := parseFilenameTimestamp("2023-04-15_14-35-22.mp4")
	if !ok {
		t.Fatal("expected match")
	}
	want := time.Date(2023, 4, 15, 14, 35, 22, 0, time.Local)
	if !ts.Equal(want) {
		t.Errorf("got %v, want %v", ts, want)
	}
}

func TestParseFilenameTimestamp_Unix10Digit(t *testing.T) {
	// 1681569322 is in 2023
	ts, ok := parseFilenameTimestamp("clip_1681569322.mp4")
	if !ok {
		t.Fatal("expected match")
	}
	if ts.Year() != 2023 {
		t.Errorf("expected year 2023, got %d", ts.Year())
	}
}

func TestParseFilenameTimestamp_Unix13Digit(t *testing.T) {
	ts, ok := parseFilenameTimestamp("clip_1681569322000.mp4")
	if !ok {
		t.Fatal("expected match")
	}
	if ts.Year() != 2023 {
		t.Errorf("expected year 2023, got %d", ts.Year())
	}
}

func TestParseFilenameTimestamp_NoMatch(t *testing.T) {
	_, ok := parseFilenameTimestamp("random_clip.mp4")
	if ok {
		t.Error("expected no match for random filename")
	}
}

func TestParseFilenameTimestamp_InvalidDate(t *testing.T) {
	// Month 99 is invalid
	_, ok := parseFilenameTimestamp("20239915_143522.mp4")
	if ok {
		t.Error("expected no match for invalid date")
	}
}

// --- parseWyzePath ---

func TestParseWyzePath_Valid(t *testing.T) {
	ts, ok := parseWyzePath("/sd/record/20230415/14/35.mp4")
	if !ok {
		t.Fatal("expected match")
	}
	want := time.Date(2023, 4, 15, 14, 35, 0, 0, time.Local)
	if !ts.Equal(want) {
		t.Errorf("got %v, want %v", ts, want)
	}
}

func TestParseWyzePath_Windows(t *testing.T) {
	ts, ok := parseWyzePath(`C:\sd\record\20230415\14\35.mp4`)
	if !ok {
		t.Fatal("expected match on Windows-style path")
	}
	if ts.Year() != 2023 {
		t.Errorf("expected year 2023, got %d", ts.Year())
	}
}

func TestParseWyzePath_NoMatch(t *testing.T) {
	_, ok := parseWyzePath("/home/user/videos/clip.mp4")
	if ok {
		t.Error("expected no match for non-Wyze path")
	}
}

// --- findVideoFiles ---

func TestFindVideoFiles_FindsVideoFiles(t *testing.T) {
	dir := t.TempDir()
	touch(t, dir, "a.mp4")
	touch(t, dir, "b.avi")
	touch(t, dir, "c.txt")

	cfg := &Config{InputDir: dir, Recursive: true, Workers: 1}
	files, err := findVideoFiles(cfg)
	if err != nil {
		t.Fatal(err)
	}
	extSet := map[string]bool{}
	for _, f := range files {
		extSet[filepath.Ext(f)] = true
	}
	if !extSet[".mp4"] || !extSet[".avi"] {
		t.Errorf("expected .mp4 and .avi, got %v", extSet)
	}
	if extSet[".txt"] {
		t.Error("should not include .txt files")
	}
}

func TestFindVideoFiles_Recursive(t *testing.T) {
	dir := t.TempDir()
	sub := filepath.Join(dir, "sub")
	os.Mkdir(sub, 0755)
	touch(t, dir, "a.mp4")
	touch(t, sub, "b.mp4")

	cfg := &Config{InputDir: dir, Recursive: true, Workers: 1}
	files, err := findVideoFiles(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if len(files) != 2 {
		t.Errorf("expected 2 files, got %d", len(files))
	}
}

func TestFindVideoFiles_NonRecursive(t *testing.T) {
	dir := t.TempDir()
	sub := filepath.Join(dir, "sub")
	os.Mkdir(sub, 0755)
	touch(t, dir, "a.mp4")
	touch(t, sub, "b.mp4")

	cfg := &Config{InputDir: dir, Recursive: false, Workers: 1}
	files, err := findVideoFiles(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if len(files) != 1 {
		t.Errorf("expected 1 file, got %d", len(files))
	}
}

func TestFindVideoFiles_NoVideos(t *testing.T) {
	dir := t.TempDir()
	touch(t, dir, "readme.txt")

	cfg := &Config{InputDir: dir, Recursive: true, Workers: 1}
	_, err := findVideoFiles(cfg)
	if err == nil {
		t.Error("expected error when no videos found")
	}
}

// helper
func touch(t *testing.T, dir, name string) {
	t.Helper()
	f, err := os.Create(filepath.Join(dir, name))
	if err != nil {
		t.Fatal(err)
	}
	f.Close()
}
