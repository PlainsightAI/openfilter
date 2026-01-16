#!/usr/bin/env python

import logging
import multiprocessing as mp
import os
import shutil
import subprocess
import unittest

from openfilter.filter_runtime import Filter, Frame
from openfilter.filter_runtime.test import QueueToFilters
from openfilter.filter_runtime.utils import setLogLevelGlobal
from openfilter.filter_runtime.filters.video_out import VideoOut, VideoOutConfig, VideoWriter

import cv2
import numpy as np

logger = logging.getLogger(__name__)

log_level = int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper()))

setLogLevelGlobal(log_level)

try:  # if not present then internal vidgear writer is used which has different output
    subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    FFMPEG = True
except Exception:
    FFMPEG = False

TEST_DIR            = 'test_video'
TEST_VIDEO_FNM      = 'test_video.mp4'
TEST_VIDEO_PATH     = os.path.join(TEST_DIR, TEST_VIDEO_FNM)

# BGR is in effect
RED_IMAGE           = np.tile(np.array([0, 0, 255], np.uint8), (200, 320, 1))
GREEN_IMAGE         = np.tile(np.array([0, 255, 0], np.uint8), (200, 320, 1))
BLUE_IMAGE          = np.tile(np.array([255, 0, 0], np.uint8), (200, 320, 1))

is_image_very_red   = lambda img: np.mean(img, axis=(0, 1)).dot((0, 0, 255)) >= 0xdfff
is_image_very_green = lambda img: np.mean(img, axis=(0, 1)).dot((0, 255, 0)) >= 0xdfff
is_image_very_blue  = lambda img: np.mean(img, axis=(0, 1)).dot((255, 0, 0)) >= 0xdfff


def read_video(fnm) -> tuple[float, list[np.ndarray]]:  # (fps, frames)
    cap    = cv2.VideoCapture(fnm)
    images = []

    try:
        while True:
            res, image = cap.read()

            if image is None:
                break
            elif not res:
                raise RuntimeError(f'failed to read video {fnm!r}')

            images.append(image)

        return (cap.get(cv2.CAP_PROP_FPS), images)

    finally:
        cap.release()


class TestVideoOut(unittest.TestCase):
    def test_normalize_config(self):
        scfg  = dict(id='vidout', sources='tcp://localhost', outputs='file://out1.mkv!bgr, file://out2_%Y%m%d_%H%M%S.mp4!fps=15!segtime=1;other, rtsp://host:1234/path!fps=true!g=30;yet_another')
        dcfg  = VideoOutConfig({'id': 'vidout', 'sources': ['tcp://localhost'], 'outputs': [
            {'output': 'file://out1.mkv', 'topic': 'main', 'options': {'bgr': True}},
            {'output': 'file://out2_%Y%m%d_%H%M%S.mp4', 'topic': 'other', 'options': {'fps': 15, 'segtime': 1}},
            {'output': 'rtsp://host:1234/path', 'topic': 'yet_another', 'options': {'fps': True, 'params': {'g': 30}}}]})
        ncfg1 = VideoOut.normalize_config(scfg)
        ncfg2 = VideoOut.normalize_config(ncfg1)

        self.assertIsInstance(ncfg1, VideoOutConfig)
        self.assertIsInstance(ncfg2, VideoOutConfig)
        self.assertEqual(ncfg1, dcfg)
        self.assertEqual(ncfg1, ncfg2)


    def test_write(self):
        os.makedirs(TEST_DIR, exist_ok=True)

        try:
            runner = Filter.Runner([
                (QueueToFilters, dict(
                    outputs = 'ipc://test-Q2F',
                    queue   = (queue := mp.Queue()),
                )),
                (VideoOut, dict(
                    sources = 'ipc://test-Q2F',
                    outputs = f'file://{TEST_VIDEO_PATH}',
                )),
            ], exit_time=10)

            try:
                queue.put(Frame(RED_IMAGE, {'meta': {'src_fps': 19}}, 'BGR'))
                queue.put(Frame(GREEN_IMAGE, {'meta': {'src_fps': 19}}, 'BGR'))
                queue.put(Frame(BLUE_IMAGE, {'meta': {'src_fps': 19}}, 'BGR'))
                queue.put(False)

                self.assertEqual(runner.wait(), [0, 0])

                fps, images = read_video(TEST_VIDEO_PATH)

                if FFMPEG:
                    self.assertEqual(fps, 19)  # if ffmpeg not present then vidgear default writer seems to set everything to 25 fps

                self.assertEqual(len(images), 3)
                self.assertEqual(images[0].shape, (200, 320, 3))
                self.assertTrue(is_image_very_red(images[0]))
                self.assertTrue(is_image_very_green(images[1]))
                self.assertTrue(is_image_very_blue(images[2]))

            finally:
                runner.stop()
                queue.close()

        finally:
            shutil.rmtree(TEST_DIR)


    def test_bgr(self):
        os.makedirs(TEST_DIR, exist_ok=True)

        try:
            runner = Filter.Runner([
                (QueueToFilters, dict(
                    outputs = 'ipc://test-Q2F',
                    queue   = (queue := mp.Queue()),
                )),
                (VideoOut, dict(
                    sources = 'ipc://test-Q2F',
                    outputs = f'file://{TEST_VIDEO_PATH}!bgr',
                )),
            ], exit_time=10)

            try:
                queue.put(Frame(RED_IMAGE, {'meta': {'src_fps': 19}}, 'BGR'))
                queue.put(False)

                self.assertEqual(runner.wait(), [0, 0])

                _, images = read_video(TEST_VIDEO_PATH)

                self.assertEqual(len(images), 1)
                self.assertTrue(is_image_very_red(images[0]))

            finally:
                runner.stop()
                queue.close()

        finally:
            shutil.rmtree(TEST_DIR)

        os.makedirs(TEST_DIR, exist_ok=True)

        try:
            runner = Filter.Runner([
                (QueueToFilters, dict(
                    outputs = 'ipc://test-Q2F',
                    queue   = (queue := mp.Queue()),
                )),
                (VideoOut, dict(
                    sources = 'ipc://test-Q2F',
                    outputs = f'file://{TEST_VIDEO_PATH}!no-bgr',
                )),
            ], exit_time=10)

            try:
                queue.put(Frame(RED_IMAGE, {'meta': {'src_fps': 19}}, 'BGR'))
                queue.put(False)

                self.assertEqual(runner.wait(), [0, 0])

                _, images = read_video(TEST_VIDEO_PATH)

                self.assertEqual(len(images), 1)
                self.assertTrue(is_image_very_blue(images[0]))

            finally:
                runner.stop()
                queue.close()

        finally:
            shutil.rmtree(TEST_DIR)


    if FFMPEG:  # only makes sense if default vidgear writer is not setting everything to 25 fps
        def test_fps(self):
            os.makedirs(TEST_DIR, exist_ok=True)

            try:
                runner = Filter.Runner([
                    (QueueToFilters, dict(
                        outputs = 'ipc://test-Q2F',
                        queue   = (queue := mp.Queue()),
                    )),
                    (VideoOut, dict(
                        sources = 'ipc://test-Q2F',
                        outputs = f'file://{TEST_VIDEO_PATH}!fps=13',
                    )),
                ], exit_time=10)

                try:
                    queue.put(Frame(RED_IMAGE, {'meta': {'src_fps': 19}}, 'BGR'))  # src_fps here will be ignored
                    queue.put(False)

                    self.assertEqual(runner.wait(), [0, 0])

                    fps, _ = read_video(TEST_VIDEO_PATH)

                    self.assertTrue(fps == 13)

                finally:
                    runner.stop()
                    queue.close()

            finally:
                shutil.rmtree(TEST_DIR)


        def test_fps_adaptive(self):
            os.makedirs(TEST_DIR, exist_ok=True)

            try:
                ORIGINAL_FPS_ADAPT_T_WAIT    = VideoWriter.FPS_ADAPT_T_WAIT  # so we don't have to wait 10 seconds for adapt
                VideoWriter.FPS_ADAPT_T_WAIT = 1 * 1_000_000_000

                runner = Filter.Runner([
                    (QueueToFilters, dict(
                        outputs = 'ipc://test-Q2F',
                        queue   = (queue := mp.Queue()),
                    )),
                    (VideoOut, dict(
                        sources = 'ipc://test-Q2F',
                        outputs = f'file://{TEST_VIDEO_PATH}!fps!segtime=0.1',  # segtime to create different videos so they can have different fps
                    )),
                ], exit_time=10)

                try:
                    for _ in range(12):
                        for _ in range(30):  # 6 * 30 frames total so we trigger the adapt algo at some point (needs a certain number of frames)
                            queue.put(Frame(RED_IMAGE, {'meta': {'src_fps': 1}}, 'BGR'))  # src_fps here will be ignored
                            queue.put(Frame(GREEN_IMAGE, {'meta': {'src_fps': 1}}, 'BGR'))
                            queue.put(Frame(BLUE_IMAGE, {'meta': {'src_fps': 1}}, 'BGR'))

                        queue.put(0.1)

                    queue.put(False)

                    self.assertEqual(runner.wait(), [0, 0])

                    fps0, _ = read_video(TEST_VIDEO_PATH[:-4] + '_000000.mp4')  # not all of these will be present but try to grab as many in case more written
                    fps1, _ = read_video(TEST_VIDEO_PATH[:-4] + '_000001.mp4')
                    fps2, _ = read_video(TEST_VIDEO_PATH[:-4] + '_000002.mp4')
                    fps3, _ = read_video(TEST_VIDEO_PATH[:-4] + '_000003.mp4')
                    fps4, _ = read_video(TEST_VIDEO_PATH[:-4] + '_000004.mp4')
                    fps5, _ = read_video(TEST_VIDEO_PATH[:-4] + '_000005.mp4')
                    fps6, _ = read_video(TEST_VIDEO_PATH[:-4] + '_000006.mp4')
                    fps7, _ = read_video(TEST_VIDEO_PATH[:-4] + '_000007.mp4')

                    self.assertFalse(fps0 == (fps1 or fps0) == (fps2 or fps0) == (fps3 or fps0) == (fps4 or fps0) ==
                        (fps5 or fps0) == (fps6 or fps0) == (fps7 or fps0))  # we don't test for correctness, just that they change, some of them will be 0 due to not existing so use first guaranteed fps in place

                finally:
                    runner.stop()
                    queue.close()

            finally:
                VideoWriter.FPS_ADAPT_T_WAIT = ORIGINAL_FPS_ADAPT_T_WAIT

                shutil.rmtree(TEST_DIR)


    def test_segtime(self):
        os.makedirs(TEST_DIR, exist_ok=True)

        try:
            runner = Filter.Runner([
                (QueueToFilters, dict(
                    outputs = 'ipc://test-Q2F',
                    queue   = (queue := mp.Queue()),
                )),
                (VideoOut, dict(
                    sources = 'ipc://test-Q2F',
                    outputs = f'file://{TEST_VIDEO_PATH}!segtime=0.016666666666666666',  # 1 / 60 (1 second)
                )),
            ], exit_time=10)

            try:
                queue.put(Frame(RED_IMAGE, {'meta': {'src_fps': 1}}, 'BGR'))
                queue.put(Frame(GREEN_IMAGE, {'meta': {'src_fps': 1}}, 'BGR'))
                queue.put(Frame(BLUE_IMAGE, {'meta': {'src_fps': 1}}, 'BGR'))
                queue.put(False)

                self.assertEqual(runner.wait(), [0, 0])

                _, images = read_video(TEST_VIDEO_PATH[:-4] + '_000000.mp4')

                self.assertEqual(len(images), 1)
                self.assertTrue(is_image_very_red(images[0]))

                _, images = read_video(TEST_VIDEO_PATH[:-4] + '_000001.mp4')

                self.assertEqual(len(images), 1)
                self.assertTrue(is_image_very_green(images[0]))

                _, images = read_video(TEST_VIDEO_PATH[:-4] + '_000002.mp4')

                self.assertEqual(len(images), 1)
                self.assertTrue(is_image_very_blue(images[0]))

            finally:
                runner.stop()
                queue.close()

        finally:
            shutil.rmtree(TEST_DIR)


    def test_config_params(self):
        os.makedirs(TEST_DIR, exist_ok=True)

        try:
            runner = Filter.Runner([
                (QueueToFilters, dict(
                    outputs = 'ipc://test-Q2F',
                    queue   = (queue := mp.Queue()),
                )),
                (VideoOut, dict(
                    sources = 'ipc://test-Q2F',
                    outputs = f'file://{TEST_VIDEO_PATH}',
                    bgr     = False,
                    fps     = 1,
                    segtime = 0.016666666666666666,  # 1 / 60 (1 second)
                )),
            ], exit_time=10)

            try:
                queue.put(Frame(RED_IMAGE, {'meta': {'src_fps': 30}}, 'BGR'))
                queue.put(Frame(GREEN_IMAGE, {'meta': {'src_fps': 30}}, 'BGR'))
                queue.put(Frame(BLUE_IMAGE, {'meta': {'src_fps': 30}}, 'BGR'))
                queue.put(False)

                self.assertEqual(runner.wait(), [0, 0])

                _, images = read_video(TEST_VIDEO_PATH[:-4] + '_000000.mp4')

                self.assertEqual(len(images), 1)
                self.assertTrue(is_image_very_blue(images[0]))

                _, images = read_video(TEST_VIDEO_PATH[:-4] + '_000001.mp4')

                self.assertEqual(len(images), 1)
                self.assertTrue(is_image_very_green(images[0]))

                _, images = read_video(TEST_VIDEO_PATH[:-4] + '_000002.mp4')

                self.assertEqual(len(images), 1)
                self.assertTrue(is_image_very_red(images[0]))

            finally:
                runner.stop()
                queue.close()

        finally:
            shutil.rmtree(TEST_DIR)


if __name__ == '__main__':
    unittest.main()
