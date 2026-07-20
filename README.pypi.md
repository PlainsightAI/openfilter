<!-- Generated from README.md by scripts/make_pypi_readme.py. Do not edit directly. -->

# <img src="https://raw.githubusercontent.com/PlainsightAI/openfilter/main/docs/openfilterlogo.png" width="38" align="center" alt="OpenFilter Logo" /> OpenFilter

[![PyPI version](https://img.shields.io/pypi/v/openfilter.svg?style=flat-square)](https://pypi.org/project/openfilter/)
[![Python versions](https://img.shields.io/pypi/pyversions/openfilter.svg?style=flat-square)](https://pypi.org/project/openfilter/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square)](https://github.com/PlainsightAI/openfilter/blob/main/LICENSE)
[![Build Status](https://github.com/PlainsightAI/openfilter/actions/workflows/ci.yaml/badge.svg)](https://github.com/PlainsightAI/openfilter/actions/workflows/ci.yaml)

**OpenFilter** is an open-source runtime and framework for building image and video processing pipelines out of small, composable
components called **filters**. It handles the setup, serialization, and communication between filters — including frame
synchronization, side-channel paths, load balancing, and telemetry — so you can focus on the processing itself, in plain Python.

A filter is a component that originates, processes, or exports a stream of frames and/or data. You chain filters into a pipeline
(with many-to-many topologies), and the runtime keeps frames that enter together synchronized through to the output. Develop and test
filters locally as ordinary Python processes, then ship each one as a Docker image.

> **Pipeline diagram:** rendered on the [GitHub README](https://github.com/PlainsightAI/openfilter#readme).

Homepage: [openfilter.io](https://openfilter.io) · Package: [PyPI](https://pypi.org/project/openfilter/) · Images: [Docker Hub](https://hub.docker.com/u/plainsightai)

Jump to:

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Built-in filters](#built-in-filters)
- [Examples](#examples)
- [Documentation](#documentation)
- [Telemetry & privacy](#telemetry--privacy)
- [Ecosystem](#ecosystem)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- Pluggable, reusable filters that you compose into pipelines
- Develop and test filters locally, in pure Python
- Automatic frame synchronization across many-to-many pipeline topologies
- Built-in I/O and visualization filters (VideoIn/VideoOut, ImageIn/ImageOut, Webvis, REST, MQTTOut, Recorder)
- Parallel processing via load-balanced filter branches and unsynchronized side-channel paths
- Built-in observability: OpenTelemetry tracing, OpenLineage lineage events, and per-frame metrics

---

## Requirements

- Python 3.10 or newer (tested on 3.10, 3.11, 3.12, and 3.13)

---

## Installation

Install OpenFilter with all built-in utility-filter dependencies:

```bash
pip install openfilter[all]
```

Install directly from GitHub:

```bash
pip install "openfilter[all] @ git+https://github.com/PlainsightAI/openfilter.git@main"
```

Install a specific version:

```bash
pip install "openfilter[all] @ git+https://github.com/PlainsightAI/openfilter.git@v1.1.2"
```

Editable install for development:

```bash
git clone https://github.com/PlainsightAI/openfilter.git
cd openfilter
make install
```

### Run a published Docker image

Each built-in filter is also published as a Docker image (see [Built-in filters](#built-in-filters)):

```bash
docker run -e FILTER_SOURCES="file:///video.mp4!loop" \
           -e FILTER_OUTPUTS="tcp://*:5550" \
           -v ./video.mp4:/video.mp4:ro \
           plainsightai/openfilter-video-in:latest
```

---

## Quick Start

Here is a minimal example that plays a video and visualizes it in the browser:

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

Alternatively, use the CLI:

```bash
openfilter run - VideoIn --sources 'file://video.mp4!loop' - Webvis
```

These examples expect a `video.mp4` in the current directory. A sample video ships with the repository at
`examples/hello-world/example_video.mp4` — copy it to `video.mp4`, or point `--sources` at that path.

---

## Built-in filters

OpenFilter ships a set of ready-to-use filters. Run `openfilter info <Filter>` for a filter's configuration options.

| Filter | Purpose | Reference |
| --- | --- | --- |
| `VideoIn` | Read video from files, URLs, or streams | [docs](https://github.com/PlainsightAI/openfilter/blob/main/docs/video-in-filter.md) |
| `VideoOut` | Write frames to a video file | [docs](https://github.com/PlainsightAI/openfilter/blob/main/docs/video-out-filter.md) |
| `ImageIn` | Read images from local paths, S3, or GCS | [docs](https://github.com/PlainsightAI/openfilter/blob/main/docs/image-in-filter.md) |
| `ImageOut` | Write frames as image files | [docs](https://github.com/PlainsightAI/openfilter/blob/main/docs/image-out-filter.md) |
| `Webvis` | View a pipeline live in the browser | [docs](https://github.com/PlainsightAI/openfilter/blob/main/docs/webvis-filter.md) |
| `REST` | Expose pipeline data over an HTTP endpoint | [docs](https://github.com/PlainsightAI/openfilter/blob/main/docs/rest-filter.md) |
| `MQTTOut` | Publish frames and data to an MQTT broker | [docs](https://github.com/PlainsightAI/openfilter/blob/main/docs/mqtt-out-filter.md) |
| `Recorder` | Record pipeline frame data to disk (JSON/CSV) | [docs](https://github.com/PlainsightAI/openfilter/blob/main/docs/recorder-filter.md) |
| `Util` | Diagnostic and utility helpers | [docs](https://github.com/PlainsightAI/openfilter/blob/main/docs/util-filter.md) |

Each I/O filter is also published as a Docker image at `plainsightai/openfilter-<name>` (multi-arch `amd64` + `arm64`), tagged with
both the version (for example `1.1.2`) and `latest`. Each installs `openfilter[extra]=={version}` from PyPI:

| Image | Filter | Extra |
| --- | --- | --- |
| `plainsightai/openfilter-video-in` | VideoIn | `video_in` |
| `plainsightai/openfilter-video-out` | VideoOut | `video_out` |
| `plainsightai/openfilter-image-in` | ImageIn | `image_in` |
| `plainsightai/openfilter-image-out` | ImageOut | `image_out` |
| `plainsightai/openfilter-mqtt-out` | MQTTOut | `mqtt_out` |
| `plainsightai/openfilter-recorder` | Recorder | `recorder` |
| `plainsightai/openfilter-rest` | REST | `rest` |
| `plainsightai/openfilter-webvis` | Webvis | `webvis` |

---

## Examples

Explore real-world examples covering:

- Frame-by-frame video processing
- Writing frames to JPEG or output video
- Dual-video pipelines with multiple topics
- Load balancing using multiple filter processes
- Publishing data over MQTT
- Ephemeral side-channel processing
- S3 integration for cloud video processing
- Fully declarative and class-based configuration

Runnable demos live in the [`examples/`](https://github.com/PlainsightAI/openfilter/tree/main/examples) directory, and every topic
above is walked through in the [Overview](https://github.com/PlainsightAI/openfilter/blob/main/docs/overview.md).

---

## Documentation

- [Overview](https://github.com/PlainsightAI/openfilter/blob/main/docs/overview.md) — concepts, pipeline topologies, and a tour of the examples
- [Your First Filter](https://github.com/PlainsightAI/openfilter/blob/main/docs/your-first-filter.md) — build your own filter
- [Declarative configuration](https://github.com/PlainsightAI/openfilter/blob/main/docs/declarative-config.md) — configure pipelines declaratively
- [Monitoring](https://github.com/PlainsightAI/openfilter/blob/main/docs/monitoring.md) and [metrics architecture](https://github.com/PlainsightAI/openfilter/blob/main/docs/metrics-architecture.md) — telemetry and observability
- [Migration guide](https://github.com/PlainsightAI/openfilter/blob/main/docs/migration-guide.md) — upgrading between versions
- Built-in filter references: [VideoIn](https://github.com/PlainsightAI/openfilter/blob/main/docs/video-in-filter.md) · [VideoOut](https://github.com/PlainsightAI/openfilter/blob/main/docs/video-out-filter.md) ·
  [ImageIn](https://github.com/PlainsightAI/openfilter/blob/main/docs/image-in-filter.md) · [ImageOut](https://github.com/PlainsightAI/openfilter/blob/main/docs/image-out-filter.md) · [Webvis](https://github.com/PlainsightAI/openfilter/blob/main/docs/webvis-filter.md) ·
  [REST](https://github.com/PlainsightAI/openfilter/blob/main/docs/rest-filter.md) · [MQTTOut](https://github.com/PlainsightAI/openfilter/blob/main/docs/mqtt-out-filter.md) · [Recorder](https://github.com/PlainsightAI/openfilter/blob/main/docs/recorder-filter.md) ·
  [Util](https://github.com/PlainsightAI/openfilter/blob/main/docs/util-filter.md)
- [Contributing guide](https://github.com/PlainsightAI/openfilter/blob/main/CONTRIBUTING.md) — development setup, conventions, DCO sign-off, and the release process

---

## Telemetry & privacy

When a filter starts, OpenFilter emits a single anonymous usage-analytics event — the filter's class name — via
[Scarf](https://scarf.sh), which helps the maintainers understand adoption. Beyond that class name, OpenFilter sends no frame data,
pipeline configuration, or personal information. Opt out at any time by setting an environment variable:

```bash
export DO_NOT_TRACK=true
```

---

## Ecosystem

OpenFilter is the open-source runtime and filter framework, released under Apache 2.0. Related projects:

- [openfilter-pipelines-controller](https://github.com/PlainsightAI/openfilter-pipelines-controller) — a Kubernetes operator for
  running filter pipelines.
- Additional open-source filters and tools are published across the
  [PlainsightAI organization](https://github.com/orgs/PlainsightAI/repositories?q=filter-).

Plainsight ([plainsight.ai](https://plainsight.ai)) offers a commercial managed platform built on OpenFilter for teams that want
hosted deployment and support.

---

## Contributing

We welcome contributions of all kinds — new filters, bug fixes, or documentation improvements.

See the [contributing guide](https://github.com/PlainsightAI/openfilter/blob/main/CONTRIBUTING.md) for development setup, coding conventions, DCO sign-off, and the release process. If you
run into a problem, [open an issue](https://github.com/PlainsightAI/openfilter/issues/new/choose).

---

## License

Apache License 2.0. See [LICENSE](https://github.com/PlainsightAI/openfilter/blob/main/LICENSE) for the full text.
