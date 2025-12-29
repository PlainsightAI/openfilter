import logging
import os
import re
from threading import Condition, Event, Thread
from time import time_ns, sleep
from typing import Any
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np

from openfilter.filter_runtime.utils import json_getval, dict_without, split_commas_maybe, Deque

__all__ = ['is_screen', 'ScreenReader', 'MultiScreenReader']

logger = logging.getLogger(__name__)

SCREEN_IN_BGR      = bool(json_getval((os.getenv('SCREEN_IN_BGR') or 'true').lower()))
SCREEN_IN_MAXFPS   = None if (_ := json_getval((os.getenv('SCREEN_IN_MAXFPS') or 'null').lower())) is None else float(_)
SCREEN_IN_MAXSIZE  = os.getenv('SCREEN_IN_MAXSIZE') or None
SCREEN_IN_RESIZE   = os.getenv('SCREEN_IN_RESIZE') or None
SCREEN_IN_BACKEND  = os.getenv('SCREEN_IN_BACKEND') or None

re_screen = re.compile(r'^screen://')

is_screen = lambda name: bool(re_screen.match(name))


re_size = re.compile(r'^\s* (\d+) \s* ([x+]) \s* (\d+) \s* (n(?:ear)? | l(?:in)? | c(?:ub)?)? \s*$', re.VERBOSE | re.IGNORECASE)

def parse_size(s: str):
    if not (m := re_size.match(s)):
        raise ValueError(f'invalid size {s!r}')

    return m.groups()


def parse_screen_uri(screen_uri: str):
    """Parse screen URI into monitor and options.

    Args:
        screen_uri: Screen URI in format screen://[monitor]?params

    Returns:
        dict: {'monitor': int | None, 'options': dict}

    Raises:
        ValueError: If URI format is invalid
    """
    if not screen_uri.startswith('screen://'):
        raise ValueError(f'Invalid screen URI: {screen_uri}')

    parsed = urlparse(screen_uri)
    result = {'monitor': None, 'options': {}}

    # Parse monitor from path: screen://0 -> monitor=0
    if parsed.path and parsed.path != '/' and parsed.path.strip('/'):
        try:
            result['monitor'] = int(parsed.path.lstrip('/'))
        except ValueError:
            raise ValueError(f'Invalid monitor index in {screen_uri}: {parsed.path}')

    # Parse query parameters: ?x=100&y=100&w=800&h=600
    if parsed.query:
        params = parse_qs(parsed.query)
        for key, values in params.items():
            value = values[0] if values else None
            if key in ('x', 'y', 'width', 'height', 'monitor'):
                result['options'][key] = int(value)
            elif key == 'w':  # Alias for width
                result['options']['width'] = int(value)
            elif key == 'h':  # Alias for height
                result['options']['height'] = int(value)
            else:
                result['options'][key] = value

    # Monitor from query params overrides path
    if 'monitor' in result['options']:
        result['monitor'] = result['options'].pop('monitor')

    return result


class ScreenReader:
    def __init__(self,
        source:  str,
        cond:    Condition | None = None,
        *,
        monitor: int | None = None,
        region:  dict | None = None,
        backend: str | None = None,
        bgr:     bool | None = None,
        maxfps:  float | None = None,
        maxsize: str | None = None,
        resize:  str | None = None,
    ):
        """Read screen capture continuously using ScreenGear.

        Args:
            source: Source screen identifier for logging purposes.

            cond: A threading.Condition to .notify_all() whenever a new frame is read.

            monitor: Monitor index using 0-based indexing (0=primary, 1=secondary, etc., -1=all monitors).
                Internally converted to 1-based indexing for VidGear compatibility.

            region: Region dict with 'x', 'y', 'width', 'height' for partial capture.

            backend: ScreenGear backend ('mss', 'dxcam', 'pil', etc).

            bgr: True means images in BGR mode, False means RGB. Has env var default.

            maxfps: Maximum frames per second to output.

            maxsize: Maximum image size to allow, above this will be resized down. Valid codes are '123x456' which will
                proportionally resize maintaining aspect ratio so that neither dimension exceeds the max, '123+456' will
                resize without maintaining aspect ratio. Optional suffixes 'near', 'lin' and 'cub' specify
                interpolation, default is 'near'est neighbor.

            resize: Straight resize always, can not be specified together with `maxsize`, it is one or the other.
        """

        from vidgear.gears import ScreenGear

        self.ScreenGear    = ScreenGear
        self.source        = source
        self.cond          = cond
        self.monitor       = monitor
        self.region        = region
        self.backend       = backend or SCREEN_IN_BACKEND
        self.maxfps        = maxfps = SCREEN_IN_MAXFPS if maxfps is None else maxfps
        self.maxsize       = None if (s := SCREEN_IN_MAXSIZE if maxsize is None else maxsize) is None else parse_size(s)
        self.resize        = None if (s := SCREEN_IN_RESIZE if resize is None else resize) is None else parse_size(s)
        self.state         = 0     # 0 = before start, 1 = playing, 2 = stopped / done
        self.ns_per_maxfps = None if maxfps is None else 1_000_000_000 // maxfps
        self.as_bgr        = bool(SCREEN_IN_BGR if bgr is None else bgr)

        if self.maxsize and self.resize:
            raise ValueError(f"can not specify both 'maxsize' and 'resize' together in {self.source!r}")

        # Build ScreenGear options
        options = {}
        if region:
            if 'x' in region:
                options['left'] = region['x']
            if 'y' in region:
                options['top'] = region['y']
            if 'width' in region:
                options['width'] = region['width']
            if 'height' in region:
                options['height'] = region['height']

        # Build ScreenGear kwargs
        sg_kwargs = {}
        if monitor is not None:
            # Convert 0-based monitor index to 1-based for VidGear
            # Special case: monitor=-1 (all monitors) remains unchanged
            sg_kwargs['monitor'] = monitor + 1 if monitor >= 0 else monitor
        if self.backend:
            sg_kwargs['backend'] = self.backend
        if options:
            sg_kwargs['options'] = options

        logger.debug(f'Initializing ScreenGear with: {sg_kwargs}')

        self.stop_evt = Event()
        self.deque    = Deque(maxlen=1)
        self.thread   = Thread(target=self.thread_reader, daemon=True)
        self.stream   = ScreenGear(**sg_kwargs)

        # Get frame rate info (screens don't have inherent FPS, so we use maxfps or default)
        self.fps = maxfps if maxfps is not None else 30  # Default to 30 FPS for screens

        fps_str = f'  ({self.fps:.1f} fps)' if maxfps is not None else ''

        logger.info(f'screen open: {self.source}{fps_str}')

    def __iter__(self):
        return self

    def __next__(self):
        if (item := self.read()) is None:
            raise StopIteration

        return item

    def start(self):  # idempotent and safe to call whenever
        if self.state != 0:
            return

        self.state  = 1
        self.tmaxfps = time_ns()

        self.stream.start()
        self.thread.start()

    def stop(self):  # idempotent and safe to call whenever
        if self.state != 1:
            return

        self.state = 2

        self.stop_evt.set()
        self.stream.stop()

    def read_one(self):
        while True:
            image = self.stream.read()

            if image is None:
                logger.debug(f'{self.source}: ScreenGear.read() returned None')
                return None

            # Apply FPS limiting
            if (ns_per_maxfps := self.ns_per_maxfps) is not None:
                t = time_ns()
                if (tdiff := t - (tmaxfps := self.tmaxfps)) < ns_per_maxfps:
                    continue  # Skip this frame and read next one

                self.tmaxfps = tmaxfps + (tdiff // ns_per_maxfps) * ns_per_maxfps

            return image

    def thread_reader(self):  # continuous screen capture
        cond = self.cond

        if size := (maxsize := self.maxsize) or self.resize:
            width, aspect, height, interp = size

            width  = int(width)
            height = int(height)
            aspect = aspect != '+'
            interp = (
                cv2.INTER_NEAREST
                if interp is None or (interp := interp.upper()[:1]) == 'N' else
                cv2.INTER_CUBIC
                if interp == 'C' else
                cv2.INTER_LINEAR
            )

        while True:
            image  = None if self.stop_evt.is_set() else self.read_one()
            tframe = time_ns()

            if image is not None:
                shape = image.shape

                if size:
                    h, w, *_ = shape

                    if maxsize:
                        if (hgt := (oh := h) > height) + (wgt := (ow := w) > width):
                            if aspect:
                                if not hgt:
                                    h = int(h * width / w)
                                elif not wgt:
                                    w = int(w * height / h)
                                else:
                                    h = int(h * (s := min(width / w, height / h)))
                                    w = int(w * s)

                            if (newsize := (min(width, w), min(height, h))) != (ow, oh):
                                image = cv2.resize(image, newsize, interpolation=interp)

                    else:  # resize
                        if (hne := h != height) + (wne := w != width):
                            if not aspect:
                                newsize = (width, height)
                            elif not hne:
                                newsize = (width, int(h * width / w))
                            elif not wne:
                                newsize = (int(w * height / h), height)
                            else:
                                newsize = (int(w * (s := min(width / w, height / h))), int(h * s))

                            image = cv2.resize(image, newsize, interpolation=interp)

                if len(shape) == 2:
                    self.as_bgr = False  # grayscale
                elif len(shape) == 3:
                    channels = shape[2]
                    if channels == 4:
                        # Just drop the alpha channel - NO color conversion
                        # ScreenGear might already be in the right format
                        image = np.ascontiguousarray(image[:, :, :3])
                    elif channels == 3 and not self.as_bgr:
                        # Convert RGB to BGR
                        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

            self.deque.append((image, tframe))

            if cond is not None:
                with cond:
                    cond.notify_all()

            if image is None:
                break

        self.state = 2

    @property
    def playing(self) -> bool:
        return self.state == 1

    @property
    def stopped(self) -> bool:
        return self.state == 2

    @property
    def frame_available(self) -> bool:
        return bool(self.deque)

    def read(self, with_tframe=False):  # -> np.ndarray | tuple[np.ndarray, int] | None
        if self.state == 0:
            raise RuntimeError('can not read from screen before it is started')
        elif self.state == 2:
            return None

        if (image_n_tframe := self.deque.popleft()) is None:
            self.state = 2

            self.stream.stop()

            return None

        return image_n_tframe if with_tframe else image_n_tframe[0]


class MultiScreenReader:
    """Read multiple screens simultaneously returning time-synchronized frames."""

    def __init__(self, sources: list[str], sources_kwargs: list[dict[str, Any]] | None = None):
        kwargss       = [{}] * len(sources) if sources_kwargs is None else sources_kwargs
        self.cond     = cond = Condition()
        self.screens  = [ScreenReader(source, cond, **kwargs) for source, kwargs in zip(sources, kwargss)]
        self.state    = 0  # 0 = before start, 1 = playing, 2 = stopped / done

    def __iter__(self):
        return self

    def __next__(self):
        if (item := self.read()) is None:
            raise StopIteration

        return item

    def start(self):  # idempotent and safe to call whenever
        if self.state != 0:
            return

        self.state = 1

        for screen in self.screens:
            screen.start()

    def stop(self):  # idempotent and safe to call whenever
        if self.state != 1:
            return

        self.state = 2

        for screen in self.screens:
            screen.stop()

    @property
    def playing(self) -> bool:
        return self.state == 1

    @property
    def stopped(self) -> bool:
        return self.state == 2

    @property
    def frame_available(self) -> bool:
        return all(scrn.frame_available for scrn in self.screens)

    def read(self, with_tframe=False):  # -> list[np.ndarray | tuple[np.ndarray, int]] | None
        if self.state == 0:
            raise RuntimeError('can not read from screens before they are started')
        elif self.state == 2:
            return None

        cond    = self.cond
        screens = self.screens

        while not all(screen.frame_available for screen in screens):
            with cond:
                cond.wait()

        images = [screen.read(with_tframe) for screen in screens]

        if any(image is None for image in images):
            self.stop()

            return None

        return images


# --- CUT HERE ---------------------------------------------------------------------------------------------------------

from openfilter.filter_runtime.filter import Frame, FilterConfig, Filter
from openfilter.filter_runtime.utils import adict, split_commas_maybe

__all__ = __all__ + ['ScreenInConfig', 'ScreenIn']

is_screen_or_cached_file = lambda s: is_screen(s)


class ScreenInConfig(FilterConfig):
    class Source(adict):
        class Options(adict):
            monitor:    int | None
            x:          int | None
            y:          int | None
            width:      int | None
            height:     int | None
            backend:    str | None
            bgr:        bool | None
            maxfps:     float | None
            maxsize:    str | None
            resize:     str | None

        source:  str
        topic:   str | None
        options: Options | None

    sources: str | list[str | Source]

    # setting these here will make them default for all screens (overridable individually)
    bgr:     bool | None
    maxfps:  float | None
    maxsize: str | None
    resize:  str | None
    backend: str | None


class ScreenIn(Filter):
    """Single or multiple screen input filter. Screens are assigned to topics via the ';' mapping character in `sources`.
    The default topic mapping if nothing specified is 'main'. All screen sources must have unique topics. '!' allows
    setting options directly in the source string.

    config:
        sources:
            The source(s) of the screen(s), comma delimited, can be screen://monitor_index or screen://monitor?params.

            Examples:
                'screen://0!maxfps=10, screen://1!maxfps=15;monitor1'

                    is the same as

                ['screen://0!maxfps=10', 'screen://1!maxfps=15;monitor1']

                    is the same as

                [{'source': 'screen://0', 'topic': 'main', 'options': {'maxfps': 10}},
                 {'source': 'screen://1', 'topic': 'monitor1', 'options': {'maxfps': 15}}]

                    For 'options' see below.

            `sources` individual options (text appended after source, e.g. 'screen://0!maxfps=10!backend=mss'):
                '!bgr', '!no-bgr':
                    Set `bgr` option for this source.

                '!maxfps=10':
                    Set `maxfps` option for this source.

                '!maxsize=1280x720', '!maxsize=1280+720C':
                    Set `maxsize` option for this source.

                '!resize=1280x720lin', '!resize=1280+720':
                    Set `resize` option for this source.

                '!backend=mss':
                    Set backend for ScreenGear. Options: 'mss', 'dxcam', 'pil'

                '!monitor=1':
                    Set monitor index (can also be in URI path: screen://1)

                '!x=100', '!y=100', '!width=800', '!height=600':
                    Set region capture parameters

        bgr:
            True means images in BGR format, False means RGB. Set here to apply to all sources or can be set
            individually per source. Global env var default SCREEN_IN_BGR.

        maxfps:
            Maximum frames per second to capture. Works for all screens. Set here to apply to all sources or can be set
            individually per source. Global env var default SCREEN_IN_MAXFPS.

        maxsize:
            Maximum image size to allow, above this will be resized down. Valid codes are 'WxH' which will
            proportionally resize maintaining aspect ratio so that neither dimension exceeds the max, 'W+H' will resize
            without maintaining aspect ratio. Optional suffixes 'near', 'lin' and 'cub' specify interpolation, default
            is 'near'est neighbor. Set here to apply to all sources or can be set individually per source. Global env
            var default SCREEN_IN_MAXSIZE.

        resize:
            Same as `maxsize` but is always applied unconditionally regardless of input size. Can not be specified
            together with `maxsize`, it is one or the other. Set here to apply to all sources or can be set individually
            per source. Global env var default SCREEN_IN_RESIZE.

        backend:
            ScreenGear backend to use ('mss', 'dxcam', 'pil'). Platform-specific - 'dxcam' is fastest on Windows,
            'mss' is most compatible. Set here to apply to all sources or can be set individually per source. Global
            env var default SCREEN_IN_BACKEND.

    Environment variables:
        SCREEN_IN_BGR
        SCREEN_IN_MAXFPS
        SCREEN_IN_MAXSIZE
        SCREEN_IN_RESIZE
        SCREEN_IN_BACKEND

    Platform Considerations:
        Windows: Preferred backend is 'dxcam' (hardware accelerated), fallback to 'mss'
        macOS: Use 'mss', requires Screen Recording permission in System Preferences
        Linux: Use 'mss', requires X11 display server

    Usage Examples:
        # Basic screen capture
        openfilter run - ScreenIn --sources screen://0 - Webvis

        # Capture with FPS limit
        openfilter run - ScreenIn --sources screen://0!maxfps=10 - Webvis

        # Capture specific region
        openfilter run - ScreenIn --sources 'screen://0?x=100&y=100&w=800&h=600' - Webvis

        # Multi-monitor capture
        openfilter run - ScreenIn --sources 'screen://0;monitor0,screen://1;monitor1' - Webvis
    """

    FILTER_TYPE = 'Input'

    @classmethod
    def normalize_config(cls, config):
        sources = split_commas_maybe(config.get('sources'))
        config  = ScreenInConfig(super().normalize_config(dict_without(config, 'sources')))

        if sources is not None:
            config.sources = sources

        if not sources:
            raise ValueError('must specify at least one source')
        if not config.outputs:
            raise ValueError('must specify at least one output')

        for idx, source in enumerate(sources):
            if isinstance(source, dict):
                if not isinstance(source, ScreenInConfig.Source):
                    sources[idx] = ScreenInConfig.Source(source)

            else:
                source, topic   = Filter.parse_topics(source, 1, False)
                source, options = Filter.parse_options(source)

                # Parse screen URI if it's a screen:// URI
                if is_screen(source):
                    parsed = parse_screen_uri(source)
                    # Merge parsed options with inline options
                    if parsed['monitor'] is not None and 'monitor' not in options:
                        options['monitor'] = parsed['monitor']
                    options.update(parsed['options'])

                sources[idx] = ScreenInConfig.Source(source=source, topic=topic and topic[0],
                    options=ScreenInConfig.Source.Options(options))

        for source in sources:
            if (topic := source.topic) is None:
                source.topic = 'main'
            if not isinstance(options := source.options, ScreenInConfig.Source.Options):
                source.options = options = ScreenInConfig.Source.Options() if options is None else ScreenInConfig.Source.Options(options)
            if any((option := o) not in ('bgr', 'maxfps', 'maxsize', 'resize', 'backend', 'monitor', 'x', 'y', 'width', 'height') for o in options):
                raise ValueError(f'unknown option {option!r} in {source!r}')

        if len(set(source.topic for source in sources)) != len(sources):
            raise ValueError(f'duplicate screen topics in {sources!r}')
        if not all(is_screen_or_cached_file(source.source) for source in sources):
            raise ValueError('this filter only accepts screen sources')

        return config

    def init(self, config):
        super().init(FilterConfig(config, sources=None))

    def setup(self, config):
        ssources = []
        topics   = []
        optionss = []

        for source in config.sources:
            # Parse screen URI to extract monitor
            if is_screen(source.source):
                parsed = parse_screen_uri(source.source)
                monitor = source.options.monitor if source.options.monitor is not None else parsed['monitor']
            else:
                monitor = source.options.monitor

            # Build region dict if coordinates specified
            region = {}
            for key in ('x', 'y', 'width', 'height'):
                if source.options.get(key) is not None:
                    region[key] = source.options[key]

            ssources.append(source.source)
            topics.append(source.topic or 'main')

            # Build kwargs for ScreenReader
            kwargs = {
                'monitor': monitor,
                'region': region if region else None,
                'backend': source.options.backend or config.backend,
                'bgr': source.options.bgr if source.options.bgr is not None else config.bgr,
                'maxfps': source.options.maxfps if source.options.maxfps is not None else config.maxfps,
                'maxsize': source.options.maxsize or config.maxsize,
                'resize': source.options.resize or config.resize,
            }
            optionss.append(kwargs)

        self.msreader    = MultiScreenReader(ssources, optionss)
        self.tops_n_scrns = tuple(zip(topics, self.msreader.screens))
        self.id          = -1  # frame id

        self.msreader.start()

    def shutdown(self):
        self.msreader.stop()

    def process(self, frames):
        def get():
            if (image_n_tframes := self.msreader.read(True)) is None:
                self.exit('screen capture ended')

            self.id = id = self.id + 1

            return {topic: Frame(img,
                {'meta': {'id': id, 'ts': tfrm / 1_000_000_000, 'src': scrn.source, 'monitor': scrn.monitor, 'backend': scrn.backend}},
                'GRAY' if len(img.shape) == 2 else 'BGR' if scrn.as_bgr else 'RGB'
            ) for (topic, scrn), (img, tfrm) in zip(self.tops_n_scrns, image_n_tframes)}

        return get


if __name__ == '__main__':
    ScreenIn.run()
