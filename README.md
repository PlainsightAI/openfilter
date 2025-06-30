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
- 📡 MQTT/REST visualization and data publishing
- 🧵 Parallel processing via load-balanced filter branches
- 📊 Built-in telemetry and metrics streaming (coming soon)

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
* Sending metrics to MQTT
* Ephemeral side-channel processing
* S3 integration for cloud video processing
* Fully declarative + class-based configuration

➡️ See [`docs/overview.md`](https://github.com/PlainsightAI/openfilter/blob/main/docs/overview.md) for all examples.

---

## Documentation

* 📘 [Overview](https://github.com/PlainsightAI/openfilter/blob/main/docs/overview.md)

---

## Contributing

We welcome contributions of all kinds — new filters, bugfixes, or documentation improvements!

Please see the [contributing guide](https://github.com/PlainsightAI/openfilter/blob/main/CONTRIBUTING.md) for details on how to get started.

If you encounter issues, [open an issue](https://github.com/PlainsightAI/openfilter/issues/new/choose).

---

## License

Apache License 2.0. See [LICENSE](https://github.com/PlainsightAI/openfilter/blob/main/LICENSE) for full text.
