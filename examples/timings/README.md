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

## Project Structure

```text
.
├── docker-compose.yaml
│   └── video_in -> webvis, one exposed port
├── env.example
│   └── Copy via `make env`, which fills in the timezone
├── Makefile
│   └── env / up / down
└── README.md
    └── This file
```
