#!/usr/bin/env python

import logging
import os
import time
import unittest

import numpy as np

from openfilter.filter_runtime.utils import setLogLevelGlobal
from openfilter.filter_runtime.filters.timing_overlay import (
    CORNERS, draw_lines, format_epoch, parse_color, timing_lines,
)

logger = logging.getLogger(__name__)

log_level = int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper()))

setLogLevelGlobal(log_level)


class TestParseColor(unittest.TestCase):
    def test_both_hex_spellings(self):
        self.assertEqual(parse_color('#0f0'), (0, 255, 0))
        self.assertEqual(parse_color('#00ff00'), (0, 255, 0))
        self.assertEqual(parse_color('00ff00'), (0, 255, 0))  # '#' optional

    def test_falls_back_to_white_rather_than_raising(self):
        # A debug overlay that refuses to start over a typo measures nothing, so
        # every bad spelling has to keep the pipeline running.
        for bad in (None, '', 'green', '#12', '#gggggg', '#1234567'):
            self.assertEqual(parse_color(bad), (255, 255, 255), bad)


class TestFormatEpoch(unittest.TestCase):
    def test_matches_the_camera_format(self):
        t = time.mktime((2026, 9, 22, 15, 22, 53, 0, 0, -1))

        self.assertEqual(format_epoch(t, with_millis=False), '2026-09-22 15:22:53')
        self.assertEqual(format_epoch(t + 0.125), '2026-09-22 15:22:53.125')

    def test_missing_time_is_a_dash_not_an_exception(self):
        self.assertEqual(format_epoch(None), '-')


class TestTimingLines(unittest.TestCase):
    def test_one_line_per_filter_plus_the_two_clocks(self):
        now = time.time()
        data = {'meta': {'ts': now - 2.4, 'filter_timings': [
            {'filter_name': 'VideoIn', 'time_in': now - 2.4, 'time_out': now - 2.37, 'duration_ms': 35.2},
            {'filter_name': 'RtDetr', 'time_in': now - 2.37, 'time_out': now - 2.3, 'duration_ms': 70.0},
        ]}}

        lines = timing_lines(data)

        self.assertEqual(len(lines), 5)  # ts, two filters, now, ts->now
        self.assertIn('VideoIn', lines[1])
        self.assertIn('35.2ms', lines[1])
        self.assertIn('RtDetr', lines[2])
        self.assertTrue(lines[3].startswith('webvis now'))
        # The gap between the frame's read time and the wall clock is the whole
        # point: the filters above it can all be fast while this one is not.
        self.assertRegex(lines[4], r'ts -> now\s+2[34]\d\dms')

    def test_survives_a_frame_with_no_timings(self):
        for data in (None, {}, {'meta': {}}, {'meta': {'filter_timings': []}}):
            lines = timing_lines(data)

            self.assertTrue(any(line.startswith('webvis now') for line in lines), data)


class TestDrawLines(unittest.TestCase):
    def setUp(self):
        self.lines = ['video_in ts   2026-09-22 15:22:53.100', 'webvis now    2026-09-22 15:22:53.124']

    def test_draws_in_every_corner_and_stays_inside_the_image(self):
        for corner in CORNERS:
            image = np.zeros((480, 640, 3), dtype=np.uint8)

            draw_lines(image, self.lines, corner=corner, color=(0, 255, 0))

            ys, xs = np.nonzero(image.any(axis=2))

            self.assertGreater(len(ys), 0, corner)
            self.assertGreaterEqual(xs.min(), 0, corner)
            self.assertLess(xs.max(), 640, corner)
            self.assertLess(ys.max(), 480, corner)

    def test_top_and_bottom_land_in_their_own_half(self):
        top, bottom = np.zeros((480, 640, 3), dtype=np.uint8), np.zeros((480, 640, 3), dtype=np.uint8)

        draw_lines(top, self.lines, corner='top-left')
        draw_lines(bottom, self.lines, corner='bottom-left')

        self.assertLess(np.nonzero(top.any(axis=2))[0].mean(), 240)
        self.assertGreater(np.nonzero(bottom.any(axis=2))[0].mean(), 240)

    def test_an_unknown_corner_draws_top_left_instead_of_raising(self):
        image = np.zeros((480, 640, 3), dtype=np.uint8)

        draw_lines(image, self.lines, corner='middle-of-nowhere')

        self.assertLess(np.nonzero(image.any(axis=2))[0].mean(), 240)

    def test_bgr_and_rgb_put_the_same_channel_where_each_expects_it(self):
        rgb, bgr = np.zeros((480, 640, 3), dtype=np.uint8), np.zeros((480, 640, 3), dtype=np.uint8)

        draw_lines(rgb, self.lines, color=(255, 0, 0), is_bgr=False)
        draw_lines(bgr, self.lines, color=(255, 0, 0), is_bgr=True)

        self.assertGreater(rgb[..., 0].sum(), 0)   # red in channel 0 for RGB
        self.assertEqual(rgb[..., 2].sum(), 0)
        self.assertGreater(bgr[..., 2].sum(), 0)   # and in channel 2 for BGR
        self.assertEqual(bgr[..., 0].sum(), 0)

    def test_gray_averages_the_colour_instead_of_failing(self):
        image = np.zeros((480, 640), dtype=np.uint8)

        draw_lines(image, self.lines, color=(255, 255, 255), is_gray=True)

        self.assertGreater(image.sum(), 0)

    def test_no_lines_leaves_the_image_untouched(self):
        image = np.zeros((480, 640, 3), dtype=np.uint8)

        draw_lines(image, [])

        self.assertEqual(image.sum(), 0)


if __name__ == '__main__':
    unittest.main()
