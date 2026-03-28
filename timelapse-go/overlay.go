package main

import "time"

// burnTimestamp renders "YYYY-MM-DD HH:MM" in the bottom-left corner of a
// raw BGR24 frame. Uses a minimal 5x7 bitmap font for the 13-character set
// needed: digits 0-9, dash '-', colon ':', and space ' '.
func burnTimestamp(data []byte, width, height int, ts time.Time) []byte {
	out := make([]byte, len(data))
	copy(out, data)

	text := ts.Format("2006-01-02 15:04")

	// Scale font size relative to 1280px reference width
	scale := width / 1280
	if scale < 1 {
		scale = 1
	}

	charW := 5 * scale
	charH := 7 * scale
	padding := 10 * scale

	x0 := padding
	y0 := height - padding - charH

	// Draw shadow (black, offset 1px), then text (white)
	for _, offset := range []struct{ dx, dy int; r, g, b byte }{
		{1, 1, 0, 0, 0},
		{0, 0, 255, 255, 255},
	} {
		x := x0 + offset.dx
		y := y0 + offset.dy
		for _, ch := range text {
			bm := glyphFor(ch)
			drawGlyph(out, width, height, x, y, scale, bm, offset.r, offset.g, offset.b)
			x += charW + scale
		}
	}

	return out
}

func drawGlyph(data []byte, width, height, x0, y0, scale int, bm [7]uint8, r, g, b byte) {
	for row := 0; row < 7; row++ {
		for col := 0; col < 5; col++ {
			if bm[row]&(1<<uint(4-col)) == 0 {
				continue
			}
			// Draw scale×scale block
			for dy := 0; dy < scale; dy++ {
				for dx := 0; dx < scale; dx++ {
					px := x0 + col*scale + dx
					py := y0 + row*scale + dy
					if px < 0 || px >= width || py < 0 || py >= height {
						continue
					}
					i := (py*width + px) * 3
					data[i] = b
					data[i+1] = g
					data[i+2] = r
				}
			}
		}
	}
}

// glyphFor returns the 5×7 bitmap for a character.
// Each uint8 encodes one row; bit 4 (MSB of low 5) = leftmost pixel.
func glyphFor(ch rune) [7]uint8 {
	switch ch {
	case '0':
		return [7]uint8{0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E}
	case '1':
		return [7]uint8{0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E}
	case '2':
		return [7]uint8{0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F}
	case '3':
		return [7]uint8{0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E}
	case '4':
		return [7]uint8{0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02}
	case '5':
		return [7]uint8{0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E}
	case '6':
		return [7]uint8{0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E}
	case '7':
		return [7]uint8{0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08}
	case '8':
		return [7]uint8{0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E}
	case '9':
		return [7]uint8{0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C}
	case '-':
		return [7]uint8{0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00}
	case ':':
		return [7]uint8{0x00, 0x04, 0x00, 0x00, 0x00, 0x04, 0x00}
	default: // space or unknown
		return [7]uint8{}
	}
}
