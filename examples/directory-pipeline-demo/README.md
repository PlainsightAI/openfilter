# Directory Pipeline Demo

This example demonstrates how to use the directory traversal feature in `VideoIn` to process a directory of video files sequentially as if they were a single continuous stream.

## Features Illustrated
1. **Sequential Directory Traversal**: Reads all video files matching our video extension allowlist within a folder in alphabetical order.
2. **Metadata Tracking**: Displays real-time metadata reporting the active physical video file, the current frame index (re-indexed on new files), and video-time offsets (presentation timestamps).
3. **Pacing and MaxFPS**: Illustrates pacing frames across segment transitions without skipping or missing frames.
4. **Frame Saving**: Uses `ImageOut` to save frames to disk inside the `output/` folder.

## How to Run

Install dependencies and run the script:
```bash
python examples/directory-pipeline-demo/main.py
```

### Options
You can also supply your own directory of videos:
```bash
python examples/directory-pipeline-demo/main.py --directory /path/to/my/videos
```

For more options, run:
```bash
python examples/directory-pipeline-demo/main.py --help
```
