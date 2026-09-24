"""Latency instrumentation. Not part of the framework, which is why it sits outside it.

This measures the two legs a pipeline cannot measure about itself: camera to
video_in, and webvis to browser. Everything it needs lives in this folder, and
the only trace of it elsewhere is in `filter_runtime/filters/webvis.py`: a
guarded import, four config options and the call that draws and embeds while a
frame is encoded for the wire.

To drop the whole thing: delete this folder and `tests/test_timings.py`. webvis
keeps working without them, since the import is guarded and the options then
warn and do nothing; reverting those edits too is tidier but not required.

- `overlay.py`  the chain as text on the picture and as JSON in the JPEG's COM segment
- `page.py`     the browser page that reads it back and compares it with the local clock
- the compose/env/Makefile/README here run the probe end to end
"""

from openfilter_timings.overlay import (
    CORNER_COLORS, CORNERS, JPEG_COMMENT_LIMIT, TIMESTAMP_FORMAT, corners_for, draw_blocks,
    draw_lines, format_epoch, insert_jpeg_comment, parse_color, parse_placement, placement_for,
    read_jpeg_comment, timing_blocks, timing_payload,
)
from openfilter_timings.page import TIMINGS_PAGE

__all__ = [
    'CORNER_COLORS', 'CORNERS', 'JPEG_COMMENT_LIMIT', 'TIMESTAMP_FORMAT', 'TIMINGS_PAGE',
    'corners_for', 'draw_blocks', 'draw_lines', 'format_epoch', 'insert_jpeg_comment',
    'parse_color', 'parse_placement', 'placement_for', 'read_jpeg_comment', 'timing_blocks',
    'timing_payload',
]
