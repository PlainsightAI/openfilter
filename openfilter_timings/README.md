# Timing probe

Where does the delay come from when a frame reaches a browser late? Every filter
already records when a frame entered and left it, so the pipeline can account
for itself, but the two legs at the ends are outside all of it: camera to
video_in, and webvis to browser.

The chain always travels inside the served JPEG, so a frame carries its own
numbers and cannot be paired with another frame's. `FILTER_TIMINGS` additionally
draws them on the picture, and `/timings` reads them back in the browser and
compares them with the machine's own clock.

```
ID    FILTER    TIME IN            TIME OUT           TOTAL MS
3247  VideoIn   1790273007.697044  1790273007.714762    43.013
3247  Webvis    1790273007.740037  1790273007.740057    43.013
```

One row per filter, for the frame on screen. Times are raw epoch seconds, the
same numbers a script reading the subject data prints, so the two line up
without converting anything. TOTAL MS is the frame's own, first filter in to
last filter out.

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
its timestamp and video_in's read stamp are then in the same frame. Set `TIMINGS` to a corner to keep the
table off it, for example `TIMINGS=bottom-left`.

## What you are looking at

The panel repeats the table, read out of the frame's own JPEG rather than from
another endpoint, and adds two rows no filter can record: when this browser
received the frame, and how far that is from the read. The clock at the top
keeps running when frames stop, which is how a stalled stream tells on itself.

## Removing it

This is not part of the framework, which is why it sits outside
`filter_runtime/`. Delete this folder and `tests/test_timings.py` and the
feature is gone: webvis's import of it is guarded, so it keeps working and the
`timings*` options warn once and do nothing. Reverting the webvis edits as well
is tidier but not required, and verified: with this folder moved away, the
webvis suite still passes and the filter still imports.

## Both ends need the same clock

The last leg compares a stamp taken in the pipeline against one taken in the
browser, so it is only as good as the agreement between those two clocks. A
container does not inherit the host's clock discipline, and on this setup the
two differed by tens of milliseconds, which is the same size as the thing being
measured.

The page says so rather than letting you read the offset as latency: a negative
`served -> browser` is impossible, so when it sees one it reports how far apart
the clocks are instead. Put both ends on NTP before trusting that row.

Everything else on the page is immune, because it compares stamps taken on one
machine.

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
