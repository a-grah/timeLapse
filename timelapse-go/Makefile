VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
LDFLAGS := -ldflags "-X main.version=$(VERSION)"

# OpenCV via pkg-config (homebrew on macOS, system pkg-config on Linux)
PKG_CONFIG_PATH ?= /opt/homebrew/lib/pkgconfig
export PKG_CONFIG_PATH
export CGO_CPPFLAGS  := $(shell pkg-config --cflags opencv4 2>/dev/null)
export CGO_LDFLAGS   := $(shell pkg-config --libs opencv4 2>/dev/null)

.PHONY: build test clean

build:
	go build $(LDFLAGS) -o timelapse .

test:
	go test ./...

clean:
	rm -f timelapse
