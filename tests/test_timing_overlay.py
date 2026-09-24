#!/usr/bin/env python

import json
import logging
import os
import time
import unittest

import numpy as np

from openfilter.filter_runtime.utils import setLogLevelGlobal
from openfilter.filter_runtime.filters.timing_overlay import (
    CORNER_COLORS, CORNERS, JPEG_COMMENT_LIMIT, corners_for, draw_blocks, draw_lines, format_epoch,
    insert_jpeg_comment, parse_color, parse_placement, placement_for, read_jpeg_comment,
    timing_blocks, timing_payload,
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


class TestTimingBlocks(unittest.TestCase):
    def test_one_block_per_filter_plus_webvis(self):
        now = time.time()
        data = {'meta': {'ts': now - 2.4, 'filter_timings': [
            {'filter_name': 'VideoIn', 'time_in': now - 2.4, 'time_out': now - 2.37, 'duration_ms': 35.2},
            {'filter_name': 'RtDetr', 'time_in': now - 2.37, 'time_out': now - 2.3, 'duration_ms': 70.0},
        ]}}

        blocks = timing_blocks(data)

        self.assertEqual([label.split()[0] for label, _ in blocks], ['VideoIn', 'RtDetr'])
        self.assertTrue(blocks[0][1][0].startswith('ts  '))   # read stamp sits with the source
        self.assertFalse(any(line.startswith('ts  ') for line in blocks[1][1]))
        self.assertIn('35.2ms', blocks[0][1][2])
        # The gap between the frame's read time and the wall clock is the whole
        # point: the filters above it can all be fast while this one is not.
        self.assertEqual(len(blocks[1][1]), 2)  # every filter reads the same lines

    def test_served_is_its_own_block_holding_the_value_no_filter_records(self):
        now = time.time()
        data = {'meta': {'ts': now - 2.4, 'filter_timings': [
            {'filter_name': 'VideoIn', 'time_in': now - 2.4, 'time_out': now - 2.3, 'duration_ms': 90.0},
        ]}}

        label, lines = timing_blocks(data, served=now)[-1]

        # It rides with the last filter, so that filter keeps the corner opposite the source.
        self.assertEqual(label.split()[0], 'VideoIn')
        self.assertTrue(lines[-2].startswith('served '))
        self.assertRegex(lines[-1], r'ts -> served\s+2[34]\d\dms')

    def test_without_a_serve_time_there_is_no_served_block(self):
        now = time.time()
        data = {'meta': {'ts': now, 'filter_timings': [
            {'filter_name': 'VideoIn', 'time_in': now, 'time_out': now, 'duration_ms': 1.0},
        ]}}

        self.assertEqual([label.split()[0] for label, _ in timing_blocks(data)], ['VideoIn'])
        self.assertEqual(len(timing_blocks(data)[0][1]), 3)  # ts, in, out and nothing else

    def test_survives_a_frame_with_no_timings(self):
        for data in (None, {}, {'meta': {}}, {'meta': {'filter_timings': []}}):
            blocks = timing_blocks(data)

            self.assertEqual([label for label, _ in blocks], [], data)


class TestCornersFor(unittest.TestCase):
    def test_source_and_webvis_keep_the_same_two_corners(self):
        # However many filters sit between them, the two ends a reader compares
        # stay put, so the eye learns one place to look.
        for count in range(2, 7):
            corners = corners_for(count)

            self.assertEqual(corners[0], 'top-left', count)
            self.assertEqual(corners[-1], 'top-right', count)
            self.assertEqual(len(corners), count, count)

    def test_middles_fill_the_opposite_edge(self):
        self.assertEqual(corners_for(4), ['top-left', 'bottom-left', 'bottom-right', 'top-right'])

    def test_first_corner_moves_the_whole_layout(self):
        self.assertEqual(corners_for(2, 'bottom-right'), ['bottom-right', 'bottom-left'])

    def test_a_single_block_just_takes_the_first_corner(self):
        self.assertEqual(corners_for(1, 'bottom-left'), ['bottom-left'])

    def test_unknown_corner_falls_back_instead_of_raising(self):
        self.assertEqual(corners_for(2, 'middle'), ['top-left', 'top-right'])


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


class TestDrawBlocks(unittest.TestCase):
    def test_two_filters_land_in_opposite_top_corners(self):
        now = time.time()
        data = {'meta': {'ts': now, 'filter_timings': [
            {'filter_name': 'VideoIn', 'time_in': now, 'time_out': now, 'duration_ms': 1.0},
        ]}}
        image = np.zeros((480, 640, 3), dtype=np.uint8)

        draw_blocks(image, timing_blocks(data, served=now))

        ys, xs = np.nonzero(image.any(axis=2))

        self.assertLess(ys.mean(), 240)                     # both in the top half
        self.assertGreater(xs.max(), 320)                   # one block reaches the right side
        self.assertLess(xs.min(), 320)                      # and one the left


class TestJpegComment(unittest.TestCase):
    def _jpg(self):
        import cv2

        ok, buf = cv2.imencode('.jpg', np.zeros((64, 64, 3), dtype=np.uint8))

        self.assertTrue(ok)

        return bytes(buf)

    def test_round_trips_and_leaves_the_picture_decodable(self):
        import cv2

        jpg = self._jpg()

        out = insert_jpeg_comment(jpg, '{"ts": 1.5}')

        self.assertEqual(read_jpeg_comment(out), '{"ts": 1.5}')
        # The point of COM: every decoder skips it, so the image itself is unaffected.
        self.assertIsNotNone(cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR))
        self.assertEqual(len(out), len(jpg) + len('{"ts": 1.5}') + 4)

    def test_a_jpeg_without_a_comment_reads_as_none(self):
        self.assertIsNone(read_jpeg_comment(self._jpg()))

    def test_non_jpeg_input_is_returned_untouched(self):
        # Instrumentation on the serving path must not raise on a surprise.
        self.assertEqual(insert_jpeg_comment(b'not a jpeg', 'x'), b'not a jpeg')

    def test_oversized_text_is_truncated_to_what_the_length_field_can_describe(self):
        out = insert_jpeg_comment(self._jpg(), 'x' * (JPEG_COMMENT_LIMIT + 100))

        self.assertEqual(len(read_jpeg_comment(out)), JPEG_COMMENT_LIMIT)

    def test_payload_carries_the_chain_and_both_ends(self):
        now = time.time()
        data = {'meta': {'ts': now - 2.4, 'filter_timings': [
            {'filter_name': 'VideoIn', 'time_in': now - 2.4, 'time_out': now - 2.3, 'duration_ms': 90.0},
        ]}}

        payload = timing_payload(data, served=now)

        self.assertEqual(payload['ts'], now - 2.4)
        self.assertEqual(payload['served'], now)
        self.assertEqual(payload['filters'], [
            {'name': 'VideoIn', 'in': now - 2.4, 'out': now - 2.3, 'duration_ms': 90.0},
        ])

    def test_payload_is_json_serialisable_for_an_empty_frame(self):
        self.assertEqual(json.loads(json.dumps(timing_payload(None)))['filters'], [])


class TestPlacement(unittest.TestCase):
    def test_defaults_put_the_two_ends_apart_and_in_different_colours(self):
        corners = corners_for(2)

        source = placement_for('VideoIn', 0, corners, {})
        last = placement_for('Webvis', 1, corners, {})

        self.assertEqual(source, ('top-left', CORNER_COLORS['top-left']))
        self.assertEqual(last, ('top-right', CORNER_COLORS['top-right']))
        self.assertNotEqual(source[1], last[1])

    def test_corner_and_colour_share_one_spelling_in_either_order(self):
        for spec in ('video_in=bottom-right:#0f0', 'video_in=#0f0:bottom-right'):
            placement = placement_for('VideoIn', 0, corners_for(2), parse_placement(spec))

            self.assertEqual(placement, ('bottom-right', (0, 255, 0)), spec)

    def test_either_may_be_given_alone(self):
        corners = corners_for(2)

        self.assertEqual(placement_for('VideoIn', 0, corners, parse_placement('video_in=#f0f')),
                         ('top-left', (255, 0, 255)))
        self.assertEqual(placement_for('VideoIn', 0, corners, parse_placement('video_in=bottom-left')),
                         ('bottom-left', CORNER_COLORS['bottom-left']))

    def test_names_match_across_the_configs_spelling_and_the_chains(self):
        # The config says `video_in`, `filter_timings` says `VideoIn`.
        for name in ('video_in', 'VideoIn', 'VIDEO_IN'):
            spec = parse_placement(f'{name}=bottom-right')

            self.assertEqual(placement_for('VideoIn', 0, corners_for(2), spec)[0], 'bottom-right', name)

    def test_a_typo_costs_that_block_its_placement_not_the_run(self):
        for spec in ('video_in', 'video_in=', 'video_in=middle', ''):
            placement = placement_for('VideoIn', 0, corners_for(2), parse_placement(spec))

            self.assertEqual(placement, ('top-left', CORNER_COLORS['top-left']), spec)
