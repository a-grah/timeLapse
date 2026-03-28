package main

import (
	"log"
	"math"
	"sort"
	"time"
)

func buildCompressedTimeline(
	segVideos []VideoFile,
	tStart, tEnd time.Time,
) (positions []float64, totalCompressed float64) {
	if len(segVideos) < 3 {
		// Too few videos — use real time
		for _, v := range segVideos {
			positions = append(positions, v.Timestamp.Sub(tStart).Seconds())
		}
		totalCompressed = tEnd.Sub(tStart).Seconds()
		return
	}

	// Compute inter-video gaps
	gaps := make([]float64, len(segVideos)-1)
	for i := 0; i < len(segVideos)-1; i++ {
		gaps[i] = segVideos[i+1].Timestamp.Sub(segVideos[i].Timestamp).Seconds()
	}

	// Median gap
	sorted := make([]float64, len(gaps))
	copy(sorted, gaps)
	sort.Float64s(sorted)
	medianGap := sorted[len(sorted)/2]
	gapCap := math.Max(medianGap*GapCapMultiplier, MinGapCapSeconds)

	log.Printf("DEBUG: Gap compression: median=%.0fs, cap=%.0fs (%.1f min)",
		medianGap, gapCap, gapCap/60)

	// Build compressed positions
	leadingGap := math.Max(segVideos[0].Timestamp.Sub(tStart).Seconds(), 0)
	positions = []float64{math.Min(leadingGap, gapCap)}

	for i := 1; i < len(segVideos); i++ {
		realGap := math.Max(segVideos[i].Timestamp.Sub(segVideos[i-1].Timestamp).Seconds(), 0)
		positions = append(positions, positions[len(positions)-1]+math.Min(realGap, gapCap))
	}

	trailingGap := math.Max(tEnd.Sub(segVideos[len(segVideos)-1].Timestamp).Seconds(), 0)
	totalCompressed = positions[len(positions)-1] + math.Min(trailingGap, gapCap)
	return
}

func sampleSegment(
	videos []VideoFile,
	timestamps []time.Time,
	tStart, tEnd time.Time,
	nCandidates int,
) []SamplePlan {
	if tEnd.Sub(tStart).Seconds() <= 0 || nCandidates <= 0 {
		return nil
	}

	// Binary search for segment bounds
	segStartIdx := sort.Search(len(timestamps), func(i int) bool {
		return !timestamps[i].Before(tStart)
	})
	segEndIdx := sort.Search(len(timestamps), func(i int) bool {
		return timestamps[i].After(tEnd)
	})

	if segStartIdx >= segEndIdx {
		nearest := segStartIdx
		if nearest >= len(videos) {
			nearest = len(videos) - 1
		}
		segStartIdx = nearest
		segEndIdx = nearest + 1
	}

	segVideos := videos[segStartIdx:segEndIdx]
	if len(segVideos) == 0 {
		return nil
	}

	compressedPos, totalCompressed := buildCompressedTimeline(segVideos, tStart, tEnd)
	if totalCompressed <= 0 {
		return nil
	}

	slotDuration := totalCompressed / float64(nCandidates)
	hitCount := make(map[string]int) // video path → number of picks

	var plan []SamplePlan
	for i := 0; i < nCandidates; i++ {
		slotCenter := slotDuration * (float64(i) + 0.5)

		// Find nearest video in compressed space
		idx := sort.SearchFloat64s(compressedPos, slotCenter)

		bestVideo := -1
		bestDelta := math.Inf(1)
		for _, ci := range []int{idx - 1, idx} {
			if ci >= 0 && ci < len(segVideos) {
				delta := math.Abs(compressedPos[ci] - slotCenter)
				if delta < bestDelta {
					bestDelta = delta
					bestVideo = ci
				}
			}
		}
		if bestVideo < 0 {
			continue
		}

		v := segVideos[bestVideo]
		hits := hitCount[v.Path]
		if hits >= MaxPicksPerVideo {
			continue
		}
		hitCount[v.Path] = hits + 1

		var frameFraction float64
		if hits == 0 {
			frameFraction = 0.5
		} else {
			totalHits := hits + 1
			frameFraction = 0.1 + (0.8 * float64(hits) / float64(totalHits))
		}

		plan = append(plan, SamplePlan{
			VideoPath:         v.Path,
			FrameFraction:     frameFraction,
			ExpectedTimestamp: v.Timestamp,
		})
	}

	return plan
}

func createSamplePlan(videos []VideoFile, cfg *Config) []SamplePlan {
	oversample := cfg.Oversample
	if cfg.SkipDetection {
		oversample = 1.0
	}

	tStart := videos[0].Timestamp
	tEnd := videos[len(videos)-1].Timestamp
	totalSeconds := tEnd.Sub(tStart).Seconds()

	timestamps := make([]time.Time, len(videos))
	for i, v := range videos {
		timestamps[i] = v.Timestamp
	}

	if totalSeconds <= 0 {
		log.Printf("WARN: All videos have the same timestamp")
		nCandidates := int(float64(cfg.TargetFrames) * oversample)
		step := len(videos) / nCandidates
		if step < 1 {
			step = 1
		}
		var plan []SamplePlan
		for i := 0; i < len(videos); i += step {
			plan = append(plan, SamplePlan{
				VideoPath:         videos[i].Path,
				FrameFraction:     0.5,
				ExpectedTimestamp: videos[i].Timestamp,
			})
			if len(plan) >= nCandidates {
				break
			}
		}
		return plan
	}

	introSecs := cfg.IntroSeconds
	outroSecs := cfg.OutroSeconds
	totalVideoSecs := float64(cfg.TargetFrames) / float64(cfg.FPS)

	var tIntroEnd, tOutroStart time.Time

	if introSecs > 0 || outroSecs > 0 {
		midVideoSecs := totalVideoSecs - introSecs - outroSecs
		weightedTotal := introSecs/LingerFactor + midVideoSecs + outroSecs/LingerFactor
		sourcePerWeightedSec := totalSeconds / weightedTotal

		introSourceSecs := (introSecs / LingerFactor) * sourcePerWeightedSec
		outroSourceSecs := (outroSecs / LingerFactor) * sourcePerWeightedSec

		tIntroEnd = tStart.Add(time.Duration(introSourceSecs * float64(time.Second)))
		tOutroStart = tEnd.Add(-time.Duration(outroSourceSecs * float64(time.Second)))

		if !tIntroEnd.Before(tOutroStart) {
			log.Printf("WARN: Intro/outro source spans overlap; falling back to uniform sampling")
			introSecs = 0
			outroSecs = 0
		} else {
			log.Printf("INFO: Linger sampling: intro %.0fs source → %.0fs video | middle → %.0fs video | outro %.0fs source → %.0fs video",
				introSourceSecs, introSecs,
				midVideoSecs,
				outroSourceSecs, outroSecs,
			)
		}
	}

	var plan []SamplePlan

	if introSecs == 0 && outroSecs == 0 {
		nCandidates := int(float64(cfg.TargetFrames) * oversample)
		plan = sampleSegment(videos, timestamps, tStart, tEnd, nCandidates)
	} else {
		midVideoSecs := totalVideoSecs - introSecs - outroSecs
		introFrames := int(introSecs * float64(cfg.FPS) * oversample)
		outroFrames := int(outroSecs * float64(cfg.FPS) * oversample)
		midFrames := int(midVideoSecs * float64(cfg.FPS) * oversample)

		planIntro := sampleSegment(videos, timestamps, tStart, tIntroEnd, introFrames)
		planMid := sampleSegment(videos, timestamps, tIntroEnd, tOutroStart, midFrames)
		planOutro := sampleSegment(videos, timestamps, tOutroStart, tEnd, outroFrames)
		plan = append(planIntro, planMid...)
		plan = append(plan, planOutro...)
	}

	uniqueVideos := make(map[string]bool)
	for _, s := range plan {
		uniqueVideos[s.VideoPath] = true
	}
	slotsPerDay := float64(len(plan)) / math.Max(1, totalSeconds/86400)
	log.Printf("INFO: Sampling plan: %d candidate frames from %d videos (%.1f slots/day, target=%d final frames)",
		len(plan), len(uniqueVideos), slotsPerDay, cfg.TargetFrames)

	return plan
}
