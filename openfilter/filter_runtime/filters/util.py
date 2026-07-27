import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pprint import pformat
from time import sleep, time

import cv2

from openfilter.filter_runtime.filter import FilterConfig, Filter, Frame
from openfilter.filter_runtime.metrics import Metrics
from openfilter.filter_runtime.mq import MQ
from openfilter.filter_runtime.utils import split_commas_maybe, once, adict

__all__ = ['UtilConfig', 'Util']

logger = logging.getLogger(__name__)

re_size = re.compile(r'^\s* (\d+) \s* ([x+]) \s* (\d+) \s* (n(?:ear)? | l(?:in)? | c(?:ub)?)? \s*$', re.VERBOSE | re.IGNORECASE)
re_box  = re.compile(r'''^
    \s*   ( (?:\d+(?:\.\d*)?) | (?:\d*\.\d+) )   \s* \+
    \s*   ( (?:\d+(?:\.\d*)?) | (?:\d*\.\d+) )   \s* x
    \s*   ( (?:\d+(?:\.\d*)?) | (?:\d*\.\d+) )   \s* x
    \s*   ( (?:\d+(?:\.\d*)?) | (?:\d*\.\d+) )   \s*
    (?:   \#([0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?)  \s*)?
$''', re.VERBOSE)


class UtilConfig(FilterConfig):
    class XForm(adict):
        action: str
        topics: list[str] | None  # None means all topics
        # other fields may be present

    log:    bool | str | None
    sleep:  float | None
    maxfps: float | None

    xforms: str | list[str | XForm] | None


class Util(Filter):
    """Generic util filter that can do a few miscellaneous things. Anything that comes in on `sources` is sent out again
    on `outputs` (if any are provided) after applying any potential `xforms`. Usually used to log data in 'pretty' mode.

    config:
        log:
            None, 'image', 'data', 'all' (same as True) or 'pretty'. LOG_LEVEL must be at 'info' or below. This will log
            data coming in from `sources`. For images it will just log their dimensions and format.

        sleep:
            None or float seconds per call to process(). Will guarantee spend at least this time in each process() call,
            a good way to slow down a pipeline if you need to.

        maxfps:
            Maximum fps to allow, can mix with `sleep`. Unlike `sleep` though, this will look at how much time has
            passed and sleep the right amount of time to maintain the framerate at this value, whereas sleep just
            sleeps this amount of time per call regardless of how much time is passed elsewhere.

        xforms:
            This is a list of transforms to apply to all or some topic images in order. The list of transforms that can
            be applied is as follows:

            flipx    - Flip THE X axis, not around it.
            flipy    - "
            flipboth - Same as rotate by 180 degrees.
            rotcw    - By 90 degrees.
            rotccw   - "
            swaprgb  - WARNING! As much as you want to, don't use this to solve your RGB problem, that is most likely
                caused by using the wrong '.rgb' or '.bgr'. This is only here for extreme cases when the actual primary
                source itself is confused about the format.
            fmtrgb   - These don't do what you think, only really useful for converting to and from grayscale.
            fmtbgr   - "
            fmtgray  - "
            resize   - "width (x or +) height [n[ear] or l[in] or c[ub]]", 'x' preserves aspect ratio and '+' does not,
                e.g. "640+480lin", "1280 + 720"
            maxsize  - "
            minsize  - "
            box      - Draw solid color box, "x + y x width x height [#??? or #??????]", in relative coords [0.0..1.0],
                '?' is hex char for color (which is RGB regardless of frame format).

            examples:
                xforms = 'flipx;main' - Flip the 'main' topic image on X (around the Y axis).

                xforms = 'flipx;main, maxsize 640+480lin;main;other' - Same as above except then resize both the 'main'
                    topic image and the 'other' topic image to a maximum 640 width and 480 height NOT preserving the
                    aspect ratio because of the '+' instead of 'x'.

                xforms = 'fmtgray, box 0+0x.5x.5#f00' - Reformat all images on all topics to grayscale (if they are not
                    already so) and then draw a red '#f00' box in the upper-left hand corner (pos 0,0 width 0.5 x 0.5).
    """

    FILTER_TYPE = 'System'

    @classmethod
    def normalize_config(cls, config):
        config = UtilConfig(super().normalize_config(config))

        if (log := config.log) is not None:
            if (new_log := MQ.LOG_MAP.get(log)) is None:
                raise ValueError(f'invalid log {log!r}, must be one of {list(MQ.LOG_MAP)}')
            else:
                config.log = new_log

        if not isinstance(config.sleep, (int, float, None.__class__)):
            raise ValueError(f'sleep must be a float, int or None')

        if not isinstance(config.maxfps, (int, float, None.__class__)):
            raise ValueError(f'maxfps must be a float, int or None')

        if xforms := config.xforms:
            xforms     = split_commas_maybe(xforms)
            new_xforms = []

            for xform in xforms:
                if isinstance(xform, str):
                    xform, topics = Filter.parse_topics(xform, mapping=False)
                    action, *args = xform.split(' ', 1)
                    xform         = UtilConfig.XForm(action=(action := action.lower()))
                    args          = args[0] if args else None

                    if topics is not None:
                        xform.topics = topics

                    if action in ('flipx', 'flipy', 'flipboth', 'rotcw', 'rotccw', 'swaprgb', 'fmtrgb', 'fmtbgr', 'fmtgray'):
                        if args:
                            raise ValueError(f'xform {action} does not take parameters')

                    elif action in ('resize', 'maxsize', 'minsize'):
                        if (m := re_size.match(args)) is None:
                            raise ValueError(f'invalid size {args!r}')

                        width, aspect, height, interp = m.groups()

                        xform.width  = int(width)
                        xform.height = int(height)

                        if aspect != 'x':
                            xform.aspect = False

                            if action == 'resize':
                                logger.warning(f"non-aspect ratio size {args.strip()!r} meaningless for resize")

                        if interp is not None:
                            xform.interp = interp.upper()[:1]

                    elif action == 'box':
                        if (m := re_box.match(args)) is None:
                            raise ValueError(f'invalid box {args!r}')

                        x, y, w, h, c = m.groups()

                        xform.x      = float(x)
                        xform.y      = float(y)
                        xform.width  = float(w)
                        xform.height = float(h)

                        if c is not None:
                            xform.color = (
                                (int(c[0] * 2, 16), int(c[1] * 2, 16), int(c[2] * 2, 16))
                                if len(c) == 3 else
                                (int(c[:2], 16), int(c[2 : 4], 16), int(c[4:], 16))
                            )

                    else:
                        raise ValueError(f'invalid xform action {action!r}')

                new_xforms.append(xform)

            config.xforms = new_xforms

        return config

    def setup(self, config):
        self.log          = config.log or False
        self.fps_td       = 0
        self.sleep        = config.sleep or None
        self.t_maxfps     = time()
        self.t_per_maxfps = None if (maxfps := config.maxfps) is None else 1 / maxfps
        self.xforms       = config.xforms
        self.executor     = ThreadPoolExecutor()

    def process(self, frames):
        t = time()

        if (log := self.log) and (log_text := Metrics.log_text(log, frames, dict(fps=self.metrics["fps"]))):
            logger.info(f'{self.config.id} - {log_text}')

        if xforms := self.xforms:
            topic_xforms = {t: adict(topic=t, frame=f, xforms=[]) for t, f in frames.items() if f.has_image}

            for xform in xforms:
                if (xform_topics := xform.topics) is None:  # apply to all topics
                    for topic_xform in topic_xforms.values():
                        topic_xform.xforms.append(xform)

                else:
                    for topic in xform_topics:
                        if topic not in frames:
                            once(logger.warning, f'topic {topic!r} not in received topics {tuple(frames)!r}', t=60*15)
                        elif topic_xform := topic_xforms.get(topic):
                            topic_xform.xforms.append(xform)

            res = self.executor.map(self.execute_xforms, topic_xforms.values())

            for topic_xform in res:
                frames[topic_xform.topic] = topic_xform.frame

        if self.sleep:
            sleep(max(0, self.sleep - (time() - t)))  # to account for xforms

        if t_per_maxfps := self.t_per_maxfps:  # apply maxfps AFTER sleep to take that into account
            if (tleft := (t_per_maxfps - ((t := time()) - (t_maxfps := self.t_maxfps)))) >= 0:
                sleep(tleft)

                t = t_maxfps + t_per_maxfps

            self.t_maxfps = t

        return frames

    def execute_xforms(self, topic_xform):
        frame = topic_xform.frame

        for xform in topic_xform.xforms:
            action = xform.action

            if action == 'flipx':
                frame = Frame(cv2.flip(frame.image, 1), frame)
            elif action == 'flipy':
                frame = Frame(cv2.flip(frame.image, 0), frame)
            elif action == 'flipboth':
                frame = Frame(cv2.flip(frame.image, -1), frame)
            elif action == 'rotcw':
                frame = Frame(cv2.rotate(frame.image, cv2.ROTATE_90_CLOCKWISE), frame)
            elif action == 'rotccw':
                frame = Frame(cv2.rotate(frame.image, cv2.ROTATE_90_COUNTERCLOCKWISE), frame)
            elif action == 'swaprgb':
                frame = frame if frame.is_gray else Frame(cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB), frame)
            elif action == 'fmtrgb':
                frame = frame.rgb
            elif action == 'fmtbgr':
                frame = frame.bgr
            elif action == 'fmtgray':
                frame = frame.gray
            elif action in ('resize', 'maxsize', 'minsize'):
                frame = self.execute_xform_size(xform, frame)
            elif action == 'box':
                frame = self.execute_xform_box(xform, frame)
            else:
                raise ValueError(f'unknown xform {action!r}')

        topic_xform.frame = frame

        return topic_xform

    def execute_xform_size(self, xform, frame):
        width  = xform.width
        height = xform.height
        interp = (
            cv2.INTER_NEAREST
            if (interp := xform.get('interp', 'N')) == 'N' else
            cv2.INTER_CUBIC
            if interp == 'C' else
            cv2.INTER_LINEAR
            if interp == 'L' else
            cv2.INTER_NEAREST
        )

        if xform.action == 'resize':
            w = width
            h = height

        elif xform.action == 'maxsize':
            if (hgt := (h := frame.height) > height) + (wgt := (w := frame.width) > width) and xform.get('aspect', True):
                if not hgt:
                    h = int(h * width / w)
                elif not wgt:
                    w = int(w * height / h)
                else:
                    h = int(h * (s := min(width / w, height / h)))
                    w = int(w * s)

            w = min(w, width)
            h = min(h, height)

        else:  # action == 'minsize':
            if (hgt := (h := frame.height) < height) + (wgt := (w := frame.width) < width) and xform.get('aspect', True):
                if not hgt:
                    h = int(h * width / w)
                elif not wgt:
                    w = int(w * height / h)
                else:
                    h = int(h * (s := max(width / w, height / h)))
                    w = int(w * s)

            w = max(w, width)
            h = max(h, height)

        if w != frame.width or h != frame.height:
            frame = Frame(cv2.resize(frame.image, (w, h), interpolation=interp), frame)

        return frame

    def execute_xform_box(self, xform, frame):
        image = frame.rw.image

        if (c := xform.color) is None:
            c = 0 if frame.is_gray else (0, 0, 0)
        elif frame.is_gray:
            c = round(sum(c) / 3)
        elif frame.is_bgr:
            c = c[::-1]

        w  = frame.width
        h  = frame.height
        x1 = (x0 := xform.x) + xform.width
        y1 = (y0 := xform.y) + xform.height

        return Frame(cv2.rectangle(image, (int(w * x0), int(h * y0)), (int(w * x1), int(h * y1)), c, -1), frame)


if __name__ == '__main__':
    Util.run()
