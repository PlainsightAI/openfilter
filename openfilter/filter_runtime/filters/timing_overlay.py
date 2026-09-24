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

import logging
import time

__all__ = ['TIMESTAMP_FORMAT', 'CORNERS', 'parse_color', 'format_epoch', 'timing_lines', 'draw_lines']

logger = logging.getLogger(__name__)

TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'

CORNERS = ('top-left', 'top-right', 'bottom-left', 'bottom-right')


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


def timing_lines(data: dict | None) -> list[str]:
    """The lines to draw for one frame: the read timestamp, then one line per filter.

    `now` is last on purpose: it is the only value that is not carried by the
    frame, so the gap between it and the line above is what this whole overlay
    exists to show.
    """

    meta = (data or {}).get('meta') or {}
    now = time.time()
    lines = []

    if (ts := meta.get('ts')) is not None:
        lines.append(f'video_in ts   {format_epoch(ts)}')

    for entry in meta.get('filter_timings') or []:
        name = entry.get('filter_name') or '?'
        lines.append(
            f'{name[:18]:<18} in {format_epoch(entry.get("time_in"))}'
            f'  out {format_epoch(entry.get("time_out"))}'
            f'  {entry.get("duration_ms", 0):.1f}ms'
        )

    lines.append(f'webvis now    {format_epoch(now)}')

    if (ts := meta.get('ts')) is not None:
        lines.append(f'ts -> now     {(now - ts) * 1000:.0f}ms')

    return lines


def draw_lines(image, lines: list[str], corner: str = 'top-left', color=(255, 255, 255),
               scale: float = 0.5, is_bgr: bool = True, is_gray: bool = False):
    """Draw `lines` in one corner of `image`, in place, and return it.

    `image` must already be writable (`frame.rw.image`); this does not copy.
    """

    import cv2

    if not lines:
        return image

    if is_gray:
        color = round(sum(color) / 3)
    elif is_bgr:
        color = color[::-1]

    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = max(1, round(scale * 2))
    height, width = image.shape[:2]
    margin = 10

    sizes = [cv2.getTextSize(line, font, scale, thickness)[0] for line in lines]
    line_h = max(h for _, h in sizes) + 8
    block_h = line_h * len(lines)
    block_w = max(w for w, _ in sizes)

    if corner not in CORNERS:
        logger.warning('timing overlay: unknown corner %r, using top-left', corner)
        corner = 'top-left'

    x = margin if corner.endswith('left') else max(margin, width - block_w - margin)
    y = margin + line_h if corner.startswith('top') else max(line_h, height - block_h - margin) + line_h

    for i, line in enumerate(lines):
        org = (x, y + i * line_h)
        # Dark outline first, light glyph over it: the same legibility trick the
        # cameras use for their own burned-in clock, so the overlay survives a
        # white box or a bright floor without a background rectangle hiding the
        # scene behind it.
        cv2.putText(image, line, org, font, scale, (0, 0, 0) if not is_gray else 0, thickness + 2, cv2.LINE_AA)
        cv2.putText(image, line, org, font, scale, color, thickness, cv2.LINE_AA)

    return image
