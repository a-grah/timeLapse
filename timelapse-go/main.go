package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
)

// version is set at build time via:
//   go build -ldflags "-X main.version=$(git describe --tags --always --dirty)" .
// Falls back to "dev" when built without ldflags.
var version = "dev"

func main() {
	// --- Flag definitions ---
	output := flag.String("o", "timelapse.mp4", "Output video file path")
	duration := flag.String("d", "", "Output duration (e.g. 30s, 5m, 2m30s, 1h). Overrides -n")
	frames := flag.Int("n", 0, "Target frame count (default: 3600 = 2m at 30fps)")
	fps := flag.Int("fps", DefaultFPS, "Output frame rate")
	noRecursive := flag.Bool("no-recursive", false, "Do not search subfolders")
	resolution := flag.String("resolution", "1280x720", "Output resolution WxH")
	timestamp := flag.Bool("timestamp", false, "Burn timestamp overlay on frames")
	intro := flag.String("intro", "", "Linger on earliest footage (e.g. 15s, 1m)")
	outro := flag.String("outro", "", "Linger on latest footage (e.g. 15s, 1m)")
	oversample := flag.Float64("oversample", DefaultOversample, "Oversample factor for detection filtering")
	skipDetection := flag.Bool("skip-detection", false, "Include all sampled frames (no detector)")
	detector := flag.String("detector", "", "External detector command. Receives BGR24 frame on stdin + 'width height' args. Exit 0 = person found.")
	dryRun := flag.Bool("dry-run", false, "Show stats without processing")
	workers := flag.Int("workers", DefaultWorkers, "Parallel workers for timestamp resolution")
	verbose := flag.Bool("v", false, "Enable debug logging")
	showVersion := flag.Bool("version", false, "Print version and exit")

	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: timelapse [options] <input_dir>\n\n")
		fmt.Fprintf(os.Stderr, "Create a time-lapse video from a collection of video clips.\n\n")
		fmt.Fprintf(os.Stderr, "Options:\n")
		flag.PrintDefaults()
		fmt.Fprintf(os.Stderr, "\nExamples:\n")
		fmt.Fprintf(os.Stderr, "  timelapse /path/to/clips -o out.mp4\n")
		fmt.Fprintf(os.Stderr, "  timelapse -d 5m /path/to/clips\n")
		fmt.Fprintf(os.Stderr, "  timelapse -d 10m -intro 30s -outro 30s /path/to/clips\n")
		fmt.Fprintf(os.Stderr, "  timelapse --dry-run /path/to/clips\n")
		fmt.Fprintf(os.Stderr, "  timelapse --skip-detection /path/to/clips\n")
		fmt.Fprintf(os.Stderr, "\nExternal detector example:\n")
		fmt.Fprintf(os.Stderr, "  timelapse --detector 'python3 detect.py' /path/to/clips\n")
	}

	flag.Parse()

	if *showVersion {
		fmt.Printf("timelapse, version %s\n", version)
		os.Exit(0)
	}

	log.SetFlags(0)
	if !*verbose {
		log.SetOutput(&levelFilter{verbose: false})
	}

	args := flag.Args()
	if len(args) != 1 {
		flag.Usage()
		os.Exit(1)
	}
	inputDir := args[0]

	// Verify input directory exists
	if info, err := os.Stat(inputDir); err != nil || !info.IsDir() {
		fmt.Fprintf(os.Stderr, "Error: '%s' is not a directory\n", inputDir)
		os.Exit(1)
	}

	// Check ffmpeg/ffprobe availability
	checkFFmpeg()

	// Parse resolution
	width, height, err := parseResolution(*resolution)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	// Resolve target frames
	targetFrames := DefaultFrames
	if *duration != "" {
		secs, err := parseDuration(*duration)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: invalid -d value: %v\n", err)
			os.Exit(1)
		}
		targetFrames = secs * *fps
		log.Printf("INFO: Duration %s → %d frames at %dfps", *duration, targetFrames, *fps)
	} else if *frames != 0 {
		targetFrames = *frames
	}

	// Parse intro/outro
	introSecs := 0.0
	outroSecs := 0.0
	if *intro != "" {
		s, err := parseDuration(*intro)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: invalid -intro value: %v\n", err)
			os.Exit(1)
		}
		introSecs = float64(s)
	}
	if *outro != "" {
		s, err := parseDuration(*outro)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: invalid -outro value: %v\n", err)
			os.Exit(1)
		}
		outroSecs = float64(s)
	}

	lingerSecs := introSecs + outroSecs
	totalVideoSecs := float64(targetFrames) / float64(*fps)
	if lingerSecs >= totalVideoSecs {
		fmt.Fprintf(os.Stderr,
			"Error: -intro (%.0fs) + -outro (%.0fs) = %.0fs exceeds total video duration (%.0fs).\n"+
				"Use a longer -d or shorter intro/outro.\n",
			introSecs, outroSecs, lingerSecs, totalVideoSecs)
		os.Exit(1)
	}

	cfg := &Config{
		InputDir:         inputDir,
		Output:           *output,
		TargetFrames:     targetFrames,
		FPS:              *fps,
		Recursive:        !*noRecursive,
		Width:            width,
		Height:           height,
		TimestampOverlay: *timestamp,
		IntroSeconds:     introSecs,
		OutroSeconds:     outroSecs,
		Oversample:       *oversample,
		SkipDetection:    *skipDetection,
		DryRun:           *dryRun,
		Workers:          *workers,
		Verbose:          *verbose,
		Detector:         *detector,
	}

	// Stage 1: Discovery
	videos, err := discoverVideos(cfg)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	// Stage 2: Sampling
	plan := createSamplePlan(videos, cfg)

	if cfg.DryRun {
		secs := float64(cfg.TargetFrames) / float64(cfg.FPS)
		mins := int(secs) / 60
		s := int(secs) % 60
		var durStr string
		if mins > 0 {
			durStr = fmt.Sprintf("%dm%02ds", mins, s)
		} else {
			durStr = fmt.Sprintf("%ds", s)
		}
		fmt.Printf("\nDry run complete. Would process %d candidate frames.\n", len(plan))
		fmt.Printf("Target output: %d frames at %dfps = %s\n", cfg.TargetFrames, cfg.FPS, durStr)
		if cfg.IntroSeconds > 0 || cfg.OutroSeconds > 0 {
			midSecs := secs - cfg.IntroSeconds - cfg.OutroSeconds
			fmt.Printf("  Intro (linger): %.0fs | Middle: %.0fs | Outro (linger): %.0fs\n",
				cfg.IntroSeconds, midSecs, cfg.OutroSeconds)
		}
		return
	}

	// Stage 3: Extract
	prog := newProgress("Extracting frames", len(plan))
	rawFrames := make(chan ExtractedFrame, 4)
	go func() {
		defer close(rawFrames)
		for ef := range extractFrames(plan, cfg.Width, cfg.Height) {
			prog.increment()
			rawFrames <- ef
		}
		prog.done()
	}()

	// Stage 3b: Detect (optional)
	var filteredFrames <-chan ExtractedFrame
	if cfg.SkipDetection || cfg.Detector == "" {
		filteredFrames = rawFrames
	} else {
		filteredFrames = filterWithDetector(rawFrames, cfg.Detector, cfg.Width, cfg.Height, len(plan))
	}

	// Stage 4: Compose
	outPath, err := composeVideo(filteredFrames, cfg)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("\nTime-lapse saved to: %s\n", outPath)
}

// checkFFmpeg verifies ffmpeg and ffprobe are in PATH.
func checkFFmpeg() {
	for _, cmd := range []string{"ffmpeg", "ffprobe"} {
		if _, err := exec.LookPath(cmd); err != nil {
			fmt.Fprintf(os.Stderr,
				"Error: '%s' not found. Install ffmpeg: https://ffmpeg.org/download.html\n", cmd)
			os.Exit(1)
		}
	}
}

func parseResolution(s string) (int, int, error) {
	parts := strings.SplitN(strings.ToLower(s), "x", 2)
	if len(parts) != 2 {
		return 0, 0, fmt.Errorf("invalid resolution '%s'. Use WxH format, e.g. 1280x720", s)
	}
	w, err1 := strconv.Atoi(parts[0])
	h, err2 := strconv.Atoi(parts[1])
	if err1 != nil || err2 != nil || w <= 0 || h <= 0 {
		return 0, 0, fmt.Errorf("invalid resolution '%s'. Use WxH format, e.g. 1280x720", s)
	}
	return w, h, nil
}

var reDurUnit = regexp.MustCompile(`(\d+)\s*(h|m|s)`)

// parseDuration parses strings like "30s", "5m", "2m30s", "1h" into total seconds.
func parseDuration(s string) (int, error) {
	s = strings.TrimSpace(strings.ToLower(s))
	if n, err := strconv.Atoi(s); err == nil {
		return n, nil
	}
	matches := reDurUnit.FindAllStringSubmatch(s, -1)
	if len(matches) == 0 {
		return 0, fmt.Errorf("invalid duration '%s'. Use formats like: 30s, 5m, 2m30s, 1h", s)
	}
	total := 0
	for _, m := range matches {
		n, _ := strconv.Atoi(m[1])
		switch m[2] {
		case "h":
			total += n * 3600
		case "m":
			total += n * 60
		case "s":
			total += n
		}
	}
	return total, nil
}

// levelFilter filters log output: DEBUG lines only shown when verbose=true.
type levelFilter struct {
	verbose bool
}

func (f *levelFilter) Write(p []byte) (int, error) {
	s := string(p)
	if !f.verbose && strings.HasPrefix(s, "DEBUG:") {
		return len(p), nil
	}
	return os.Stderr.Write(p)
}
