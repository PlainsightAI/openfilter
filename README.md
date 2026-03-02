# OpenFilter

[![PyPI version](https://img.shields.io/pypi/v/openfilter.svg?style=flat-square)](https://pypi.org/project/openfilter/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/PlainsightAI/openfilter/blob/main/LICENSE)
![Build Status](https://github.com/PlainsightAI/openfilter/actions/workflows/ci.yaml/badge.svg)


**OpenFilter** is an universal abstraction for building and running vision workloads in modular image/video processing pipelines. It simplifies communication between components (called filters) and supports synchronization, side-channel paths, metrics, and load balancing — all in pure Python.

Jump to:
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Examples](#examples)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- 🔁 Easily pluggable filter components
- 🧪 Develop and test filters locally with Python
- ⚡ High-throughput synchronized pipelines
- 📡 MQTT Bridge/REST Connect visualization and data publishing
- 🧵 Parallel processing via load-balanced filter branches
- 📊 Built-in telemetry and metrics streaming (coming soon)

---

## User Consent & Privacy

OpenFilter may collect usage metrics and telemetry data to help improve the project. We respect user privacy and provide multiple ways to manage consent:

**Opt out of tracking:**
- Set the `DO_NOT_TRACK` environment variable:
  ```bash
  export DO_NOT_TRACK=true
  ```
- Or use project-specific configuration options if available in your setup

Users can easily opt in or out through environment variables or configuration settings. Please refer to your project's specific configuration documentation for additional privacy options.

---

## Installation

Install OpenFilter with all utility filter dependencies:

```bash
pip install openfilter[all]
````

Install directly from GitHub:

```bash
pip install git+ssh://git@github.com/PlainsightAI/openfilter.git@main#egg=openfilter[all]
```

To install a specific version:

```bash
pip install git+ssh://git@github.com/PlainsightAI/openfilter.git@v1.3.17#egg=openfilter[all]
```

Editable install for development:

```bash
git clone git@github.com:PlainsightAI/openfilter.git
cd openfilter
make install
```

---

## Quick Start

Here’s a minimal example that plays a video and visualizes it in the browser:

```python
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.video_in import VideoIn
from openfilter.filter_runtime.filters.webvis import Webvis

if __name__ == '__main__':
    Filter.run_multi([
        (VideoIn, dict(sources='file://video.mp4', outputs='tcp://*')),
        (Webvis,  dict(sources='tcp://localhost')),
    ])
```

Run it with:

```bash
python script.py
```

Then open [http://localhost:8000](http://localhost:8000) to see your video stream.

---

Alternatively, simply use the CLI:

```
openfilter run - VideoIn --sources 'file://video.mp4!loop' - Webvis
```

Note: Ensure that a `video.mp4` file exists. A simple example is available at `examples/hello-world/video.mp4`.

## Examples

Explore real-world examples covering:

* Frame-by-frame video processing
* Writing frames to JPEG or output video
* Dual-video pipelines with multiple topics
* Load balancing using multiple filter processes
* Sending metrics to MQTT Bridge
* Ephemeral side-channel processing
* S3 integration for cloud video processing
* Fully declarative + class-based configuration

➡️ See [`docs/overview.md`](https://github.com/PlainsightAI/openfilter/blob/main/docs/overview.md) for all examples.

---

## Documentation

* 📘 [Overview](https://github.com/PlainsightAI/openfilter/blob/main/docs/overview.md)

---

## Releasing

OpenFilter publishes to **PyPI** (Python package) and **Docker Hub** (8 built-in filter images) via a single GitHub Actions workflow.

### How to release a new version

1. Update `VERSION` with the new version (e.g. `v0.1.22`)
2. Add a matching entry at the top of `RELEASE.md` with the same version and a changelog
3. Commit both changes and merge to `main`
4. Go to **GitHub Actions > "Create Release" > "Run workflow"** on the `main` branch

The workflow runs automatically from there:
- Runs unit tests across Python 3.10, 3.11, 3.12, 3.13
- Validates that `VERSION` matches `RELEASE.md`
- Creates a git tag and GitHub Release
- Builds and publishes the Python wheel to [PyPI](https://pypi.org/project/openfilter/)
- Builds and pushes 8 Docker images to [Docker Hub](https://hub.docker.com/u/plainsightai) (multi-arch: amd64 + arm64)

### Docker Hub images

Each built-in filter has a corresponding Docker image at `plainsightai/openfilter-<name>`:

| Image | Built-in filter | Extra |
|-------|----------------|-------|
| `plainsightai/openfilter-video-in` | VideoIn | `video_in` |
| `plainsightai/openfilter-video-out` | VideoOut | `video_out` |
| `plainsightai/openfilter-image-in` | ImageIn | `image_in` |
| `plainsightai/openfilter-image-out` | ImageOut | `image_out` |
| `plainsightai/openfilter-mqtt-out` | MQTTOut | `mqtt_out` |
| `plainsightai/openfilter-recorder` | Recorder | `recorder` |
| `plainsightai/openfilter-rest` | REST | `rest` |
| `plainsightai/openfilter-webvis` | Webvis | `webvis` |

Images are tagged with both the version (e.g. `0.1.20`) and `latest`. They install `openfilter[extra]=={version}` from PyPI, so the PyPI publish must succeed before Docker images are built.

### Using a published image

```bash
docker run -e FILTER_SOURCES="file:///video.mp4!loop" \
           -e FILTER_OUTPUTS="tcp://*:5550" \
           -v ./video.mp4:/video.mp4:ro \
           plainsightai/openfilter-video-in:latest
```

---

## Contributing

We welcome contributions of all kinds — new filters, bugfixes, or documentation improvements!

Please see the [contributing guide](https://github.com/PlainsightAI/openfilter/blob/main/CONTRIBUTING.md) for details on how to get started.

If you encounter issues, [open an issue](https://github.com/PlainsightAI/openfilter/issues/new/choose).

---

## License

Apache License 2.0. See [LICENSE](https://github.com/PlainsightAI/openfilter/blob/main/LICENSE) for full text.
