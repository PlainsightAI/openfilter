import logging
import os
import re
from statistics import median_high, stdev
from time import time_ns, strftime
from typing import Any, Literal

import av
import cv2

from openfilter.filter_runtime.utils import json_getval, dict_without, split_commas_maybe, hide_uri_users_and_pwds, once

__all__ = ['VideoWriter']

logger = logging.getLogger(__name__)

parse_segtime     = lambda s: sum(float(a) * b for a, b in zip(([0] + str(s).split(':', 1))[-2:], (60, 1))) if s else None  # -> '02:21' -> 141, segtime in minutes

VIDEO_OUT_BGR     = bool(json_getval((os.getenv('VIDEO_OUT_BGR') or os.getenv('FILTER_BGR') or 'true').lower()))
VIDEO_OUT_FPS     = json_getval((os.getenv('VIDEO_OUT_FPS') or os.getenv('FILTER_FPS') or 'null').lower())
VIDEO_OUT_SEGTIME = parse_segtime(json_getval((os.getenv('VIDEO_OUT_SEGTIME') or os.getenv('FILTER_SEGTIME') or 'null').lower()))
VIDEO_OUT_PARAMS  = json_getval(os.getenv('VIDEO_OUT_PARAMS') or os.getenv('FILTER_PARAMS') or 'null')

re_video          = re.compile(r'^(rtsp|rtmp|http|https|file|webcam)://')
re_video_stream   = re.compile(r'^(rtsp|rtmp|http|https)://')

is_video          = lambda name: bool(re_video.match(name))
is_video_file     = lambda name: name.startswith('file://')
is_video_webcam   = lambda name: name.startswith('webcam://')
is_video_stream   = lambda name: bool(re_video_stream.match(name))

# PyAV stream properties set directly on the stream object (not via stream.options)
_STREAM_PROPS = {
    'pix_fmt':  'pix_fmt',
    'g':        'gop_size',
    'gop_size': 'gop_size',
    'bitrate':  'bit_rate',
    'bit_rate': 'bit_rate',
}


class VideoWriter:
    def __init__(self,
        output:  str,
        *,
        bgr:     bool | None = None,
        fps:     int | float | Literal[True] | None = True,
        segtime: int | float | None = None,
        params:  dict | None = None
    ):
        """Write a single segmented video file or rtsp stream.

        Args:
            output: Destination video stream, can be file or RTSP stream. If file, then can be segmented into `segtime`
                minute-long chunks in which case output filename is first formatted using time.strftime() then
                potentially a segment index specified with '%d'.

            bgr: True means images in BGR mode, False means RGB. Has env var default.

            fps: The framerate value for the video metadata. Actual fps may not be this in which case the video will
                look weird. If None then it will be set to a default value from an environment variable. If True then
                adaptive fps is used. This will track rate at which frames are written and set this rate for each new
                file segment or restart the RTSP stream if it strays too far from what the stream is set to.

            segtime: Only valid for file output. If not None then break up file output into individual segments of this
                length in minutes. If specified, the source filename can be treated as a template to use 'strftime()' on
                and a segment index will be added as well.

            params: Dictionary of encoding parameters. Keys may be prefixed with '-' (WriteGear compat) or bare.
                "crf":     Sets the constant rate factor for controlling video quality (0=best quality, 51=worst). Example: "crf": 23
                "preset":  Sets the encoding preset for balancing speed and compression. Example: "preset": "ultrafast"
                "bitrate": Sets the video bitrate. Example: "bitrate": "1M" (1 megabit per second)
                "pix_fmt": Sets the pixel format. Example: "pix_fmt": "yuv420p"
                "g":       Sets the group of pictures (GOP) size. Example: "g": 50
        """

        if segtime and is_video_stream(output):
            raise ValueError(f'an RTSP output can not have segments: {output!r}')

        self.output    = output
        self.params    = {**{f'-{p}': v for p, v in (VIDEO_OUT_PARAMS or {}).items()}, **(params or {})}
        self.is_bgr    = bool(VIDEO_OUT_BGR if bgr is None else bgr)
        self.is_stream = is_stream = is_video_stream(output)
        self.segtime   = None if is_stream else (VIDEO_OUT_SEGTIME if segtime is None else segtime)
        self.out_split = output.rsplit('.', 1)
        self.segidx    = 0
        self.segend    = float('inf')  # if segtime is None then this makes sure the current output file never ends
        self.segfrm    = 0
        self.container = None
        self.stream    = None
        self.pts       = 0

        if ((fps := VIDEO_OUT_FPS or 15) if fps is None else fps) is True:  # None -> VIDEO_OUT_FPS, True -> 15/adaptive
            self.fps     = 15
            self.t_frame = None
            self.write   = self.write_adapt_begin

        else:
            self.fps = fps

            self.new_writer()

    @staticmethod
    def _parse_params(params):
        """Split params dict into (codec_name, container_format, container_options, stream_props, stream_options).

        Handles both bare keys and '-' prefixed keys (WriteGear compat).
        """
        codec_name        = 'libx264'
        container_format  = None
        container_options = {}
        stream_props      = {}
        stream_options    = {}

        for key, value in params.items():
            k = key.lstrip('-')

            if k == 'vcodec':
                codec_name = value
            elif k == 'f':
                container_format = value
            elif k in ('rtsp_transport',):
                container_options[k] = str(value)
            elif k == 'input_framerate':
                pass  # handled via stream rate, not a real param
            elif k in _STREAM_PROPS:
                stream_props[_STREAM_PROPS[k]] = value
            else:
                stream_options[k] = str(value)

        return codec_name, container_format, container_options, stream_props, stream_options

    def start(self):  # idempotent and safe to call whenever
        pass

    def stop(self):  # idempotent and safe to call whenever
        if self.container is not None:
            # flush encoder
            if self.stream is not None:
                try:
                    for packet in self.stream.encode():
                        self.container.mux(packet)
                except Exception:
                    logger.debug('flush failed (stream may have disconnected)')

            self.container.close()
            self.container = None
            self.stream    = None
            self.pts       = 0

    def new_writer(self):
        self.stop()

        if is_stream := self.is_stream:
            output = self.output
            params = {
                '-vcodec':          'libx264',
                '-f':               'rtsp',
                '-rtsp_transport':  'tcp',
                '-input_framerate': self.fps,
                **self.params,
            }

            logger.info(f'video serve: {hide_uri_users_and_pwds(output)}  ({self.fps:.1f} fps)')

        else:
            if (segtime := self.segtime) is None:
                output = self.output

            else:
                self.segidx = (segidx := self.segidx) + 1
                output      = f'{(o := self.out_split)[0]}_{segidx:06}' + ('' if len(o) == 1 else f'.{o[1]}')
                self.segend = segtime * 60 * self.fps
                self.segfrm = 0

            output = strftime(output)
            params = {
                '-vcodec':          'libx264',
                '-input_framerate': self.fps,
                **self.params,
            }

            logger.info(f'video create: {output[7:]}  ({self.fps:.1f} fps)')

        codec_name, container_format, container_options, stream_props, stream_options = self._parse_params(params)

        file_path       = output if is_stream else output[7:]  # strip file:// prefix for local files
        self.container  = av.open(file_path, mode='w', format=container_format, options=container_options or None)
        # stream width/height are set from the first frame in write() since dimensions are unknown here
        self.stream     = stream = self.container.add_stream(codec_name, rate=int(round(self.fps)), options=stream_options or None)
        self.pts        = 0
        self._dims_set  = False

        # apply stream properties
        for prop, value in stream_props.items():
            if prop == 'bit_rate' and isinstance(value, str):
                # parse "1M", "500K" etc
                value = value.strip()
                multiplier = {'k': 1000, 'm': 1_000_000}.get(value[-1:].lower(), 1)
                value = int(float(value.rstrip('kKmM')) * multiplier)
            setattr(stream, prop, value)

        # default pix_fmt if not set
        if 'pix_fmt' not in stream_props:
            stream.pix_fmt = 'yuv420p'

    def write(self, image):  # image: np.ndarray
        if (container := self.container) is None:
            raise RuntimeError('can not write to a closed video')

        if not self.is_bgr and len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        if not self._dims_set:
            h, w = image.shape[:2]
            self.stream.width  = w
            self.stream.height = h
            self._dims_set = True

        frame     = av.VideoFrame.from_ndarray(image, format='bgr24')
        frame.pts = self.pts
        self.pts += 1

        for packet in self.stream.encode(frame):
            container.mux(packet)

        self.segfrm = segfrm = self.segfrm + 1

        if segfrm >= self.segend:
            self.new_writer()

    def write_adapt_begin(self, image):
        self.t_write     = time_ns()
        self.first_image = image
        self.write       = self.write_adapt_create

    def write_adapt_create(self, image):
        td           = (t_write := time_ns()) - self.t_write
        self.write   = self.write_adapt
        self.t_write = t_write

        self.fps_adapt_init(t_write, td)
        self.new_writer()

        VideoWriter.write(self, self.first_image)  # write first delayed image (because we had to get an fps estimate first)
        VideoWriter.write(self, image)

        del self.first_image

    def write_adapt(self, image):
        td           = (t_write := time_ns()) - self.t_write
        self.t_write = t_write

        if self.fps_adapt(t_write, td) and self.is_stream:
            self.new_writer()
        else:
            VideoWriter.write(self, image)

    # FPS adaptive stuff, ALMOST deserves its own class, almost...

    FPS_ADAPT_F_WINDOW = 90                  # frame window for calculating fps
    FPS_ADAPT_F_TRANS  = 45                  # min number of frames required before a deviation from last fps is considered non-transient
    FPS_ADAPT_F_WAIT   = 45                  # minimum frames to pass before allowing new writer again
    FPS_ADAPT_T_WAIT   = 10 * 1_000_000_000  # minimum time to pass before allowing new writer again
    FPS_ADAPT_T_TOL    = 0.2                 # tolerance * stdev to consider fps out of bounds

    def fps_adapt_init(self, t, td):
        self.fps       = fps = max(10, min(30, 1_000_000_000 / td))  # keep things sane to start with
        self.fa_td_cur = td = 1_000_000_000 // fps
        self.fa_tds    = [td]
        self.fa_t_wait = t + self.FPS_ADAPT_T_WAIT
        self.fa_f      = self.FPS_ADAPT_F_WAIT

    def fps_adapt(self, t, td):
        (fa_tds := self.fa_tds).append(td)

        if (l := len(fa_tds)) > (f_win := self.FPS_ADAPT_F_WINDOW):
            del fa_tds[:l - f_win]

        td_med = median_high(fa_tds)
        td_std = stdev(fa_tds)
        # print(f'... {self.fps:.1f} ({1_000_000_000 / self.fa_td_cur:.1f}),  {1_000_000_000 / (td_med + (td_std_tol := td_std * self.FPS_ADAPT_T_TOL)):.1f} - {1_000_000_000 / (td_med - td_std_tol):.1f},  {self.fa_f}')  # DEBUG!

        if (td_med - (td_std_tol := td_std * self.FPS_ADAPT_T_TOL)) <= self.fa_td_cur <= (td_med + td_std_tol):
            self.fa_f = min(self.fa_f + 1, self.FPS_ADAPT_F_TRANS)  # slowly restore frame tolerance for frame count deviations from good fps
            self.fps  = 1_000_000_000 / td_med  # set current most accurate fps in case new file segment is created

            return False  # within tolerance, don't change anything

        self.fa_f = fa_f = self.fa_f - 1

        if fa_f >= 0 or t < self.fa_t_wait:
            return False  # didn't exceed number of frames required for non-transience or wait time from last adapt event, don't change anything yet

        self.fps       = 1_000_000_000 / td_med  # set current most accurate fps in case new file segment is created
        self.fa_td_cur = td_med
        self.fa_t_wait = t + self.FPS_ADAPT_T_WAIT
        self.fa_f      = self.FPS_ADAPT_F_WAIT

        return True


# --- CUT HERE ---------------------------------------------------------------------------------------------------------

from openfilter.filter_runtime.filter import FilterConfig, Filter
from openfilter.filter_runtime.utils import adict, split_commas_maybe

__all__ = __all__ + ['VideoOutConfig', 'VideoOut']


class VideoOutConfig(FilterConfig):
    class Output(adict):
        class Options(adict):
            fps:     float | Literal[True] | None
            segtime: float | None
            params:  dict[str, Any] | None

        output:  str
        topic:   str | None
        options: Options | None

    outputs: str | list[str | Output]

    # setting these will make them default for all videos (overridable individually)
    bgr:     bool | None
    fps:     float | Literal[True] | None
    segtime: float | None
    params:  dict[str, Any] | None


class VideoOut(Filter):
    """Single or multiple video output filter. Videos are assigned to topics via the ';' mapping character in `outputs`.
    The default topic mapping if nothing specified is 'main'. Topics can be sent to multiple video outputs, so the same
    topic can appear multiple times in the outputs. '!' allows setting options directly in the output string.

    config:
        outputs:
            The destination(s) of the video(s), comma delimited, can be file:// or rtsp://. In the case of rtsp://, this
            filter does not serve the stream itself but rather sends to an RTSP proxy like 'bluenviron/mediamtx'.

            Examples:
                'file://a!fps=15!segtime=1, rtsp://b;c'

                    is the same as

                ['file://a!fps=15!segtime=1', 'rtsp://b;c']

                    is the same as

                [{'output': 'file://a', 'topic'?: 'main', 'options'?: {'fps': 15, 'segtime': 1}},
                 {'output': 'rtsp://b', 'topic'?: 'c'}]

                    For 'options' see below.

            `outputs` individual options (text appended after output, e.g. 'file:///myvideo.mp4!no-bgr!segtime=5:00'):
                '!bgr', '!no-bgr':
                    Set `bgr` option for this output.

                '!fps', '!fps=25':
                    Set `fps` option for this output.

                '!segtime=5:00', '!segtime=180', '!segtime=0.5':
                    Set `segtime` option for this output.

                '!params={"crf": 23, "g": 30}', etc...:
                    Set `params` option for this output.

        bgr:
            True means images in BGR format, False means RGB. This is here for emergency purposes only and is NOT the
            inverse of VIDEO_IN_BGR so don't touch this unless you have an explicit need and understanding of why you
            have to change it instead of doing something else to solve your problem. Set here to apply to all outputs or
            can be set infividually per output. Global env var default VIDEO_OUT_BGR.

        fps:
            The framerate value for the video metadata. Can be float value and this will be set for the output. The
            actual video framerate may not be this in which case the video will look too fast or slow. If True then
            adaptive framerate is used. Set here to apply to all outputs or can be set infividually per output. Global
            env var default VIDEO_OUT_FPS.

            NOTE: Adaptive framerate will track rate at which frames are written and set this rate for each new file
            segment created (can't modify already started segment) or restart the RTSP stream if the rate strays too far
            from what the stream is set to. Note that this will only work for files if they are output in segments,
            otherwise there will never be an opportunity to set a more correct framerate than the initial guess, which
            is usually not accurate at all.

        segtime:
            Only valid for file output. If this is specified then the output file is broken up into segments of at MOST
            `segtime` minutes, not size. The output filename will be treated as a template to use 'strftime()' on
            (https://docs.python.org/3/library/time.html#time.strftime) and a segment index will be appended to the end
            of the filename as well. For example, a filename with the date and time would be:
            "myvideo_%Y-%m-%d_%H-%M-%S.mp4". Note that the use of this formatting is not mandatory, you can just use
            a normal filename.

        params:
            Dictionary of encoding parameters passed to PyAV. Some useful params:

            "crf":     Sets the constant rate factor for controlling video quality (0=best quality, 51=smallest).
                Example: {"crf": 23}
            "preset":  Sets the encoding preset for balancing speed and compression. Example: {"preset": "ultrafast"}
                (other options: superfast, fast, medium, slow, veryslow)
            "pix_fmt": Sets the pixel format. Example: {"pix_fmt": "yuv420p"}
            "g":       Sets the group of pictures (GOP) size. Example: {"g": 50}

    Environment variables (FILTER_* or legacy VIDEO_OUT_* prefix, legacy takes precedence):
        FILTER_BGR      / VIDEO_OUT_BGR
        FILTER_FPS      / VIDEO_OUT_FPS
        FILTER_SEGTIME  / VIDEO_OUT_SEGTIME
        FILTER_PARAMS   / VIDEO_OUT_PARAMS
    """

    FILTER_TYPE = 'Output'

    @classmethod
    def normalize_config(cls, config):
        outputs = split_commas_maybe(config.get('outputs'))  # we do not assume how Filter will normalize sources/outputs in the future
        config  = VideoOutConfig(super().normalize_config(dict_without(config, 'outputs')))

        if outputs is not None:
            config.outputs = outputs

        if not config.sources:
            raise ValueError('must specify at least one source')
        if not outputs:
            raise ValueError('must specify at least one output')

        for idx, output in enumerate(outputs):
            if isinstance(output, dict):
                if not isinstance(output, VideoOutConfig.Output):
                    outputs[idx] = VideoOutConfig.Output(output)  # because silly user might have passed in dicts

            else:
                output, topic   = Filter.parse_topics(output, 1, False)
                output, options = Filter.parse_options(output)
                outputs[idx]    = VideoOutConfig.Output(output=output, topic=topic and topic[0],
                    options=VideoOutConfig.Output.Options(options))

        for output in outputs:
            if (topic := output.topic) is None:
                output.topic = 'main'
            if not isinstance(options := output.options, VideoOutConfig.Output.Options):
                output.options = options = VideoOutConfig.Output.Options() if options is None else VideoOutConfig.Output.Options(options)
            if isinstance(segtime := options.segtime, str):
                options.segtime = parse_segtime(segtime)

            for option, value in list(options.items()):
                if option not in ('bgr', 'fps', 'segtime', 'params'):
                    options.setdefault('params', {})[option] = value

                    del options[option]

        if not all(is_video_file(o := output.output) or o.startswith('rtsp://') for output in outputs):
            raise ValueError(f'this filter only accepts video file:// and rtsp:// outputs, not {o!r}')

        return config

    def init(self, config):
        super().init(FilterConfig(config, outputs=None))

    def create_videos(self):
        self.tops_n_vids = [(top, VideoWriter(out, **opts)) for top, out, opts in self.tops_n_outs_n_opts]

    def setup(self, config):
        default_options         = {'bgr': config.bgr, 'fps': config.fps, 'segtime': config.segtime}
        default_params          = config.params or {}
        has_src_fps             = False
        self.tops_n_outs_n_opts = tops_n_outs_n_opts = []

        for output in config.outputs:
            topic   = output.get('topic') or 'main'
            options = output.options
            params  = {f'-{p}': v for p, v in {**default_params, **(options.params or {})}.items()}
            options = adict({**default_options, **(options or {}), 'params': params})
            output  = output.output

            if options.fps is None:
                has_src_fps = True

            tops_n_outs_n_opts.append((topic, output, options))

        if has_src_fps:
            self.tops_n_vids = None

            self.process = self.process_src_fps

        else:
            self.process = self.process_check_rtsp_fps

            self.create_videos()

            for _, writer in self.tops_n_vids:
                writer.start()

    def shutdown(self):
        if self.tops_n_vids is not None:
            for _, writer in self.tops_n_vids:
                writer.stop()

    def process_src_fps(self, frames):
        if any(not (f := frames.get(topic := t)) or not f.has_image for t, _, _ in self.tops_n_outs_n_opts):  # don't process until we get all frames
            once(logger.warning, f'video output hold because expected video topic {topic!r} not found or empty among: {", ".join(frames.keys())}', t=60*15)

            return

        for topic, _, options in self.tops_n_outs_n_opts:
            if options.fps is None:
                if (src_fps := (frames[topic].data.get('meta') or {}).get('src_fps')) is not None:
                    options.fps = src_fps

                else:
                    options.fps = True

                    logger.warning(f'topic {topic!r} does not have source fps information, falling back to adaptive fps')

        self.create_videos()

        return self.process_check_rtsp_fps(frames)

    def process_check_rtsp_fps(self, frames):
        if any(not (f := frames.get(topic := t)) or not f.has_image for t, _, _ in self.tops_n_outs_n_opts):  # don't process until we get all frames
            once(logger.warning, f'video output hold because expected video topic {topic!r} not found or empty among: {", ".join(frames.keys())}', t=60*15)

            return

        frames_fpss = set((frame.data.get('meta') or {}).get('src_fps') for frame in frames.values())
        rtsps_fpss  = set(fps for _, out, opts in self.tops_n_outs_n_opts if (fps := opts.fps) is not True and is_video_stream(out))

        if (lf := len(frames_fpss)) > 1 or (lr := len(rtsps_fpss) > 1) or (lf and lr and frames_fpss.pop() != rtsps_fpss.pop()):
            logger.warning(f'multiple sources and/or output RTSP streams with different FPS may cause stuttering and/or incorrect framerates')

        del self.process

        return self.process(frames)

    def process(self, frames):
        for topic, writer in self.tops_n_vids:
            if (frame := frames.get(topic)) is None or (image := frame.bgr.image) is None:
                once(logger.warning, f'expected video topic {topic!r} not found or empty among: {", ".join(frames.keys())}', t=60*15)
            else:
                writer.write(image)


if __name__ == '__main__':
    VideoOut.run()
