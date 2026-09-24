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

__all__ = ['TIMESTAMP_FORMAT', 'CORNERS', 'parse_color', 'format_epoch', 'timing_blocks', 'corners_for',
           'draw_lines', 'draw_blocks']

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


def timing_blocks(data: dict | None, served: float | None = None) -> list[tuple[str, list[str]]]:
    """One block per filter, in pipeline order, every block the same three lines.

    Kept as separate blocks rather than one list of lines so each filter can be
    drawn in its own corner: reading a delay means comparing two numbers that are
    far apart in the picture, and a single stacked block puts them one line
    apart, where a 2-second gap looks the same as a 20-millisecond one.

    Read the blocks at serve time, not inside `process()`: a filter's own entry
    is appended to `filter_timings` only after its `process()` returns
    (`filter.py`), so webvis's own in/out exist by the time a frame is encoded
    for the wire but not while it is being handled. `served`, the instant the
    JPEG goes out, is the one value no filter records, and it closes the chain.
    """

    meta = (data or {}).get('meta') or {}
    ts = meta.get('ts')
    blocks = []

    for i, entry in enumerate(meta.get('filter_timings') or []):
        lines = [
            f'in  {format_epoch(entry.get("time_in"))}',
            f'out {format_epoch(entry.get("time_out"))}  {entry.get("duration_ms", 0):.1f}ms',
        ]

        if i == 0 and ts is not None:  # the source's read stamp belongs with the source
            lines.insert(0, f'ts  {format_epoch(ts)}')

        blocks.append((str(entry.get('filter_name') or '?')[:24], lines))

    # The serve stamp joins the last filter's block rather than forming its own: it happens in
    # that filter, and a separate block would push the last filter out of the corner opposite the
    # source, which is where a reader looks for the other end of the chain.
    if served is not None:
        lines = [f'served {format_epoch(served)}']

        if ts is not None:
            lines.append(f'ts -> served  {(served - ts) * 1000:.0f}ms')

        if blocks:
            blocks[-1][1].extend(lines)
        else:
            blocks.append(('served', lines))

    return blocks


def corners_for(count: int, first: str = 'top-left') -> list[str]:
    """Place `count` blocks: the source at `first`, webvis opposite it on the same edge.

    The two ends are what a reader compares, so they keep the same two corners
    however many filters sit between them; anything in between fills the other
    edge. With more blocks than corners the extras wrap, which is ugly but still
    readable, and beats dropping a filter's numbers silently.
    """

    if first not in CORNERS:
        logger.warning('timing overlay: unknown corner %r, using top-left', first)
        first = 'top-left'

    edge, side = first.split('-')
    opposite = f'{edge}-{"right" if side == "left" else "left"}'
    other_edge = 'bottom' if edge == 'top' else 'top'
    middles = [f'{other_edge}-{side}', f'{other_edge}-{"right" if side == "left" else "left"}']

    if count <= 1:
        return [first]

    return [first] + [middles[i % 2] for i in range(count - 2)] + [opposite]


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


def draw_blocks(image, blocks: list[tuple[str, list[str]]], first_corner: str = 'top-left',
                color=(255, 255, 255), scale: float = 0.5, is_bgr: bool = True, is_gray: bool = False):
    """Draw each block in its own corner, in place, and return the image."""

    corners = corners_for(len(blocks), first_corner)

    for corner, (label, lines) in zip(corners, blocks):
        draw_lines(image, [label, *lines], corner=corner, color=color, scale=scale,
                   is_bgr=is_bgr, is_gray=is_gray)

    return image
