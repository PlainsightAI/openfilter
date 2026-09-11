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
from time import sleep, time
from unittest import mock

import cv2
import numpy as np

from openfilter.filter_runtime.filters.video_in import VideoIn, VideoReader, FPS_SANE_CEILING
from openfilter.filter_runtime.utils import setLogLevelGlobal

logger = logging.getLogger(__name__)
setLogLevelGlobal(int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper())))

FPS      = 30
N_FRAMES = 90   # 3 s of source


def _write_video(path: str, n_frames: int = N_FRAMES, fps: int = FPS) -> None:
    """n_frames distinct frames at `fps`, via ffmpeg so the container reports a fixed rate."""
    proc = subprocess.Popen([
        'ffmpeg', '-loglevel', 'error', '-y',
        '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '64x64', '-r', str(fps), '-i', '-',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path,
    ], stdin=subprocess.PIPE)

    for i in range(n_frames):
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


def _reader_reporting_fps(path: str, fps: float, **kwargs) -> VideoReader:
    """Open a real fixture but make cap.get(CAP_PROP_FPS) report `fps` at construction.

    Reproduces a container whose reported rate is the VFR sentinel without having to author
    one; the patch only spans __init__ (which is where the by-index gate reads the rate)."""
    real_get = cv2.VideoCapture.get

    def fake_get(self, prop):
        return fps if prop == cv2.CAP_PROP_FPS else real_get(self, prop)

    with mock.patch.object(cv2.VideoCapture, 'get', fake_get):
        return VideoReader(f'file://{path}', **kwargs)


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
        n, elapsed = _drain(sync=False, maxfps=5, maxfps_by_index=True)

        self.assertEqual(n, N_FRAMES // 6, 'by-index is exact: 1 in every 6 of 90')
        self.assertLess(elapsed, 1.5, 'by-index should read as fast as the decoder allows')

    def test_by_index_keeps_the_first_frame_and_then_every_stride(self):
        """The selection is 1 in ceil(fps / maxfps), starting at the first frame."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'v.mp4')
            _write_video(path)

            vid = VideoReader(f'file://{path}', sync=False, maxfps=5, maxfps_by_index=True)
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

            vid = VideoReader(f'file://{path}', sync=False, maxfps=60, maxfps_by_index=True)

            try:
                self.assertIsNone(vid.index_stride)
            finally:
                vid.cap.release()  # stop() is a no-op without start(); release the cap directly

    def test_by_index_delivers_the_full_selection_with_sync_off_the_default(self):
        """sync=False (the default) + by-index must still deliver every selected frame.

        By-index switches off both clock paths, which are also the only back-pressure on the
        reader. Without the sync_evt handshake the reader outruns the 1-slot deque and drops
        selected frames whenever the consumer is even slightly slow (the reviewer saw 3 of 50).
        A per-frame sleep here makes that race deterministic."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'v.mp4')
            _write_video(path)

            vid = VideoReader(f'file://{path}', sync=False, maxfps=5, maxfps_by_index=True)
            vid.start()

            try:
                self.assertEqual(vid.index_stride, 6)

                frame_ns = []

                while (item := vid.read(with_tframe=True)) is not None:
                    if item[0] is not None:
                        frame_ns.append(item[2]['frame_n'])

                    sleep(0.02)  # a slow-ish consumer, to expose the reader outrunning the deque
            finally:
                vid.stop()

        self.assertEqual(frame_ns, list(range(0, N_FRAMES, 6)))  # 0, 6, ..., 84 - none dropped

    def test_by_index_holds_the_last_frame_when_the_eof_index_is_off_stride(self):
        """The last selected frame must survive even when the phantom EOF index is off-stride.

        read_one calls wait() at EOF to hold the last frame for the consumer; the by-index
        branch used to return before the handshake when that phantom index was off-stride, so
        the (None, ...) sentinel evicted the last frame. 91 frames at stride 6 puts the phantom
        EOF index off-stride ((92 - 1) % 6 != 0), the case the 90-frame fixture hides."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'v.mp4')
            _write_video(path, n_frames=91)

            vid = VideoReader(f'file://{path}', sync=False, maxfps=5, maxfps_by_index=True)
            vid.start()

            try:
                self.assertEqual(vid.index_stride, 6)

                frame_ns = []

                while (item := vid.read(with_tframe=True)) is not None:
                    if item[0] is not None:
                        frame_ns.append(item[2]['frame_n'])

                    sleep(0.02)  # slow consumer so a missed handshake would drop the last frame
            finally:
                vid.stop()

        self.assertEqual(frame_ns, list(range(0, 91, 6)))  # 0, 6, ..., 90 - the last one kept

    def test_by_index_restarts_at_source_zero_on_each_loop(self):
        """Each loop pass must restart the by-index phase at source index 0.

        The reopen resets self.cap but has to reset self.frame_i too, otherwise the stride
        phase carries over and pass two selects from the wrong offset. 92 frames is not a
        multiple of stride 6, so a carried-over phase shows (pass two would start at frame 4);
        the 90-frame fixture hides it because 90 % 6 == 0."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'v.mp4')
            _write_video(path, n_frames=92)

            vid = VideoReader(f'file://{path}', sync=False, maxfps=5, maxfps_by_index=True, loop=2)
            vid.start()

            try:
                self.assertEqual(vid.index_stride, 6)

                frame_ns = []

                while (item := vid.read(with_tframe=True)) is not None:
                    if item[0] is not None:
                        frame_ns.append(item[2]['frame_n'])
            finally:
                vid.stop()

        one_pass = list(range(0, 92, 6))  # 0, 6, ..., 90
        self.assertEqual(frame_ns, one_pass + one_pass)  # both passes select from source index 0

    def test_by_index_no_ops_under_sync_preserving_the_no_skip_guarantee(self):
        """sync=True is documented as "will not skip any frames"; by-index is a sync=False
        optimisation and must no-op under sync=True. Locks in the reviewer's 181 -> 61 drop:
        the by-index count must equal the stock sync=True count, never a subsample."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'v.mp4')
            _write_video(path, n_frames=30)  # 1 s of source, paced at 15/s -> ~2 s per run

            def count(**kwargs):
                vid = VideoReader(f'file://{path}', **kwargs)
                vid.start()

                try:
                    n = 0

                    while vid.read() is not None:
                        n += 1

                    return n, vid.index_stride
                finally:
                    vid.stop()

            stock_n, _         = count(sync=True, maxfps=15)
            by_index_n, stride = count(sync=True, maxfps=15, maxfps_by_index=True)

        self.assertIsNone(stride, 'by-index must not engage under sync=True')
        self.assertEqual(by_index_n, stock_n, 'sync=True must never skip: by-index == stock')
        self.assertEqual(by_index_n, 30, 'all frames delivered under sync=True')

    def test_by_index_no_ops_on_the_fps_sentinel_container(self):
        """A container reporting the >= FPS_SANE_CEILING VFR sentinel must not drive by-index.

        _cap_read already rejects that rate as bogus; the gate must too, otherwise stride is
        ceil(1000 / maxfps) = 200 and 99% of the frames are dropped. Guarding the gate makes
        it fall back to the normal path (index_stride stays None) instead."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'v.mp4')
            _write_video(path)

            vid = _reader_reporting_fps(path, FPS_SANE_CEILING, sync=False, maxfps=5, maxfps_by_index=True)

            try:
                self.assertEqual(vid.native_fps, FPS_SANE_CEILING)  # the reported sentinel rate
                self.assertIsNone(vid.index_stride)                 # by-index no-ops on it
            finally:
                vid.cap.release()

    def test_by_index_logs_the_two_requested_but_no_op_paths(self):
        """The requested-but-no-op paths must not be silent: an operator who set the flag
        fleet-wide needs to know why a pipeline got no speedup. Limited to sync=True and the
        fps sentinel; the frequent, legitimate fps <= maxfps no-op stays quiet."""
        _LOGGER = 'openfilter.filter_runtime.filters.video_in'

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'v.mp4')
            _write_video(path)

            # sync=True: requested, would have engaged, but no-skip is preserved
            with self.assertLogs(_LOGGER, level='INFO') as cm:
                VideoReader(f'file://{path}', sync=True, maxfps=5, maxfps_by_index=True).cap.release()
            self.assertTrue(any('not engaged' in m and 'sync is on' in m for m in cm.output))

            # fps sentinel: requested, sync off, but the reported rate is bogus
            with self.assertLogs(_LOGGER, level='INFO') as cm:
                _reader_reporting_fps(path, FPS_SANE_CEILING, sync=False, maxfps=5, maxfps_by_index=True).cap.release()
            self.assertTrue(any('not engaged' in m and 'sentinel' in m for m in cm.output))

            # fps <= maxfps: a legitimate no-op, must stay quiet about by-index
            with self.assertLogs(_LOGGER, level='INFO') as cm:
                VideoReader(f'file://{path}', sync=False, maxfps=60, maxfps_by_index=True).cap.release()
            self.assertFalse(any('not engaged' in m for m in cm.output))

    def test_by_index_regates_each_file_of_a_mixed_rate_directory(self):
        """A directory's members can report different rates, so the stride is per file.

        The gate runs once in __init__ against dir_files[0]; _open_dir_file re-runs it for
        every subsequent member. Without that the stride of the first file is carried for the
        whole directory and a faster file is delivered above maxfps: 30 fps then 60 fps at
        maxfps=5 keeps stride 6 throughout, so the 60 fps file comes out at 10 fps."""
        with tempfile.TemporaryDirectory() as d:
            _write_video(os.path.join(d, 'a.mp4'), n_frames=30, fps=30)
            _write_video(os.path.join(d, 'b.mp4'), n_frames=60, fps=60)

            vid = VideoReader(f'file://{d}', sync=False, maxfps=5, maxfps_by_index=True)
            vid.start()

            try:
                self.assertEqual(vid.index_stride, 6)  # from a.mp4, 30 fps

                frame_ns = []

                while (item := vid.read(with_tframe=True)) is not None:
                    if item[0] is not None:
                        frame_ns.append(item[2]['frame_n'])
            finally:
                vid.stop()

        # a.mp4 at stride 6, then b.mp4 re-gated to stride 12: both land on 5 fps effective.
        self.assertEqual(frame_ns, list(range(0, 30, 6)) + list(range(0, 60, 12)))

    def test_by_index_restarts_at_source_zero_for_every_file_in_a_directory(self):
        """The by-index phase must not carry across a directory's file boundaries.

        This is the fe89efe loop-reopen fix on the directory path: _open_dir_file resets
        frame_i so each member selects from its own index 0, both on the first pass and on
        every loop pass. The file lengths are deliberately off-stride (10 and 12 against
        stride 6) so a carried-over phase shows as a shifted start."""
        with tempfile.TemporaryDirectory() as d:
            _write_video(os.path.join(d, 'a.mp4'), n_frames=10)
            _write_video(os.path.join(d, 'b.mp4'), n_frames=12)

            vid = VideoReader(f'file://{d}', sync=False, maxfps=5, maxfps_by_index=True)
            vid.start()

            try:
                frame_ns = []

                while (item := vid.read(with_tframe=True)) is not None:
                    if item[0] is not None:
                        frame_ns.append(item[2]['frame_n'])
            finally:
                vid.stop()

        self.assertEqual(frame_ns, [0, 6, 0, 6])  # b.mp4 starts at its own 0, not at 2

    def test_by_index_restarts_at_source_zero_on_each_directory_loop_pass(self):
        """Same reset, exercised through the directory loop-restart branch rather than the
        file-to-file transition: a single-file directory looped twice."""
        with tempfile.TemporaryDirectory() as d:
            _write_video(os.path.join(d, 'a.mp4'), n_frames=10)

            vid = VideoReader(f'file://{d}', sync=False, maxfps=5, maxfps_by_index=True, loop=2)
            vid.start()

            try:
                frame_ns = []

                while (item := vid.read(with_tframe=True)) is not None:
                    if item[0] is not None:
                        frame_ns.append(item[2]['frame_n'])
            finally:
                vid.stop()

        self.assertEqual(frame_ns, [0, 6, 0, 6])  # pass two restarts the phase

    def test_declined_directory_member_keeps_its_own_pacing(self):
        """A member the gate declines must fall back to ITS OWN wall-clock pacing.

        Regression. Once by-index engages on the first member it creates a sync_evt, and the
        code used to read "sync_evt exists" as "sync is on". A declined member then ran the
        sync=True no-skip contract on a sync=False reader: every frame handed downstream,
        paced at maxfps, costing frames/maxfps seconds. Measured by review on a 120-frame
        no-rate member: 1 frame in 2.17 s became 120 frames in 24.21 s.

        Asserted on state rather than wall clock, so it does not flake: after the transition
        the stride is gone AND ns_per_fps is back, which is the pair the bug broke."""
        with tempfile.TemporaryDirectory() as d:
            _write_video(os.path.join(d, 'a.mp4'), n_frames=30, fps=30)   # engages, stride 6
            _write_video(os.path.join(d, 'b.mp4'), n_frames=30, fps=3)    # declined, 3 <= maxfps

            vid = VideoReader(f'file://{d}', sync=False, maxfps=5, maxfps_by_index=True)
            vid.start()

            try:
                self.assertEqual(vid.index_stride, 6)        # a.mp4 engaged
                self.assertIsNotNone(vid.sync_evt)           # and created the handshake

                # Sample the state while the declined member is the open one. Reading to
                # exhaustion is no good: the directory restarts on a.mp4, which re-engages
                # by-index and legitimately nulls ns_per_fps again.
                on_b = None

                while vid.read() is not None:
                    if vid.ssource.endswith('b.mp4') and on_b is None:
                        on_b = (vid.index_stride, vid.ns_per_fps)

                self.assertIsNotNone(on_b, 'never reached the second member')
                stride_on_b, ns_per_fps_on_b = on_b

                self.assertIsNone(stride_on_b)               # b.mp4 declined
                self.assertIsNotNone(
                    ns_per_fps_on_b,
                    'a declined member lost its own pacing: the by-index branch nulls '
                    'ns_per_fps and nothing puts it back once sync_evt exists')
            finally:
                vid.stop()

    def test_src_fps_does_not_flip_across_directory_members(self):
        """meta['src_fps'] must not change between members of one directory.

        Same root cause: _open_dir_file decided the reported rate on `not self.sync_evt`
        while __init__ decides it on `not sync`. With by-index on, the first member reported
        maxfps and every later member reported its native rate, in one stream."""
        with tempfile.TemporaryDirectory() as d:
            _write_video(os.path.join(d, 'a.mp4'), n_frames=30, fps=30)
            _write_video(os.path.join(d, 'b.mp4'), n_frames=30, fps=30)

            vid = VideoReader(f'file://{d}', sync=False, maxfps=5, maxfps_by_index=True)
            vid.start()

            try:
                seen = set()

                while (item := vid.read(with_tframe=True)) is not None:
                    if item[0] is not None:
                        seen.add(item[2].get('src_fps'))
            finally:
                vid.stop()

        self.assertEqual(len(seen), 1, f'src_fps changed mid-directory: {sorted(seen)}')

    def test_a_declined_directory_member_does_not_run_the_sync_contract(self):
        """A member the gate declines must keep sync=False semantics, not gain sync=True ones.

        `wait()` used to select the paced, no-skip branch on `sync_evt is not None`, which was
        equivalent to the sync flag until by-index started creating that event on a sync=False
        reader. From then on a declined member ran the sync=True contract on a sync=False
        reader: handshake plus sleep-to-maxfps with no frame skipping, so it handed the chain
        every one of its frames instead of subsampling, and cost `frames / maxfps` seconds.

        The sentinel member is the case that shows it as a count rather than as a duration:
        declined on its own it contributes nothing, so the directory should deliver only
        a.mp4's 5 sampled frames. Measured on the pre-fix tree this test returns 65 frames in
        12.20 s; fixed it is 5 in 0.08 s.
        """
        with tempfile.TemporaryDirectory() as d:
            _write_video(os.path.join(d, 'a.mp4'), n_frames=30, fps=30)          # engages, stride 6
            _write_video(os.path.join(d, 'b.mp4'), n_frames=60, fps=1000)        # VFR sentinel, declined

            vid = VideoReader(f'file://{d}', sync=False, maxfps=5, maxfps_by_index=True)
            vid.start()

            try:
                t0 = time()
                n  = 0

                while vid.read() is not None:
                    n += 1
            finally:
                vid.stop()

        self.assertEqual(n, 5,
            'the declined member contributed frames: it is running the sync=True no-skip '
            'contract on a sync=False reader')
        # Generous, because the point is the order of magnitude: paced at maxfps the declined
        # member alone would take 60 / 5 = 12 s.
        self.assertLess(time() - t0, 5.0,
            'the declined member was paced at maxfps instead of read as fast as possible')

    def test_option_is_accepted_in_a_source_string(self):
        cfg = VideoIn.normalize_config({
            'id': 'vidin',
            'sources': 'file://x.mp4!sync!maxfps=5!maxfps_by_index',
            'outputs': 'tcp://*',
        })

        self.assertIs(cfg.sources[0].options.maxfps_by_index, True)


if __name__ == '__main__':
    unittest.main()
