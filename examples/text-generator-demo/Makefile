.PHONY: install run-multi run-crops run-single test clean help

# Default target
help:
	@echo "Text Generator Demo - Available targets:"
	@echo "  install     - Install the demo package"
	@echo "  test        - Run filter tests"
	@echo "  run-multi   - Run multi-text demo (main + crops)"
	@echo "  run-crops   - Run crops-only demo (no main frame)"
	@echo "  run-single  - Run single text demo (crop only)"
	@echo "  clean       - Clean build artifacts"
	@echo "  help        - Show this help message"

# Install the demo package
install:
	pip install -e .

# Run filter tests
test: install
	@echo "Running Text Generator Filter Tests..."
	python test_filter.py

# Run multi-text demo (main frame + individual crops)
run-multi: install
	@echo "Running Multi-Text Demo (Main + Crops)"
	python filter_text_generator_demo/main.py multi

# Run crops-only demo (no main frame)
run-crops: install
	@echo "Running Crops-Only Demo (No Main Frame)"
	python filter_text_generator_demo/main.py crops

# Run single text demo (crop only)
run-single: install
	@echo "Running Single Text Demo (Crop Only)"
	python filter_text_generator_demo/main.py single

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Create sample video if it doesn't exist
create-sample-video:
	@if [ ! -f example_video.mp4 ]; then \
		echo "Creating sample video..."; \
		python -c "import cv2; import numpy as np; \
		cap = cv2.VideoWriter('example_video.mp4', cv2.VideoWriter_fourcc(*'mp4v'), 1, (640, 480)); \
		for i in range(30): \
			frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8); \
			cap.write(frame); \
		cap.release(); \
		print('Sample video created: example_video.mp4')"; \
	else \
		echo "Sample video already exists: example_video.mp4"; \
	fi

# Setup everything
setup: create-sample-video install
	@echo "Setup complete! You can now run:"
	@echo "  make run-multi   # Multi-text demo"
	@echo "  make run-crops   # Crops-only demo"
	@echo "  make run-single  # Single text demo" 