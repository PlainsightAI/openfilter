# ImageIn Filter Demo Scenarios

This directory contains demonstration scripts for the ImageIn filter that showcase different real-world scenarios.

## Available Scripts

### 1. `scenario1_empty_start.py` - Empty Folder Start
**Simulates:** Pipeline starts with an empty folder and waits for images to appear.

**What it does:**
- Creates an empty `test_images/` directory
- Starts the pipeline with no images present
- Automatically adds images at 5, 15, 25, 35, and 45 seconds
- Demonstrates how the pipeline remains idle until images appear
- Shows automatic pickup of new images when they're added

**Usage:**
```bash
python scenario1_empty_start.py
```

**Expected behavior:**
1. Pipeline starts with empty folder
2. Webvis shows no images initially
3. Images appear automatically as they're added to the folder
4. Pipeline processes each new image as it appears

### 2. `scenario2_excluded_images.py` - Pattern Exclusion
**Simulates:** Pipeline starts with images in folder but they're excluded by pattern.

**What it does:**
- Creates `test_images/` with 3 excluded images (.bmp, .png, .tiff)
- Starts pipeline with pattern `*.jpg` only
- Pipeline remains idle (ignores excluded formats)
- Automatically adds matching .jpg images at 8, 18, 28, 38, and 48 seconds
- Demonstrates pattern-based filtering and automatic resume

**Usage:**
```bash
python scenario2_excluded_images.py
```

**Expected behavior:**
1. Pipeline starts with excluded images present
2. Webvis shows no images (pattern excludes them)
3. When .jpg images are added, pipeline automatically picks them up
4. Shows how pattern filtering works in real scenarios

## Key Features Demonstrated

### Polling Behavior
Both scripts use `poll_interval=1.0` to check for new images every second, demonstrating the real-time monitoring capability.

### Pattern Filtering
Scenario 2 demonstrates how `pattern=*.jpg` can exclude certain file types while monitoring for matching ones.

### FPS Control
Both scripts use `maxfps=0.5` (1 image every 2 seconds) to control display speed.

### Automatic Resume
Both scenarios show how the pipeline automatically resumes processing when new matching images appear.

## Pipeline Configuration

Both scripts use the same pipeline structure:
```
ImageIn -> Util -> Webvis
```

- **ImageIn**: Monitors folder for images with pattern filtering
- **Util**: Applies transformations (resize + colored box)
- **Webvis**: Displays results in web browser at http://localhost:8000

## Real-World Applications

### Scenario 1 Use Cases:
- **Security cameras**: Pipeline starts before cameras are active
- **Batch processing**: Waiting for new image batches to arrive
- **Monitoring systems**: Starting monitoring before data arrives

### Scenario 2 Use Cases:
- **File format filtering**: Only process specific image formats
- **Quality control**: Ignore temporary or low-quality images
- **Multi-format environments**: Handle mixed file types intelligently

## Running the Scripts

1. **Navigate to the directory:**
   ```bash
   cd examples/image_in
   ```

2. **Run either scenario:**
   ```bash
   python scenario1_empty_start.py
   # or
   python scenario2_excluded_images.py
   ```

3. **Open browser:**
   Navigate to http://localhost:8000 to see the results

4. **Stop the pipeline:**
   Press Ctrl+C to stop the pipeline

## Environment Variables

You can customize behavior with environment variables:
```bash
# Control polling frequency
export IMAGE_IN_POLL_INTERVAL=2.0

# Control FPS
export IMAGE_IN_MAXFPS=1.0

# Run with custom settings
python scenario1_empty_start.py
```

## Troubleshooting

- **No images appear**: Check that the `test_images/` directory is created
- **Webvis not loading**: Ensure port 8000 is available
- **Pipeline errors**: Check that all dependencies are installed
- **Permission issues**: Ensure write permissions for creating test directories 