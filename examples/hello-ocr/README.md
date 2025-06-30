# Hello World OCR Demo

## Table of Contents
- [Hello World OCR Demo](#hello-world-ocr-demo)
  - [Overview](#overview)
  - [Running the demo](#running-the-demo)
    - [Requirements](#requirements)
    - [Steps](#steps)

## Overview

This example demonstrates serveral filter types easily composed together to achieve a simple task: run OCR on a simple text video

```mermaid
flowchart LR
    A["[Utility]<br/>VideoIn"] --> B["[OTS Model]<br/>OCR"]
    B --> C["[Utility]<br/>Webviz"]
```

This example demonstrates 3 filters composed together to achieve our **hello world ocr demo** goal:

* **VideoIn**
  A **Utility** filter (does not run any models) which takes in an RTSP feed or a video file and pushes the frames forward through the pipeline.

* **OCR Filter**
  An **Off-the-Shelf (OTS) Model** filter that processes the frames passed to it by video in and applies optical character recognition (OCR) to extract the text.

* **Webviz Filter**
  A **Utility** filter which displays the frames passed to it on a live feed in the browser

## Running the demo

### Requirements

- [Python 3.11](https://www.python.org/downloads/release/python-3110/)
- Linux system

> Note: This project is designed with Linux support in mind. It should run on macOS, but your mileage may vary.

### Steps
1. [Optional] Create a virtual environemnt using a tool of your choosing (`venv` is used here)
```
python -m venv venv
source venv/bin/activate
```
2. run `make install`
3. run `make run`
4. visit `http://localhost:8000`

`make run` executes the filter pipeline via the openfilter CLI as follows:

```bash
openfilter run \
	- VideoIn \
		--sources 'file://hello.mov!loop' \
	- filter_optical_character_recognition.filter.FilterOpticalCharacterRecognition \
		--ocr_engine easyocr \
		--forward_ocr_texts true \
	- Webvis
```

#### Alternatively, you may use the `Filter.run_multi` utility as follows:
```bash
python filter_hello_ocr/main.py
```

We encourage the inspect the content of [filter_hello_ocr/main.py](filter_hello_ocr/main.py) for a code example!