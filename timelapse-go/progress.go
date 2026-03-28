package main

import (
	"fmt"
	"os"
	"sync/atomic"
)

// Progress is a simple stderr progress bar.
type Progress struct {
	label string
	total int
	count atomic.Int64
}

func newProgress(label string, total int) *Progress {
	return &Progress{label: label, total: total}
}

func (p *Progress) increment() {
	n := p.count.Add(1)
	p.render(int(n))
}

func (p *Progress) render(n int) {
	if p.total <= 0 {
		return
	}
	const width = 30
	frac := float64(n) / float64(p.total)
	filled := int(frac * width)
	if filled > width {
		filled = width
	}
	bar := ""
	for i := 0; i < width; i++ {
		if i < filled {
			bar += "="
		} else if i == filled {
			bar += ">"
		} else {
			bar += " "
		}
	}
	fmt.Fprintf(os.Stderr, "\r%s [%s] %d/%d (%.1f%%)",
		p.label, bar, n, p.total, frac*100)
}

func (p *Progress) done() {
	p.render(p.total)
	fmt.Fprintln(os.Stderr)
}
