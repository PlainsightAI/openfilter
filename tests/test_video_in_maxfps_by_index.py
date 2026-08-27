#!/usr/bin/env python

"""maxfps applied from the source timeline instead of from the wall clock.

By default maxfps limits how many frames are delivered per second of real time, so an
hour of file costs an hour of wall clock no matter how fast the machine is. That is right
for anything tracking real time and wrong for offline processing of a recording, where
the same selection should come off the source timeline and be read as fast as possible.
"""

import logging
import os
import subprocess
import tempfile
import unittest
from time import time

import numpy as np

from openfilter.filter_runtime.filters.video_in import VideoIn, VideoReader
from openfilter.filter_runtime.utils import setLogLevelGlobal

logger = logging.getLogger(__name__)
setLogLevelGlobal(int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper())))

FPS      = 30
N_FRAMES = 90   # 3 s of source


def _write_video(path: str) -> None:
    """90 distinct frames at 30 fps, via ffmpeg so the container reports a fixed rate."""
    proc = subprocess.Popen([
        'ffmpeg', '-loglevel', 'error', '-y',
        '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '64x64', '-r', str(FPS), '-i', '-',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path,
    ], stdin=subprocess.PIPE)

    for i in range(N_FRAMES):
        proc.stdin.write(np.full((64, 64, 3), i * 2 % 256, dtype=np.uint8).tobytes())

    proc.stdin.close()
    proc.wait()


def _drain(**kwargs) -> tuple[int, float]:
    """Read a video to exhaustion, returning how many frames came out and how long it took."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'v.mp4')
        _write_video(path)

        vid = VideoReader(f'file://{path}', **kwargs)
        vid.start()

        try:
            t0 = time()
            n  = 0

            while vid.read() is not None:
                n += 1

            return n, time() - t0

        finally:
            vid.stop()


@unittest.skipUnless(
    subprocess.run(['which', 'ffmpeg'], capture_output=True).returncode == 0,
    'ffmpeg needed to author the fixture',
)
class TestMaxfpsByIndex(unittest.TestCase):
    def test_off_by_default_so_maxfps_still_paces_the_read(self):
        """3 s of source capped to 5 fps: about 15 frames, spread over ~3 s of real time.

        The count is approximate on purpose. Selecting against the wall clock cannot be
        exact, which is the other half of what by-index fixes."""
        n, elapsed = _drain(sync=False, maxfps=5)

        self.assertGreaterEqual(n, 13)
        self.assertLessEqual(n, 16)
        self.assertGreater(elapsed, 2.0, 'default maxfps should still be bound to real time')

    def test_by_index_selects_the_same_frames_without_waiting(self):
        n, elapsed = _drain(sync=True, maxfps=5, maxfps_by_index=True)

        self.assertEqual(n, N_FRAMES // 6, 'by-index is exact: 1 in every 6 of 90')
        self.assertLess(elapsed, 1.5, 'by-index should read as fast as the decoder allows')

    def test_by_index_keeps_the_first_frame_and_then_every_stride(self):
        """The selection is 1 in round(fps / maxfps), starting at the first frame."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'v.mp4')
            _write_video(path)

            vid = VideoReader(f'file://{path}', sync=True, maxfps=5, maxfps_by_index=True)
            vid.start()

            try:
                self.assertEqual(vid.index_stride, 6)

                frame_ns = []

                while (item := vid.read(with_tframe=True)) is not None:
                    frame_ns.append(item[2]['frame_n'])

            finally:
                vid.stop()

        self.assertEqual(frame_ns[:4], [0, 6, 12, 18])

    def test_ignored_when_maxfps_is_not_below_the_source_rate(self):
        """Nothing to drop, so the reader stays on its normal path."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'v.mp4')
            _write_video(path)

            vid = VideoReader(f'file://{path}', sync=True, maxfps=60, maxfps_by_index=True)

            try:
                self.assertIsNone(vid.index_stride)
            finally:
                vid.stop()

    def test_option_is_accepted_in_a_source_string(self):
        cfg = VideoIn.normalize_config({
            'id': 'vidin',
            'sources': 'file://x.mp4!sync!maxfps=5!maxfps_by_index',
            'outputs': 'tcp://*',
        })

        self.assertIs(cfg.sources[0].options.maxfps_by_index, True)


if __name__ == '__main__':
    unittest.main()
