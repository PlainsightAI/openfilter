"""Draw a filter's timing chain onto a frame, in the camera's own clock format.

A pipeline already records, per filter, when a frame entered and left it:
`Filter._inject_timings` appends `{filter_name, time_in, time_out, duration_ms}`
to `frame.data['meta']['filter_timings']` (`filter.py`), and video_in stamps
`frame.data['meta']['ts']` with the wall clock at read time. Summing those
durations answers "how long did the pipeline take", which is not the question
when a frame reaches a browser seconds late: the two segments nobody times are
camera -> video_in and webvis -> browser.

Rendering those same numbers *into the pixels*, in the `2026-09-22 15:22:53.123`
format an IP camera burns into its own image, makes the first segment readable
with no extra tooling: both clocks are then in one frame, side by side, and a
screenshot is the measurement.

The text is drawn with a dark outline under a light glyph so it stays legible
over any scene, the same trick the cameras use.
"""

import json
import logging
import time

__all__ = ['TIMESTAMP_FORMAT', 'CORNERS', 'JPEG_COMMENT_LIMIT', 'parse_color', 'format_epoch', 'timing_blocks',
           'corners_for', 'draw_lines', 'draw_blocks', 'timing_payload', 'insert_jpeg_comment',
           'read_jpeg_comment']

logger = logging.getLogger(__name__)

TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'

CORNERS = ('top-left', 'top-right', 'bottom-left', 'bottom-right')

# A COM segment carries a 2-byte big-endian length that counts itself, so the text cannot exceed
# 65535 - 2. A timing chain is a few hundred bytes; the cap is here so a pathological one is
# truncated rather than producing a segment whose length field lies about its own size.
JPEG_COMMENT_LIMIT = 65533


def parse_color(color: str | None) -> tuple[int, int, int]:
    """`#rgb` or `#rrggbb` -> an (r, g, b) tuple, the spelling `util.py` already accepts.

    Returns white for None or anything unparseable, because an overlay that is
    the wrong colour is still a usable measurement while a filter that refused
    to start over a typo in a debug option is not.
    """

    if not color:
        return (255, 255, 255)

    c = color.strip().lstrip('#')

    try:
        if len(c) == 3:
            return (int(c[0] * 2, 16), int(c[1] * 2, 16), int(c[2] * 2, 16))
        if len(c) == 6:
            return (int(c[:2], 16), int(c[2:4], 16), int(c[4:], 16))
    except ValueError:
        pass

    logger.warning('timing overlay: unparseable color %r, falling back to white', color)

    return (255, 255, 255)


def format_epoch(t: float | None, with_millis: bool = True) -> str:
    """Epoch seconds -> the camera's own format, in local time so the two clocks compare directly."""

    if t is None:
        return '-'

    out = time.strftime(TIMESTAMP_FORMAT, time.localtime(t))

    return f'{out}.{int((t % 1) * 1000):03d}' if with_millis else out


def timing_rows(data: dict | None) -> tuple[list[str], list[list[str]]]:
    """The chain as a header and one row per filter, the shape a log already reads in.

    Columns are `ID FILTER TIME IN TIME OUT TOTAL MS`, with the times as raw
    epoch seconds rather than a formatted clock: this is read next to a terminal
    printing the same numbers out of the subject data, and a reader should not
    have to convert between the two to line them up.

    TOTAL MS is the frame's total, first filter in to last filter out, repeated
    on every row. Per-filter durations are mostly the wait for the next frame,
    so a column of them answers a question nobody asked; the total is the one
    that moves when a pipeline gets slower.
    """

    meta = (data or {}).get('meta') or {}
    timings = meta.get('filter_timings') or []

    if not timings:
        return [], []

    frame_id = str(meta.get('id', '-'))
    total_ms = (timings[-1].get('time_out', 0) - timings[0].get('time_in', 0)) * 1000
    header = ['ID', 'FILTER', 'TIME IN', 'TIME OUT', 'TOTAL MS']
    rows = [
        [
            frame_id,
            str(entry.get('filter_name') or '?')[:20],
            f'{entry.get("time_in", 0):.6f}',
            f'{entry.get("time_out", 0):.6f}',
            f'{total_ms:.3f}',
        ]
        for entry in timings
    ]

    return header, rows


def timing_payload(data: dict | None, served: float | None = None) -> dict:
    """The timing chain as plain data, for travelling inside the JPEG itself.

    The browser gets the picture on one URL and the subject data on another, and
    nothing ties one to the other: a reading of "this frame took N seconds" is
    only as good as the assumption that the numbers belong to the frame on
    screen. Carried in the frame's own bytes, that assumption is gone.
    """

    meta = (data or {}).get('meta') or {}
    payload = {
        'id': meta.get('id'),
        'ts': meta.get('ts'),
        'filters': [
            {
                'name': entry.get('filter_name'),
                'in': entry.get('time_in'),
                'out': entry.get('time_out'),
                'duration_ms': entry.get('duration_ms'),
            }
            for entry in meta.get('filter_timings') or []
        ],
    }

    if served is not None:
        payload['served'] = served

    return payload


def insert_jpeg_comment(jpg: bytes, text: str) -> bytes:
    """Return `jpg` with `text` in a COM segment right after the SOI marker.

    COM (0xFFFE) is the JPEG spec's free-text segment: every decoder skips it, so
    the picture is byte-for-byte the same image to anything that does not look
    for it, and nothing is re-encoded here, only prepended.

    A payload that is not valid JPEG comes back untouched rather than raising,
    for the same reason the drawing path swallows its errors: this rides on the
    serving path, and instrumentation must not cost the stream.
    """

    data = bytes(jpg)

    if not data.startswith(b'\xff\xd8'):
        logger.warning('jpeg comment: not a JPEG (no SOI), leaving the frame untouched')
        return data

    payload = text.encode('utf8')[:JPEG_COMMENT_LIMIT]
    segment = b'\xff\xfe' + (len(payload) + 2).to_bytes(2, 'big') + payload

    return data[:2] + segment + data[2:]


def read_jpeg_comment(jpg: bytes) -> str | None:
    """The text of the first COM segment, or None. The reader half of `insert_jpeg_comment`."""

    data = bytes(jpg)
    i = 2

    while i + 4 <= len(data) and data[i] == 0xFF:
        marker = data[i + 1]

        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:  # standalone markers carry no length
            i += 2
            continue

        length = int.from_bytes(data[i + 2:i + 4], 'big')

        if marker == 0xFE:
            return data[i + 4:i + 2 + length].decode('utf8', 'replace')
        if marker == 0xDA:  # start of scan: entropy-coded data follows, stop looking
            return None

        i += 2 + length

    return None




def draw_table(image, header: list[str], rows: list[list[str]], corner: str = 'top-left',
               color=(0, 255, 0), scale: float | None = None, is_bgr: bool = True,
               is_gray: bool = False):
    """Draw the chain as an aligned table, in place, and return the image.

    Columns are laid out on measured widths rather than padded with spaces:
    OpenCV's Hershey fonts are proportional, so a space-padded row that lines up
    in a terminal comes out ragged on a frame.

    `scale` defaults to the frame's width, so the table stays the same physical
    size on a 720p preview and on a 4K source instead of turning into a smear on
    one of them.
    """

    import cv2

    if not rows:
        return image

    if corner not in CORNERS:
        logger.warning('timings: unknown corner %r, using top-left', corner)
        corner = 'top-left'

    if is_gray:
        color = round(sum(color) / 3)
    elif is_bgr:
        color = color[::-1]

    height, width = image.shape[:2]
    scale = scale if scale is not None else max(0.4, round(width / 1600, 2))
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = max(1, round(scale * 2))
    gap = round(18 * scale)
    margin = round(20 * scale)

    table = [header, *rows]
    widths = [
        max(cv2.getTextSize(row[col], font, scale, thickness)[0][0] for row in table)
        for col in range(len(header))
    ]
    line_h = cv2.getTextSize('0', font, scale, thickness)[0][1] + round(14 * scale)
    block_w = sum(widths) + gap * (len(widths) - 1)
    block_h = line_h * len(table)

    x0 = margin if corner.endswith('left') else max(margin, width - block_w - margin)
    y0 = margin + line_h if corner.startswith('top') else max(line_h, height - block_h - margin) + line_h

    for r, row in enumerate(table):
        x = x0
        for col, cell in enumerate(row):
            # Numbers right-aligned in their column, text left: the same reason a log does it,
            # digits that do not line up cannot be compared down the column.
            offset = widths[col] - cv2.getTextSize(cell, font, scale, thickness)[0][0] if col >= 2 else 0
            org = (x + offset, y0 + r * line_h)

            cv2.putText(image, cell, org, font, scale, (0, 0, 0) if not is_gray else 0,
                        thickness + 2, cv2.LINE_AA)
            cv2.putText(image, cell, org, font, scale, color, thickness, cv2.LINE_AA)

            x += widths[col] + gap

    return image
