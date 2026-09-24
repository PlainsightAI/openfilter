# Timing probe

Where does the delay come from when a frame reaches a browser late? Every filter
already records when a frame entered and left it, so the pipeline can account
for itself, but the two legs at the ends are outside all of it: camera to
video_in, and webvis to browser.

This stack makes both visible. `FILTER_TIMINGS` draws each filter's block into
the picture and carries the same numbers inside the JPEG, and `/timings` reads
them back in the browser and compares them with the machine's own clock.

## Run

```bash
make env                  # writes .env with this machine's timezone
make up                   # http://localhost:8000/timings
```

Point `SOURCE` at a camera to measure the first leg:

```bash
SOURCE='rtsp://user:pass@host:554/path!resize=1280x720!maxfps=10'
```

A camera that burns its own clock into the picture gives you that leg for free:
its timestamp and video_in's read stamp are then in the same frame. Use
`PLACEMENT` to keep the drawn blocks off it, for example
`video_in=bottom-left, webvis=bottom-right`.

## What you are looking at

The picture carries one block per filter, each in its own corner and colour. The
panel repeats those numbers, read out of the frame's own JPEG rather than from
another endpoint, and adds what only the browser knows: when the frame actually
arrived. `read -> on screen` is the number a customer would recognise, and the
clock at the top keeps running when frames stop, which is how a stalled stream
tells on itself.

## Removing it

This is not part of the framework, which is why it sits outside
`filter_runtime/`. Delete this folder and `tests/test_timings.py` and the
feature is gone: webvis's import of it is guarded, so it keeps working and the
`timings*` options warn once and do nothing. Reverting the webvis edits as well
is tidier but not required, and verified: with this folder moved away, the
webvis suite still passes and the filter still imports.

## Project Structure

```text
.
├── __init__.py
│   └── What this is, and how to remove it
├── overlay.py
│   └── The chain as text on the picture and as JSON in the JPEG's COM segment
├── page.py
│   └── The browser page that reads it back and compares with the local clock
├── docker-compose.yaml
│   └── video_in -> webvis, one exposed port
├── env.example
│   └── Copied by `make env`, which fills in this machine's timezone
├── Makefile
│   └── env / up / down
└── README.md
    └── This file
```
