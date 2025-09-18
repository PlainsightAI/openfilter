.PHONY: install run clean help

# Default target
help:
	@echo "Video Pipeline Demo - Available targets:"
	@echo "  install  - Install dependencies"
	@echo "  run      - Run the video pipeline demo"
	@echo "  clean    - Clean output files"
	@echo "  help     - Show this help message"

# Install dependencies
install:
	pip install -e .

# Run the demo
run:
	python main.py

# Clean output files
clean:
	rm -rf output/deduped_frames/*
	rm -rf logs/*

# Run with custom videos
run-custom:
	@echo "Usage: make run-custom VIDEO1=path/to/video1.mp4 VIDEO2=path/to/video2.mp4"
	VIDEO1_PATH=$(VIDEO1) VIDEO2_PATH=$(VIDEO2) python main.py
