package main

import (
	"encoding/json"
	"fmt"
	"io/fs"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Timestamp regex patterns, in priority order after Wyze path check.
var (
	// Wyze SD card path: record/YYYYMMDD/HH/MM
	reWyzePath = regexp.MustCompile(`record[/\\](\d{4})(\d{2})(\d{2})[/\\](\d{2})[/\\](\d{2})`)

	// YYYYMMDD_HHMMSS or YYYYMMDD-HHMMSS (RE2 has no backreferences, use loose sep)
	reCompact = regexp.MustCompile(`(\d{4})[\-_]?(\d{2})[\-_]?(\d{2})[\-_](\d{2})[\-_]?(\d{2})[\-_]?(\d{2})`)

	// YYYY-MM-DDTHH:MM:SS (ISO 8601)
	reISO = regexp.MustCompile(`(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})`)

	// YYYY-MM-DD_HH-MM-SS
	reISO2 = regexp.MustCompile(`(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})`)

	// 13-digit millisecond Unix timestamp
	reUnixMS = regexp.MustCompile(`(?:^|[^\d])(\d{13})(?:[^\d]|$)`)

	// 10-digit second Unix timestamp
	reUnixSec = regexp.MustCompile(`(?:^|[^\d])(\d{10})(?:[^\d]|$)`)
)

func parseWyzePath(path string) (time.Time, bool) {
	m := reWyzePath.FindStringSubmatch(path)
	if m == nil {
		return time.Time{}, false
	}
	year, _ := strconv.Atoi(m[1])
	month, _ := strconv.Atoi(m[2])
	day, _ := strconv.Atoi(m[3])
	hour, _ := strconv.Atoi(m[4])
	min, _ := strconv.Atoi(m[5])
	t := time.Date(year, time.Month(month), day, hour, min, 0, 0, time.Local)
	if t.Year() < 2015 || t.Year() > 2030 {
		return time.Time{}, false
	}
	return t, true
}

func parseFilenameTimestamp(name string) (time.Time, bool) {
	// ISO 8601: YYYY-MM-DDTHH:MM:SS
	if m := reISO.FindStringSubmatch(name); m != nil {
		t := parseFields(m[1], m[2], m[3], m[4], m[5], m[6])
		if !t.IsZero() {
			return t, true
		}
	}
	// YYYY-MM-DD_HH-MM-SS
	if m := reISO2.FindStringSubmatch(name); m != nil {
		t := parseFields(m[1], m[2], m[3], m[4], m[5], m[6])
		if !t.IsZero() {
			return t, true
		}
	}
	// YYYYMMDD_HHMMSS (compact with optional separators)
	// groups: year, month, day, hour, min, sec
	if m := reCompact.FindStringSubmatch(name); m != nil {
		t := parseFields(m[1], m[2], m[3], m[4], m[5], m[6])
		if !t.IsZero() {
			return t, true
		}
	}
	// 13-digit ms Unix timestamp
	if m := reUnixMS.FindStringSubmatch(name); m != nil {
		ms, err := strconv.ParseInt(m[1], 10, 64)
		if err == nil {
			t := time.UnixMilli(ms).Local()
			if t.Year() >= 2015 && t.Year() <= 2030 {
				return t, true
			}
		}
	}
	// 10-digit sec Unix timestamp
	if m := reUnixSec.FindStringSubmatch(name); m != nil {
		sec, err := strconv.ParseInt(m[1], 10, 64)
		if err == nil {
			t := time.Unix(sec, 0).Local()
			if t.Year() >= 2015 && t.Year() <= 2030 {
				return t, true
			}
		}
	}
	return time.Time{}, false
}

func parseFields(year, month, day, hour, min, sec string) time.Time {
	y, e1 := strconv.Atoi(year)
	mo, e2 := strconv.Atoi(month)
	d, e3 := strconv.Atoi(day)
	h, e4 := strconv.Atoi(hour)
	mi, e5 := strconv.Atoi(min)
	s, e6 := strconv.Atoi(sec)
	if e1 != nil || e2 != nil || e3 != nil || e4 != nil || e5 != nil || e6 != nil {
		return time.Time{}
	}
	t := time.Date(y, time.Month(mo), d, h, mi, s, 0, time.Local)
	if t.Year() < 2015 || t.Year() > 2030 {
		return time.Time{}
	}
	return t
}

// ffprobeResult matches the JSON structure returned by ffprobe -show_format.
type ffprobeResult struct {
	Format struct {
		Duration string `json:"duration"`
		Tags     struct {
			CreationTime string `json:"creation_time"`
		} `json:"tags"`
	} `json:"format"`
}

func probeCreationTime(path string) (time.Time, bool) {
	out, err := exec.Command(
		"ffprobe", "-v", "quiet",
		"-print_format", "json",
		"-show_format",
		path,
	).Output()
	if err != nil {
		return time.Time{}, false
	}
	var result ffprobeResult
	if err := json.Unmarshal(out, &result); err != nil {
		return time.Time{}, false
	}
	ts := result.Format.Tags.CreationTime
	if ts == "" {
		return time.Time{}, false
	}
	// Handle trailing Z: replace with +00:00 for RFC3339 parsing
	ts = strings.Replace(ts, "Z", "+00:00", 1)
	t, err := time.Parse(time.RFC3339Nano, ts)
	if err != nil {
		// Try without sub-seconds
		t, err = time.Parse(time.RFC3339, ts)
	}
	if err != nil {
		return time.Time{}, false
	}
	return t.Local(), true
}

// probeDuration returns the video duration in seconds via ffprobe.
// Results are cached in the provided map (caller should pass a persistent map).
func probeDuration(path string, cache map[string]float64) (float64, bool) {
	if d, ok := cache[path]; ok {
		return d, true
	}
	out, err := exec.Command(
		"ffprobe", "-v", "quiet",
		"-print_format", "json",
		"-show_format",
		path,
	).Output()
	if err != nil {
		return 0, false
	}
	var result ffprobeResult
	if err := json.Unmarshal(out, &result); err != nil {
		return 0, false
	}
	d, err := strconv.ParseFloat(result.Format.Duration, 64)
	if err != nil || d <= 0 {
		return 0, false
	}
	cache[path] = d
	return d, true
}

func getTimestamp(path string) (time.Time, error) {
	// Strategy 1: Wyze path
	if t, ok := parseWyzePath(path); ok {
		return t, nil
	}
	// Strategy 2: filename
	base := filepath.Base(path)
	if t, ok := parseFilenameTimestamp(base); ok {
		return t, nil
	}
	// Strategy 3: full path string
	if t, ok := parseFilenameTimestamp(path); ok {
		return t, nil
	}
	// Strategy 4: ffprobe metadata
	if t, ok := probeCreationTime(path); ok {
		return t, nil
	}
	// Strategy 5: filesystem mtime
	info, err := os.Stat(path)
	if err != nil {
		return time.Time{}, fmt.Errorf("stat failed: %w", err)
	}
	log.Printf("DEBUG: using mtime fallback for %s", filepath.Base(path))
	return info.ModTime(), nil
}

func findVideoFiles(cfg *Config) ([]string, error) {
	var files []string
	err := filepath.WalkDir(cfg.InputDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			// Skip sub-directories if not recursive (but still visit root)
			if !cfg.Recursive && path != cfg.InputDir {
				return fs.SkipDir
			}
			return nil
		}
		ext := strings.ToLower(filepath.Ext(path))
		if videoExtensions[ext] {
			files = append(files, path)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	if len(files) == 0 {
		extra := ""
		if cfg.Recursive {
			extra = " (searched recursively)"
		}
		return nil, fmt.Errorf("no video files found in '%s'%s", cfg.InputDir, extra)
	}
	return files, nil
}

func discoverVideos(cfg *Config) ([]VideoFile, error) {
	paths, err := findVideoFiles(cfg)
	if err != nil {
		return nil, err
	}
	log.Printf("INFO: Found %d video files, resolving timestamps...", len(paths))

	workers := cfg.Workers
	if workers > len(paths) {
		workers = len(paths)
	}

	type result struct {
		vf  VideoFile
		err error
		idx int
	}

	jobs := make(chan int, len(paths))
	results := make(chan result, len(paths))

	var wg sync.WaitGroup
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for idx := range jobs {
				p := paths[idx]
				ts, err := getTimestamp(p)
				results <- result{vf: VideoFile{Path: p, Timestamp: ts}, err: err, idx: idx}
			}
		}()
	}

	for i := range paths {
		jobs <- i
	}
	close(jobs)

	go func() {
		wg.Wait()
		close(results)
	}()

	prog := newProgress("Scanning videos", len(paths))
	var videos []VideoFile
	for r := range results {
		prog.increment()
		if r.err != nil {
			log.Printf("WARN: Skipping %s: %v", filepath.Base(paths[r.idx]), r.err)
			continue
		}
		videos = append(videos, r.vf)
	}
	prog.done()

	sort.Slice(videos, func(i, j int) bool {
		return videos[i].Timestamp.Before(videos[j].Timestamp)
	})

	if len(videos) == 0 {
		return nil, fmt.Errorf("no video files could be timestamped")
	}

	tStart := videos[0].Timestamp
	tEnd := videos[len(videos)-1].Timestamp
	spanDays := tEnd.Sub(tStart).Hours() / 24
	log.Printf("INFO: Discovered %d videos spanning %s to %s (%.1f days)",
		len(videos),
		tStart.Format("2006-01-02"),
		tEnd.Format("2006-01-02"),
		spanDays,
	)

	return videos, nil
}
