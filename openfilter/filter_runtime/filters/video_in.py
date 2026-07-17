import logging
import os
import re
from threading import Condition, Event, Lock, Thread, current_thread
from time import time_ns, sleep
from typing import Any
from urllib.parse import urlparse

import cv2

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    from filter_subject_data_in.video_controller import VideoController as _VideoController
    _HAS_VIDEO_CONTROLLER = True
except ImportError:
    _VideoController = None
    _HAS_VIDEO_CONTROLLER = False

from openfilter.filter_runtime.utils import json_getval, dict_without, split_commas_maybe, hide_uri_users_and_pwds, Deque

__all__ = ['is_video', 'is_video_file', 'is_video_webcam', 'is_video_stream', 'VideoReader', 'MultiVideoReader']

logger = logging.getLogger(__name__)


class _SeekFanout:
    """Fan a single controller seek out to every VideoReader.

    Controllers typically clear the pending seek on the first ``consume_seek()``
    call. With N readers sharing one controller, that leaves N-1 cameras
    unsought. This wrapper records each new target under a generation counter
    so every reader observes it exactly once.
    """

    def __init__(self, inner: Any):
        self.inner = inner
        self._lock = Lock()
        self._gen = 0
        self._target: int | None = None
        self._last_gen: dict[int, int] = {}

    def view(self, reader_id: int) -> '_SeekFanoutView':
        return _SeekFanoutView(self, reader_id)

    def consume_for(self, reader_id: int) -> int | None:
        with self._lock:
            t = self.inner.consume_seek()
            if t is not None:
                self._gen += 1
                self._target = int(t)
            last = self._last_gen.get(reader_id, 0)
            if self._target is not None and last < self._gen:
                self._last_gen[reader_id] = self._gen
                return self._target
            return None


class _SeekFanoutView:
    """Per-reader facade; seek is fanned out, other methods delegate to inner."""

    def __init__(self, shared: _SeekFanout, reader_id: int):
        self._shared = shared
        self._reader_id = reader_id

    def consume_seek(self) -> int | None:
        return self._shared.consume_for(self._reader_id)

    def should_freeze(self) -> bool:
        return self._shared.inner.should_freeze()

    def on_frame_emitted(self, frame_n: int) -> None:
        self._shared.inner.on_frame_emitted(frame_n)

    def __getattr__(self, name: str):
        return getattr(self._shared.inner, name)

VIDEO_IN_BGR      = bool(json_getval((os.getenv('VIDEO_IN_BGR') or os.getenv('FILTER_BGR') or 'true').lower()))
VIDEO_IN_SYNC     = bool(json_getval((os.getenv('VIDEO_IN_SYNC') or os.getenv('FILTER_SYNC') or 'false').lower()))
VIDEO_IN_LOOP     = _ if isinstance(_ := json_getval((os.getenv('VIDEO_IN_LOOP') or os.getenv('FILTER_LOOP') or 'false').lower()), bool) else int(_)
VIDEO_IN_MAXFPS   = None if (_ := json_getval((os.getenv('VIDEO_IN_MAXFPS') or os.getenv('FILTER_MAXFPS') or 'null').lower())) is None else float(_)
VIDEO_IN_MAXSIZE  = os.getenv('VIDEO_IN_MAXSIZE') or os.getenv('FILTER_MAXSIZE') or None
VIDEO_IN_RESIZE   = os.getenv('VIDEO_IN_RESIZE') or os.getenv('FILTER_RESIZE') or None

re_video          = re.compile(r'^(rtsp|rtmp|http|https|file|webcam|s3)://')
re_video_stream   = re.compile(r'^(rtsp|rtmp|http|https)://')

is_video          = lambda name: bool(re_video.match(name))
is_video_file     = lambda name: name.startswith('file://')
is_video_webcam   = lambda name: name.startswith('webcam://')
is_video_stream   = lambda name: bool(re_video_stream.match(name))
is_video_s3       = lambda name: name.startswith('s3://')


re_size = re.compile(r'^\s* (\d+) \s* ([x+]) \s* (\d+) \s* (n(?:ear)? | l(?:in)? | c(?:ub)?)? \s*$', re.VERBOSE | re.IGNORECASE)

def parse_size(s: str):
    if not (m := re_size.match(s)):
        raise ValueError(f'invalid size {s!r}')

    return m.groups()


def parse_s3_uri(s3_uri: str):
    """Parse S3 URI into bucket and key components.
    
    Args:
        s3_uri: S3 URI in format s3://bucket/key
        
    Returns:
        tuple: (bucket, key)
        
    Raises:
        ValueError: If URI format is invalid
    """
    if not s3_uri.startswith('s3://'):
        raise ValueError(f'Invalid S3 URI: {s3_uri}')
    
    parsed = urlparse(s3_uri)
    if not parsed.netloc:
        raise ValueError(f'Invalid S3 URI: {s3_uri} (missing bucket)')
    
    bucket = parsed.netloc
    key = parsed.path.lstrip('/')
    
    if not key:
        raise ValueError(f'Invalid S3 URI: {s3_uri} (missing key)')
    
    return bucket, key


def s3_to_presigned_url(s3_uri: str, expiration: int = 3600, region: str = None):
    """Convert S3 URI to presigned HTTPS URL.
    
    Args:
        s3_uri: S3 URI in format s3://bucket/key
        expiration: URL expiration time in seconds (default: 1 hour)
        region: AWS region (optional, will use default if not specified)
        
    Returns:
        str: HTTPS URL for streaming the S3 object
        
    Raises:
        ValueError: If S3 URI is invalid or boto3 not available
        ClientError: If S3 access fails
        NoCredentialsError: If AWS credentials not configured
    """
    if not HAS_BOTO3:
        raise ValueError('boto3 is required for S3 support. Install with: pip install boto3')
    
    bucket, key = parse_s3_uri(s3_uri)
    
    s3_client = boto3.client('s3', region_name=region)
    
    try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expiration
        )
        return presigned_url
    except NoCredentialsError:
        raise ValueError(
            f'AWS credentials not found for {s3_uri}. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY '
            'environment variables or configure AWS credentials file.'
        )
    except ClientError as e:
        raise ValueError(f'Failed to generate presigned URL for {s3_uri}: {e}')


class VideoReader:
    def __init__(self,
        source:  str,
        cond:    Condition | None = None,
        *,
        bgr:        bool | None = None,
        sync:       bool | None = None,
        loop:       bool | int = False,
        maxfps:     float | None = None,
        maxsize:    str | None = None,
        resize:     str | None = None,
        region:     str | None = None,
        expiration: int | None = None,
        replay_ctrl: Any = None,
    ):
        """Read a single video file, network stream or webcam until the end.

        Args:
            source: Source video stream, can be file, web stream like 'rtsp://...' or a webcam index starting at 0 -
                'webcam://0'.

            cond: A threading.Condition to .notify_all() whenever a new frame is read.

            bgr: True means images in BGR mode, False means RGB. Has env var default.

            sync: Only has meaning for files. If True then frames will be delivered one by one without skipping or
                waiting to maintain realtime, in this way all frames will be read. If None the the system default is
                used which comes from an environment variable (and is False if not present).

            loop: Only has meaning for files. True or 0 means infinite loop, False means loop once, otherwise int loops
                through the video. Has env var default.

            maxsize: Maximum image size to allow, above this will be resized down. Valid codes are '123x456' which will
                proportionally resize maintaining aspect ratio so that neither dimension exceeds the max, '123+456' will
                resize without maintaining aspect ratio. Optional suffixes 'near', 'lin' and 'cub' specify
                interpolation, default is 'near'est neighbor.

            resize: Straight resize always, can not be specified together with `maxsize`, it is one or the other.
        """

        if not isinstance((loop := VIDEO_IN_LOOP if loop is None else loop), (bool, int)) or loop < 0:
            raise ValueError(f"invalid loop '{loop}', must be a bool or nonnegative integer")

        self.source        = hide_uri_users_and_pwds(source)
        self.cond          = cond
        self.loop          = 0 if loop is True else 1 if loop is False else loop
        self.maxfps        = maxfps = VIDEO_IN_MAXFPS if maxfps is None else maxfps
        self.maxsize       = None if (s := VIDEO_IN_MAXSIZE if maxsize is None else maxsize) is None else parse_size(s)
        self.resize        = None if (s := VIDEO_IN_RESIZE if resize is None else resize) is None else parse_size(s)
        self.state         = 0     # 0 = before start, 1 = playing, 2 = stopped / done
        self.sync_evt      = None  # this is set only for file fideo with 'sync' option True
        self.ns_per_fps    = None  # this is set only for file video with 'sync' option False
        self.ns_per_maxfps = None if maxfps is None else 1_000_000_000 // maxfps
        self.is_file       = is_file = is_video_file(source) or is_video_s3(source)
        self.as_bgr        = bool(VIDEO_IN_BGR if bgr is None else bgr)  # only validated after first frame is read (set to False if frames are grayscale)

        if self.maxsize and self.resize:
            raise ValueError(f"can not specify both 'maxsize' and 'resize' together in {self.source!r}")

        if is_file:
            if is_video_file(source):
                source = source[7:]  # Remove 'file://' prefix
            elif is_video_s3(source):
                # Convert S3 URI to presigned HTTPS URL
                logger.info(f"Converting S3 URI to presigned URL: {hide_uri_users_and_pwds(source)}")
                try:
                    s3_expiration = expiration or 3600  # Default 1 hour
                    source = s3_to_presigned_url(source, expiration=s3_expiration, region=region)
                    logger.debug(f"Generated presigned URL for S3 video (region={region}, expiration={s3_expiration}s)")
                except Exception as e:
                    raise ValueError(f'Failed to generate presigned URL for S3 source {self.source!r}: {e}')
            self.is_file = True

            if sync := VIDEO_IN_SYNC if sync is None else sync:
                self.sync_evt = Event()

                self.sync_evt.set()

        else:
            if sync:
                logger.warning(f"'sync' does not apply to videos which are not files in {self.source!r}")

            if is_video_webcam(source):
                source = int(source[9:])
            elif not is_video_stream(source):
                raise ValueError(f'invalid source {self.source!r}')

        self.ssource  = source  # with 'file://' stripped and 'webcam://num' converted to num
        self.stop_evt = Event()
        self.deque    = Deque(maxlen=1)
        self.thread   = Thread(target=self.thread_reader, daemon=True)
        self.cap      = cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise RuntimeError(f'failed to open video source: {self.source!r}')
        fps           = cap.get(cv2.CAP_PROP_FPS) or None

        if is_file and not sync:
            self.ns_per_fps = 1_000_000_000 // (fps or 15)  # cv2 reads files as fast as possible, this is to keep it realtime, default to 15 if video doesn't provide fixed framerate

        self.fps              = fps
        self._replay_ctrl     = replay_ctrl
        self._frame_n         = 0
        self._last_replay_img = None
        self._total_frames    = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if is_file else 0

        if fps is None:
            logger.warning(f'video does not have fixed framerate {self.source!r}{"" if maxfps is None else ", maxfps ignored"}')

            fps_str = ''

        else:
            if maxfps is None or fps <= maxfps:  # maxfps is not None implies (not is_file or not sync) because it would have errored otherwise
                fps_str = f'  ({fps:.1f} fps)'

            else:
                fps_str = f'  ({fps:.1f} fps at {maxfps:.1f} maxfps)'
                fps     = maxfps

                if not is_file or not sync:
                    self.fps = fps

        logger.info(f'video open: {self.source}{fps_str}')

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
        self.tfps  = self.tmaxfps = time_ns()

        self.thread.start()

    def stop(self):  # idempotent and safe to call whenever
        if self.state != 1:
            return

        self.state = 2

        self.stop_evt.set()
        # Unblock thread_reader / read_one waiting on sync_evt.wait()
        if (sync_evt := self.sync_evt) is not None:
            sync_evt.set()
        # Wait for the reader thread to leave cap.read() before releasing
        if self.thread.is_alive() and self.thread is not current_thread():
            self.thread.join(timeout=2.0)
        try:
            self.cap.release()
        except Exception:
            pass

    def read_one(self):
        def wait() -> bool:  # returns if should return frame or keep looping
            t = time_ns()

            if self.is_file:
                if (sync_evt := self.sync_evt) is not None:
                    sync_evt.wait()
                    sync_evt.clear()

                    if (ns_per_maxfps := self.ns_per_maxfps) is not None:  # sleep until we reach maxfps
                        if (tleft := (ns_per_maxfps - ((t := time_ns()) - (tmaxfps := self.tmaxfps)))) > 0:
                            sleep(tleft / 1_000_000_000)

                            t = tmaxfps + ns_per_maxfps

                        self.tmaxfps = t

                    return True

                if (tleft := ((ns_per_fps := self.ns_per_fps) - (t - (tfps := self.tfps)))) > 0:  # cap video file to maximum of its specified fps
                    sleep(tleft / 1_000_000_000)

                    t = tfps + ns_per_fps

                self.tfps = t

            if (ns_per_maxfps := self.ns_per_maxfps) is not None:  # skip frames until we reach maxfps, keep remainder, if more than one frame over then discard extra time
                if (tdiff := t - (tmaxfps := self.tmaxfps)) < ns_per_maxfps:
                    return False

                self.tmaxfps = tmaxfps + (tdiff // ns_per_maxfps) * ns_per_maxfps

            return True

        while True:
            ret, image = self.cap.read()

            if not ret or image is None:
                if not self.is_file:
                    return None

                # We do the wait()s below in order to maintain the last frame for the same amount of time as others
                # because otherwise cv2 returns (False, None) immediately after the last frame has been read from a
                # file which does not allow enough time for the last frame to be picked up, thus losing it. The last
                # frame may be lost on a realtime video if it takes too long to query it but it will never be lost on
                # a `sync` video.

                if loop := self.loop:
                    self.loop = loop - 1

                    if not self.loop:
                        wait()

                        return None

                try:
                    logger.info(f'video loop: {self.source}{f"  (last loop)" if loop == 2 else f"  ({self.loop} left)" if loop else ""}')

                    self.cap.release()
                    self.cap = cv2.VideoCapture(self.ssource)
                    if not self.cap.isOpened():
                        raise RuntimeError(f'failed to reopen video source: {self.source!r}')

                except Exception:
                    wait()

                    return None

                ret, image = self.cap.read()

                if not ret or image is None:  # no wait() here because if first frame fails then nothing means anything anymore and we might as well just end it
                    return None

            if wait():
                break

        return image

    def _seek_accurate(self, target_frame: int) -> int:
        """Seek to target_frame with I-frame compensation (reads forward from nearest I-frame).

        Clamps to ``[0, total_frames-1]`` when frame count is known so scrubbing
        past EOF lands on the last frame instead of ending the pipeline.

        Returns the effective frame index the capture is positioned to decode next
        (may be < requested target if OpenCV undershoots / hits EOF early).
        """
        if self._total_frames > 0:
            target_frame = max(0, min(int(target_frame), self._total_frames - 1))
        else:
            target_frame = max(0, int(target_frame))

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        actual = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        while actual < target_frame:
            ret, _ = self.cap.read()
            if not ret:
                break
            actual += 1

        if actual < target_frame:
            # EOF during forward-read — land on the last decodable index
            landed = max(actual - 1, 0)
            logger.warning(
                'VideoIn seek: requested/clamped target %s undershot at %s; '
                'clamping to frame %s',
                target_frame, actual, landed,
            )
            if landed > 0 or actual == 0:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, landed)
            self._frame_n = landed
            return landed

        self._frame_n = target_frame
        return target_frame

    def thread_reader(self):
        cond  = self.cond
        ctrl  = self._replay_ctrl

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
                cv2.INTER_NEAREST
            )

        _just_seeked       = False
        _seek_target_frame = None

        while True:
            # ----------------------------------------------------------------
            # Replay: check for a pending seek command (highest priority)
            # ----------------------------------------------------------------
            if ctrl is not None:
                seek_target = ctrl.consume_seek()
                if seek_target is not None:
                    self._seek_accurate(seek_target)
                    _just_seeked       = True
                    _seek_target_frame = seek_target

            # ----------------------------------------------------------------
            # Replay: freeze-frame (paused) – re-emit the last image unchanged
            # Exception: if a seek just happened, fall through to read() once
            # so _last_replay_img is updated to the seek-target frame first.
            # ----------------------------------------------------------------
            if ctrl is not None and ctrl.should_freeze() and not _just_seeked:
                if self.stop_evt.is_set():
                    self.deque.append((None, time_ns(), {}))
                    if cond is not None:
                        with cond:
                            cond.notify_all()
                    break
                if self._last_replay_img is not None:
                    freeze_extras = {'frame_n': self._frame_n, 'frame_repeat': True}
                    tframe        = time_ns()
                    self.deque.append((self._last_replay_img, tframe, freeze_extras))
                    if cond is not None:
                        with cond:
                            cond.notify_all()
                    # Throttle to the natural frame rate to avoid spinning
                    if (sync_evt := self.sync_evt) is not None:
                        sync_evt.wait()
                        sync_evt.clear()
                    else:
                        ns = self.ns_per_fps or self.ns_per_maxfps or 40_000_000
                        sleep(ns / 1_000_000_000)
                else:
                    sleep(0.04)
                continue

            # ----------------------------------------------------------------
            # Normal read
            # ----------------------------------------------------------------
            image  = None if self.stop_evt.is_set() else self.read_one()
            tframe = time_ns()

            # After a seek near EOF, OpenCV may return no frame — clamp by
            # re-emitting the last decoded image (or a re-seek to last frame)
            # so scrubbing to the end does not kill the pipeline.
            if image is None and _just_seeked and not self.stop_evt.is_set():
                if self._total_frames > 0:
                    self._seek_accurate(self._total_frames - 1)
                    image = self.read_one()
                if image is None and self._last_replay_img is not None:
                    image = self._last_replay_img
                    # Keep seek_reset semantics using the clamped _frame_n
                    replay_extras = {
                        'frame_n': self._frame_n,
                        'seek_reset': True,
                        'seek_frame_index': self._frame_n,
                    }
                    self.deque.append((image, tframe, replay_extras))
                    if cond is not None:
                        with cond:
                            cond.notify_all()
                    if ctrl is not None:
                        ctrl.on_frame_emitted(self._frame_n)
                    _just_seeked = False
                    _seek_target_frame = None
                    continue

            replay_extras: dict = {}

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

                if len(shape) != 3:
                    self.as_bgr = False  # because not validated on init
                elif not self.as_bgr:
                    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

                # ---- replay metadata injection ----
                if ctrl is not None:
                    # cap.get(POS_FRAMES) points to the NEXT frame to be read, so -1
                    frame_n = max(int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1, 0)
                    self._frame_n         = frame_n
                    self._last_replay_img = image
                    replay_extras         = {'frame_n': frame_n}
                    if _just_seeked:
                        # Keep frame_index and seek_frame_index identical on the
                        # first post-seek frame. Prefer the actual decoded position
                        # when OpenCV undershoots the requested target.
                        if (
                            _seek_target_frame is not None
                            and frame_n != _seek_target_frame
                        ):
                            logger.warning(
                                'VideoIn seek: requested frame %s but decoded '
                                'position is %s; emitting seek_frame_index=%s '
                                'to match frame_index',
                                _seek_target_frame, frame_n, frame_n,
                            )
                        replay_extras['seek_reset']       = True
                        replay_extras['seek_frame_index'] = frame_n
                        _just_seeked       = False
                        _seek_target_frame = None
                    ctrl.on_frame_emitted(frame_n)

            self.deque.append((image, tframe, replay_extras))

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

    def read(self, with_tframe=False):  # -> np.ndarray | tuple[np.ndarray, int, dict] | None
        if self.state == 0:
            raise RuntimeError('can not read from video before it is started')
        elif self.state == 2:
            return None

        if (item := self.deque.popleft()) is None:
            self.state = 2

            self.cap.release()

            return None

        if (sync_evt := self.sync_evt) is not None:
            sync_evt.set()

        if with_tframe:
            # item is always (image, tframe, extras) now; extras may be empty dict
            return item
        return item[0]

    @staticmethod
    def get_info(source: str) -> tuple[int, int, str, float]:  # (height, width, format, fps)
        cap = cv2.VideoCapture(int(source[9:]) if is_video_webcam(source) else source[7:] if is_video_file(source) else source)

        try:
            ret, image = cap.read()

            if not ret:
                raise RuntimeError('failed to read a frame')

            width  = image.shape[1]
            height = image.shape[0]
            fps    = cap.get(cv2.CAP_PROP_FPS)
            is_bgr = cap.get(cv2.CAP_PROP_CONVERT_RGB)
            format = 'GRAY' if len(image.shape) == 2 else 'BGR' if is_bgr else 'RGB'

            return height, width, format, fps

        finally:
            cap.release()


class MultiVideoReader:
    """Read multiple videos simultaneously returning time-synchronized frames until one of them is exhausted."""

    def __init__(self, sources: list[str], sources_kwargs: list[dict[str, Any]] | None = None):
        kwargss     = [{}] * len(sources) if sources_kwargs is None else sources_kwargs
        self.cond   = cond = Condition()
        self.videos = [VideoReader(source, cond, **kwargs) for source, kwargs in zip(sources, kwargss)]
        self.state  = 0  # 0 = before start, 1 = playing, 2 = stopped / done

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

        for video in self.videos:
            video.start()

    def stop(self):  # idempotent and safe to call whenever
        if self.state != 1:
            return

        self.state = 2

        for video in self.videos:
            video.stop()

    @property
    def playing(self) -> bool:
        return self.state == 1

    @property
    def stopped(self) -> bool:
        return self.state == 2

    @property
    def frame_available(self) -> bool:
        return all(vid.frame_available for vid in self.videos)

    def read(self, with_tframe=False):  # -> list[np.ndarray | tuple[np.ndarray, int, dict]] | None
        if self.state == 0:
            raise RuntimeError('can not read from videos before they are started')
        elif self.state == 2:
            return None

        cond   = self.cond
        videos = self.videos

        while not all(video.frame_available for video in videos):
            with cond:
                cond.wait()

        items = [video.read(with_tframe) for video in videos]

        # item is None when state==2, or (None, tframe, extras) when video ended
        if any(
            item is None or (with_tframe and item[0] is None)
            for item in items
        ):
            self.stop()
            return None

        return items


# --- CUT HERE ---------------------------------------------------------------------------------------------------------

from openfilter.filter_runtime.filter import is_cached_file, Frame, FilterConfig, Filter
from openfilter.filter_runtime.utils import adict, split_commas_maybe

__all__ = __all__ + ['VideoInConfig', 'VideoIn']

is_video_or_cached_file = lambda s: is_video(s) or is_cached_file(s)


class VideoInConfig(FilterConfig):
    class Source(adict):
        class Options(adict):
            bgr:        bool | None
            sync:       bool | None
            loop:       bool | int | None
            maxfps:     float | None
            maxsize:    str | None
            resize:     str | None
            region:     str | None
            expiration: int | None

        source:  str
        topic:   str | None
        options: Options | None

    sources: str | list[str | Source]

    # setting these here will make them default for all videos (overridable individually)
    bgr:     bool | None
    sync:    bool | None
    loop:    bool | int | None
    maxfps:  float | None
    maxsize: str | None
    resize:  str | None

    # ---- seekable replay control (optional) ----
    # When control_port is set, VideoIn starts an HTTP replay API (pause/play/seek/step)
    # via VideoController (from filter_subject_data_in) and injects replay sync metadata
    # (frame_index / frame_repeat / seek_*) into every Frame.meta.
    #
    # IMPORTANT: only FilterSubjectDataIn with sync_key='sequential' consumes these
    # signals today. Other sync_key modes (e.g. 'ts') ignore them — see the Replay
    # Sync Meta Spec in the class docstring.
    #
    # Env vars (legacy VIDEO_IN_* takes precedence over FILTER_*):
    #   VIDEO_IN_CONTROL_PORT / FILTER_CONTROL_PORT
    #   VIDEO_IN_SDI_URL      / FILTER_SDI_URL
    #   VIDEO_IN_WEBVIS_URL   / FILTER_WEBVIS_URL
    #   VIDEO_IN_WEBVIS_TOPIC / FILTER_WEBVIS_TOPIC
    control_port: int | None
    sdi_url:      str | None
    webvis_url:   str | None
    webvis_topic: str | None


class VideoIn(Filter):
    """Single or multiple video input filter. Videos are assigned to topics via the ';' mapping character in `sources`.
    The default topic mapping if nothing specified is 'main'. All video sources must have unique topics. '!' allows
    setting options directly in the source string.

    config:
        sources:
            The source(s) of the video(s), comma delimited, can be file://, rtsp:// stream, s3:// bucket object, 
            or a webcam:// index.

            Examples:
                'file://a.mp4!sync!loop=3, rtsp://b.com!no-bgr;c, s3://bucket/video.mp4!region=us-west-2, webcam://0;e'

                    is the same as

                ['file://a.mp4!sync!loop=3', 'rtsp://b.com!no-bgr;c', 's3://bucket/video.mp4!region=us-west-2', 'webcam://0;e']

                    is the same as

                [{'source': 'file://a.mp4', 'topic': 'main', 'options': {'sync': True, 'loop': 3}},
                 {'source': 'rtsp://b.com', 'topic': 'c', 'options': {'bgr': False}},
                 {'source': 's3://bucket/video.mp4', 'topic': 'main', 'options': {'region': 'us-west-2'}},
                 {'source': 'webcam://0', 'topic': 'e', 'options': {}}]

                    For 'options' see below.

            `sources` individual options (text appended after source, e.g. 'file:///myvideo.mp4!no-bgr!sync!loop=3'):
                '!bgr', '!no-bgr':
                    Set `bgr` option for this source.

                '!sync', '!no-sync':
                    Set `sync` option for this source.

                '!loop', '!no-loop', '!loop=3':
                    Set `loop` option for this source.

                '!maxfps=10':
                    Set `maxfps` option for this source.

                '!maxsize=1280x720', '!maxsize=1280+720C':
                    Set `maxsize` option for this source.

                '!resize=1280x720lin', '!resize=1280+720':
                    Set `resize` option for this source.

                '!region=us-west-2':
                    Set AWS region for S3 sources. Only applies to s3:// sources.

                '!expiration=7200':
                    Set presigned URL expiration time in seconds for S3 sources. Default is 3600 (1 hour).
                    Only applies to s3:// sources.

        bgr:
            True means images in BGR format, False means RGB. Doesn't really affect anythong other than procesing speed
            since images should always be converted to the needed format. Don't touch this unless you have an explicit
            need and understanding of why you need to change it. Set here to apply to all sources or can be set
            individually per source. Global env var default FILTER_BGR / VIDEO_IN_BGR.

        sync:
            Only has meaning for file:// sources. If True then frames will be delivered one by one without skipping or
            waiting to maintain realtime, in this way all frames will be read and presented. Set here to apply to all
            sources or can be set individually per source. Global env var default FILTER_SYNC / VIDEO_IN_SYNC.

            NOTE: When a file source is read in `sync` mode, the original fps is passed downstream so that any video
            created from this file will have the original framerate regardless of the potential slowness of the
            processing applied to it. This is intended for offline processing of all frames of a video at the maximum
            speed possible while maintaining original video framerate.

        loop:
            Only has meaning for file:// sources. True or 0 means infinite loop, False means don't loop and go through
            the video only once, otherwise an int value loops through the video that number of times. Set here to apply
            to all sources or can be set individually per source. Global env var default FILTER_LOOP / VIDEO_IN_LOOP.

        maxfps:
            Restrict video to this FPS. Works for all types of video and if playing a file:// video in `sync` mode then
            will present the individual frames at this frame rate but will not skip any frames. Set here to apply to
            all sources or can be set individually per source. Global env var default FILTER_MAXFPS / VIDEO_IN_MAXFPS.

        maxsize:
            Maximum image size to allow, above this will be resized down. Valid codes are 'WxH' which will
            proportionally resize maintaining aspect ratio so that neither dimension exceeds the max, 'W+H' will resize
            without maintaining aspect ratio. Optional suffixes 'near', 'lin' and 'cub' specify interpolation, default
            is 'near'est neighbor. Set here to apply to all sources or can be set individually per source. Global env
            var default FILTER_MAXSIZE / VIDEO_IN_MAXSIZE.

        resize:
            Same as `maxsize` but is always applied unconditionally regardless of input size.Can not be specified
            together with `maxsize`, it is one or the other. Set here to apply to all sources or can be set individually
            per source. Global env var default FILTER_RESIZE / VIDEO_IN_RESIZE.

    Environment variables (FILTER_* or legacy VIDEO_IN_* prefix, legacy takes precedence):
        FILTER_BGR           / VIDEO_IN_BGR
        FILTER_SYNC          / VIDEO_IN_SYNC
        FILTER_LOOP          / VIDEO_IN_LOOP
        FILTER_MAXFPS        / VIDEO_IN_MAXFPS
        FILTER_MAXSIZE       / VIDEO_IN_MAXSIZE
        FILTER_RESIZE        / VIDEO_IN_RESIZE
        FILTER_CONTROL_PORT  / VIDEO_IN_CONTROL_PORT
        FILTER_SDI_URL       / VIDEO_IN_SDI_URL
        FILTER_WEBVIS_URL    / VIDEO_IN_WEBVIS_URL
        FILTER_WEBVIS_TOPIC  / VIDEO_IN_WEBVIS_TOPIC

    S3 Configuration:
        For s3:// sources, AWS credentials are required. Set these environment variables:
        
        AWS_ACCESS_KEY_ID - Your AWS access key ID
        AWS_SECRET_ACCESS_KEY - Your AWS secret access key  
        AWS_DEFAULT_REGION - Default AWS region (optional, can be overridden per source)
        AWS_PROFILE - AWS credentials profile to use (alternative to access keys)
        
        S3 sources are converted to presigned HTTPS URLs and streamed directly without local storage.
        
        Example S3 usage:
            openfilter run - VideoIn --sources s3://my-bucket/video.mp4!region=us-west-2 - Webvis

    Seekable Replay API (requires filter_subject_data_in package):
        When `control_port` is set, VideoIn wires a VideoController HTTP server
        (pause/play/step/seek + HTML player). HTTP/UI lives in that package so VideoIn
        stays focused on frame production; seek/freeze still run inside VideoReader
        because they gate which frames enter the deque.

        If `control_port` is set but filter_subject_data_in is not installed, setup()
        raises RuntimeError (fail loud — the operator explicitly requested controls).

        Frame.meta keys (always present when control_port is active):

            meta['id']                 - monotonic emit counter (pipeline order; NOT file position)
            meta['ts']                 - wall-clock emit time in seconds (NOT video-relative)
            meta['frame_index']        - 0-based position in the video file (trust this for sync)
            meta['total_frames']       - total frames in the video file

        Replay Sync Meta Spec v1 (emitted only when control_port is active):

            meta['frame_repeat']       - True on every re-emitted frozen frame while paused
            meta['seek_reset']         - True on the first frame after a seek
            meta['seek_frame_index']   - actual decoded frame index of that seek (always == frame_index
                                         on the seek_reset frame)
            meta['seek_ts']            - seek_frame_index / src_fps (seconds)

        Downstream consumers:
            FilterSubjectDataIn sync_key='sequential' — honors frame_repeat / seek_reset /
                seek_frame_index (cursor freeze / jump).
            FilterSubjectDataIn sync_key='ts' (and any other mode) — ignores these signals;
                do not use interactive seek/pause with those modes if sync must hold.
            Any third-party filter — may rely on Replay Sync Meta Spec v1 keys above.

        HTTP endpoints (served by VideoController on control_port):
            POST /pause
            POST /play
            POST /step?frames=N
            POST /seek?frame=N  |  POST /seek?ts=12.345
            GET  /status
            GET  /video          (streams the local MP4; single-source only)
            GET  /player         (HTML5 browser player with scrubber + overlay)

        Config / env vars (VIDEO_IN_* takes precedence over FILTER_*):
            control_port  / VIDEO_IN_CONTROL_PORT  / FILTER_CONTROL_PORT
            sdi_url       / VIDEO_IN_SDI_URL       / FILTER_SDI_URL
            webvis_url    / VIDEO_IN_WEBVIS_URL    / FILTER_WEBVIS_URL
            webvis_topic  / VIDEO_IN_WEBVIS_TOPIC  / FILTER_WEBVIS_TOPIC
    """

    FILTER_TYPE = 'Input'

    @classmethod
    def normalize_config(cls, config):
        sources = split_commas_maybe(config.get('sources'))  # we do not assume how Filter will normalize sources/outputs in the future
        config  = VideoInConfig(super().normalize_config(dict_without(config, 'sources')))

        if sources is not None:
            config.sources = sources

        if not sources:
            raise ValueError('must specify at least one source')
        if not config.outputs:
            raise ValueError('must specify at least one output')

        # ---- replay control env var defaults ----
        # Dual-prefix convention: VIDEO_IN_* (legacy) takes precedence over FILTER_*.
        # Also accept FILTER_VIDEO_* as a transitional alias.
        if config.control_port is None:
            _env = (
                os.getenv('VIDEO_IN_CONTROL_PORT')
                or os.getenv('FILTER_CONTROL_PORT')
                or os.getenv('FILTER_VIDEO_CONTROL_PORT')
            )
            config.control_port = int(_env) if _env else None
        if config.sdi_url is None:
            config.sdi_url = (
                os.getenv('VIDEO_IN_SDI_URL')
                or os.getenv('FILTER_SDI_URL')
                or os.getenv('FILTER_VIDEO_SDI_URL')
                or 'http://localhost:8090'
            )
        if config.webvis_url is None:
            config.webvis_url = (
                os.getenv('VIDEO_IN_WEBVIS_URL')
                or os.getenv('FILTER_WEBVIS_URL')
                or os.getenv('FILTER_VIDEO_WEBVIS_URL')
                or 'http://localhost:8000'
            )
        if config.webvis_topic is None:
            config.webvis_topic = (
                os.getenv('VIDEO_IN_WEBVIS_TOPIC')
                or os.getenv('FILTER_WEBVIS_TOPIC')
                or os.getenv('FILTER_VIDEO_WEBVIS_TOPIC')
                or 'viz'
            )

        for idx, source in enumerate(sources):
            if isinstance(source, dict):
                if not isinstance(source, VideoInConfig.Source):
                    sources[idx] = VideoInConfig.Source(source)  # because silly user might have passed in dicts

            else:
                source, topic   = Filter.parse_topics(source, 1, False)
                source, options = Filter.parse_options(source)
                sources[idx]    = VideoInConfig.Source(source=source, topic=topic and topic[0],
                    options=VideoInConfig.Source.Options(options))

        for source in sources:
            if (topic := source.topic) is None:
                source.topic = 'main'
            if not isinstance(options := source.options, VideoInConfig.Source.Options):
                source.options = options = VideoInConfig.Source.Options() if options is None else VideoInConfig.Source.Options(options)
            if any((option := o) not in ('bgr', 'sync', 'loop', 'maxfps', 'maxsize', 'resize', 'region', 'expiration') for o in options):
                raise ValueError(f'unknown option {option!r} in {source!r}')

        if len(set(source.topic for source in sources)) != len(sources):
            raise ValueError(f'duplicate video topics in {sources!r}')
        if not all(is_video_or_cached_file(source.source) for source in sources):
            raise ValueError('this filter only accepts video sources')

        return config

    def init(self, config):
        super().init(FilterConfig(config, sources=None))

    def setup(self, config):
        vsources = []
        topics   = []
        optionss = []

        for source in config.sources:
            vsources.append(source.source)
            topics.append(source.topic or 'main')
            optionss.append(source.options or {})

        default_options  = {'bgr': config.bgr, 'sync': config.sync, 'loop': config.loop, 'maxfps': config.maxfps,
            'maxsize': config.maxsize, 'resize': config.resize}
        self.mvreader    = MultiVideoReader(vsources, [{**default_options, **options} for options in optionss])
        self.tops_n_vids = tuple(zip(topics, self.mvreader.videos))
        self.id          = -1  # frame id
        self._camera_connected = 0

        # ---- seekable replay controller (optional) ----
        self._replay_ctrl = None
        if config.control_port:
            if not _HAS_VIDEO_CONTROLLER:
                raise RuntimeError(
                    f'VideoIn: control_port={config.control_port} was set but '
                    'filter_subject_data_in is not installed — refusing to start '
                    'without the requested replay API. Install with: '
                    'pip install filter-subject-data-in'
                )
            # Use the first video as the canonical source for the controller
            primary_vid  = self.mvreader.videos[0]
            primary_src  = config.sources[0].source
            local_path   = primary_src.replace('file://', '') if primary_src.startswith('file://') else None
            if local_path and not os.path.isfile(local_path):
                local_path = None

            ctrl = _VideoController(
                total_frames=primary_vid._total_frames,
                fps=primary_vid.fps or 30.0,
                source=primary_src,
                local_path=local_path,
            )
            ctrl.start_server(
                config.control_port,
                sdi_url=config.sdi_url,
                webvis_url=config.webvis_url,
                webvis_topic=config.webvis_topic,
            )
            self._replay_ctrl = ctrl

            # Fan each seek out to every reader (consume_seek is read-and-clear
            # on the underlying controller — without this only one camera seeks).
            fanout = _SeekFanout(ctrl)
            for i, vid in enumerate(self.mvreader.videos):
                vid._replay_ctrl = fanout.view(i)

            logger.info(
                'VideoIn: seekable replay API on port %s  player=http://localhost:%s/player',
                config.control_port, config.control_port,
            )

        self.mvreader.start()

    def shutdown(self):
        ctrl = getattr(self, '_replay_ctrl', None)
        if ctrl is not None:
            # Quiesce freeze/seek before joining reader threads
            play = getattr(ctrl, 'play', None)
            if callable(play):
                try:
                    play()
                except Exception:
                    pass
            stop_server = getattr(ctrl, 'stop_server', None)
            if callable(stop_server):
                try:
                    stop_server()
                except Exception:
                    pass
        self.mvreader.stop()
        if ctrl is not None:
            self._replay_ctrl = None

    def process(self, frames):
        ctrl = getattr(self, '_replay_ctrl', None)

        def get():
            if (items := self.mvreader.read(True)) is None:
                self._camera_connected = 0
                self.exit('video ended')
                return None

            self._camera_connected = 1
            self.id = id = self.id + 1

            result = {}
            for (topic, vid), item in zip(self.tops_n_vids, items):
                img, tfrm, extras = item  # always (image, tframe, extras) since thread_reader change

                meta = {
                    'id':      id,
                    'ts':      tfrm / 1_000_000_000,
                    'src':     vid.source,
                    'src_fps': vid.fps,
                }

                if ctrl is not None and extras:
                    frame_n = extras.get('frame_n', 0)
                    meta['frame_index']  = frame_n
                    meta['total_frames'] = vid._total_frames
                    if extras.get('frame_repeat'):
                        meta['frame_repeat'] = True
                    if extras.get('seek_reset'):
                        meta['seek_reset']       = True
                        meta['seek_ts']          = frame_n / (vid.fps or 30.0)
                        meta['seek_frame_index'] = extras.get('seek_frame_index', frame_n)

                result[topic] = Frame(
                    img,
                    {'meta': meta},
                    'GRAY' if len(img.shape) == 2 else 'BGR' if vid.as_bgr else 'RGB',
                )

            return result

        return get


if __name__ == '__main__':
    VideoIn.run()
