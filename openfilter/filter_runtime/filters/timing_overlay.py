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

# One colour per corner, so two blocks are told apart by where they are AND by how they look. Green
# and cyan for the two ends of the chain, which are the pair a reader compares; amber and magenta
# for whatever sits between them.
CORNER_COLORS = {
    'top-left':     (0, 255, 0),
    'top-right':    (0, 255, 255),
    'bottom-left':  (255, 191, 0),
    'bottom-right': (255, 0, 255),
}

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


def draw_blocks(image, blocks: list[tuple[str, list[str]]], spec: dict[str, list[str]] | None = None,
                scale: float = 0.5, is_bgr: bool = True, is_gray: bool = False):
    """Draw each block in its own corner and colour, in place, and return the image."""

    spec = spec or {}
    corners = corners_for(len(blocks))

    for i, (label, lines) in enumerate(blocks):
        corner, colour = placement_for(label, i, corners, spec)

        draw_lines(image, [label, *lines], corner=corner, color=colour, scale=scale,
                   is_bgr=is_bgr, is_gray=is_gray)

    return image


def timing_payload(data: dict | None, served: float | None = None) -> dict:
    """The timing chain as plain data, for travelling inside the JPEG itself.

    The browser gets the picture on one URL and the subject data on another, and
    nothing ties one to the other: a reading of "this frame took N seconds" is
    only as good as the assumption that the numbers belong to the frame on
    screen. Carried in the frame's own bytes, that assumption is gone.
    """

    meta = (data or {}).get('meta') or {}
    payload = {
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


def parse_placement(spec: str | None) -> dict[str, list[str]]:
    """`'video_in=top-left:#0f0, webvis=bottom-right'` -> `{'videoin': ['top-left', '#0f0'], ...}`.

    One spelling for corner and colour, since both are the same kind of statement
    about one filter and two option formats double what a reader has to
    remember. A value is a colour when it starts with `#` and a corner
    otherwise, so order does not matter. Names match case-insensitively and
    ignore underscores: the config says `video_in`, the timing chain says
    `VideoIn`.

    An unparseable entry is dropped with a warning rather than raising, so a typo
    costs that block its placement instead of costing the run.
    """

    out: dict[str, list[str]] = {}

    for part in (spec or '').split(','):
        if not (part := part.strip()):
            continue

        name, sep, value = part.partition('=')

        if not sep or not (value := value.strip()):
            logger.warning('timings: ignoring %r, expected <filter>=<corner>[:#colour]', part)
            continue

        key = name.strip().replace('_', '').lower()
        out.setdefault(key, []).extend(v.strip() for v in value.split(':') if v.strip())

    return out


def placement_for(name: str, index: int, corners: list[str],
                  spec: dict[str, list[str]]) -> tuple[str, tuple[int, int, int]]:
    """The corner and colour a block ends up with, after any per-filter override.

    Unset, a block takes the corner its position in the chain gives it and the
    colour that corner carries, so two filters never come out looking alike
    without anyone having configured anything.
    """

    corner = corners[index]
    colour = None

    for value in spec.get(name.replace('_', '').lower(), []):
        if value.startswith('#'):
            colour = parse_color(value)
        elif value in CORNERS:
            corner = value
        else:
            logger.warning('timings: unknown corner %r for %s, keeping %s', value, name, corner)

    return corner, colour if colour is not None else CORNER_COLORS.get(corner, (255, 255, 255))
