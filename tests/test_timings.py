#!/usr/bin/env python

import json
import logging
import os
import time
import unittest

import numpy as np

from openfilter.filter_runtime.utils import setLogLevelGlobal
from openfilter_timings import (
    CORNERS, JPEG_COMMENT_LIMIT, draw_table, format_epoch, insert_jpeg_comment, parse_color,
    read_jpeg_comment, timing_payload, timing_rows,
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


class TestTimingRows(unittest.TestCase):
    def _data(self, now):
        return {'meta': {'id': 3247, 'ts': now, 'filter_timings': [
            {'filter_name': 'VideoIn', 'time_in': now, 'time_out': now + 0.0177, 'duration_ms': 17.7},
            {'filter_name': 'Webvis', 'time_in': now + 0.043, 'time_out': now + 0.043013, 'duration_ms': 0.013},
        ]}}

    def test_one_row_per_filter_in_the_columns_the_script_prints(self):
        now = 1790273007.697044

        header, rows = timing_rows(self._data(now))

        self.assertEqual(header, ['ID', 'FILTER', 'TIME IN', 'TIME OUT', 'TOTAL MS', 'CLOCK'])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][:2], ['3247', 'VideoIn'])
        self.assertEqual(rows[0][2], '1790273007.697044')  # raw epoch, to line up with the script
        self.assertRegex(rows[0][5], r'^\d\d:\d\d:\d\d\.\d\d\d$')  # and the same instant as a clock

    def test_total_is_the_frame_not_the_filter_and_repeats_on_every_row(self):
        # Per-filter durations are mostly the wait for the next frame; the frame's total is the
        # number that moves when a pipeline gets slower, so that is the column.
        now = 1790273007.697044

        _, rows = timing_rows(self._data(now))

        self.assertEqual(rows[0][4], '43.013')
        self.assertEqual(rows[0][4], rows[1][4])

    def test_a_frame_with_no_chain_draws_nothing(self):
        for data in (None, {}, {'meta': {}}, {'meta': {'filter_timings': []}}):
            self.assertEqual(timing_rows(data), ([], []), data)


class TestDrawTable(unittest.TestCase):
    def setUp(self):
        now = 1790273007.697044
        self.header, self.rows = timing_rows({'meta': {'id': 1, 'ts': now, 'filter_timings': [
            {'filter_name': 'VideoIn', 'time_in': now, 'time_out': now + 0.02, 'duration_ms': 20.0},
        ]}})

    def test_draws_in_every_corner_and_stays_inside_the_frame(self):
        for corner in CORNERS:
            image = np.zeros((720, 1280, 3), dtype=np.uint8)

            draw_table(image, self.header, self.rows, corner=corner)

            ys, xs = np.nonzero(image.any(axis=2))

            self.assertGreater(len(ys), 0, corner)
            self.assertLess(xs.max(), 1280, corner)
            self.assertLess(ys.max(), 720, corner)

    def test_top_and_bottom_land_in_their_own_half(self):
        top, bottom = (np.zeros((720, 1280, 3), dtype=np.uint8) for _ in range(2))

        draw_table(top, self.header, self.rows, corner='top-left')
        draw_table(bottom, self.header, self.rows, corner='bottom-left')

        self.assertLess(np.nonzero(top.any(axis=2))[0].mean(), 360)
        self.assertGreater(np.nonzero(bottom.any(axis=2))[0].mean(), 360)

    def test_an_unknown_corner_falls_back_instead_of_raising(self):
        image = np.zeros((720, 1280, 3), dtype=np.uint8)

        draw_table(image, self.header, self.rows, corner='middle-of-nowhere')

        self.assertLess(np.nonzero(image.any(axis=2))[0].mean(), 360)

    def test_scale_follows_the_frame_so_4k_is_not_a_smear(self):
        small, big = np.zeros((720, 1280, 3), dtype=np.uint8), np.zeros((2160, 3840, 3), dtype=np.uint8)

        draw_table(small, self.header, self.rows)
        draw_table(big, self.header, self.rows)

        def width(img):
            xs = np.nonzero(img.any(axis=2))[1]
            return xs.max() - xs.min()

        self.assertGreater(width(big), width(small) * 2)

    def test_nothing_to_draw_leaves_the_frame_untouched(self):
        image = np.zeros((720, 1280, 3), dtype=np.uint8)

        draw_table(image, [], [])

        self.assertEqual(image.sum(), 0)

    def test_gray_and_rgb_frames_are_handled(self):
        gray = np.zeros((720, 1280), dtype=np.uint8)
        rgb = np.zeros((720, 1280, 3), dtype=np.uint8)

        draw_table(gray, self.header, self.rows, is_gray=True)
        draw_table(rgb, self.header, self.rows, color=(255, 0, 0), is_bgr=False)

        self.assertGreater(gray.sum(), 0)
        self.assertGreater(rgb[..., 0].sum(), 0)
        self.assertEqual(rgb[..., 2].sum(), 0)
