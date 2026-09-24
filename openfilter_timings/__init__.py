"""Latency instrumentation. Not part of the framework, which is why it sits outside it.

Every filter already records when a frame entered and left it. What was missing was a way to see
those numbers against the frame they belong to, and against a clock outside the pipeline.

Two halves, and they are not the same feature:

- The chain always travels inside the served JPEG, in its COM segment. A frame that carries its
  own timings cannot be paired with the wrong ones, which is what happens when the picture comes
  from one URL and the subject data from another.
- Drawing it on the picture is opt-in, through webvis's single `timings` option.

Everything lives in this folder, and the only trace elsewhere is in
`filter_runtime/filters/webvis.py`: a guarded import, one config option and the call that draws and
embeds while a frame is encoded for the wire. Delete this folder and `tests/test_timings.py` and
the feature is gone; webvis keeps working without them.

- `overlay.py`  the table on the picture and the JSON in the COM segment
- `page.py`     the browser page that reads it back and compares it with the local clock
- the compose/env/Makefile/README here run the probe end to end
"""

from openfilter_timings.overlay import (
    CORNERS, JPEG_COMMENT_LIMIT, TIMESTAMP_FORMAT, draw_table, format_epoch, insert_jpeg_comment,
    parse_color, read_jpeg_comment, timing_payload, timing_rows,
)
from openfilter_timings.page import TIMINGS_PAGE

__all__ = [
    'CORNERS', 'JPEG_COMMENT_LIMIT', 'TIMESTAMP_FORMAT', 'TIMINGS_PAGE', 'draw_table',
    'format_epoch', 'insert_jpeg_comment', 'parse_color', 'read_jpeg_comment', 'timing_payload',
    'timing_rows',
]
