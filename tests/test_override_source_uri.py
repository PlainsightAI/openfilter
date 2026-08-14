#!/usr/bin/env python

import os
import tempfile
import unittest

from openfilter.filter_runtime.utils import adict, resolve_override_source_uri


class TestResolveOverrideSourceURI(unittest.TestCase):
    """Unit tests for the FILTER_OVERRIDE_SOURCE_URI[_FILE] resolution helper."""

    def test_none_when_unset(self):
        self.assertIsNone(resolve_override_source_uri(adict()))

    def test_direct_value(self):
        cfg = adict(override_source_uri='s3://bucket/path/original.png')
        self.assertEqual(resolve_override_source_uri(cfg), 's3://bucket/path/original.png')

    def test_file_value(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'input.source_uri')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('s3://bucket/path/from-file.mp4\n')  # trailing newline must be stripped
            cfg = adict(override_source_uri_file=path)
            self.assertEqual(resolve_override_source_uri(cfg), 's3://bucket/path/from-file.mp4')

    def test_direct_value_wins_over_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'input.source_uri')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('s3://bucket/from-file')
            cfg = adict(override_source_uri='s3://bucket/direct', override_source_uri_file=path)
            self.assertEqual(resolve_override_source_uri(cfg), 's3://bucket/direct')

    def test_missing_file_returns_none(self):
        cfg = adict(override_source_uri_file='/no/such/file.source_uri')
        self.assertIsNone(resolve_override_source_uri(cfg))

    def test_empty_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'empty')
            open(path, 'w', encoding='utf-8').close()
            cfg = adict(override_source_uri_file=path)
            self.assertIsNone(resolve_override_source_uri(cfg))

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'requires os.mkfifo (POSIX)')
    def test_fifo_rejected(self):
        # A FIFO/named pipe must be rejected without being opened — reading it would block the
        # setup thread indefinitely. It is absolute and has no '..', so only the regular-file
        # check can reject it.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'pipe.source_uri')
            os.mkfifo(path)
            self.assertIsNone(resolve_override_source_uri(adict(override_source_uri_file=path)))

    def test_path_traversal_rejected(self):
        self.assertIsNone(resolve_override_source_uri(adict(override_source_uri_file='/ws/../etc/passwd')))

    def test_relative_path_rejected(self):
        self.assertIsNone(resolve_override_source_uri(adict(override_source_uri_file='relative/input.source_uri')))

    def test_invalid_utf8_file_returns_none(self):
        # A file with invalid UTF-8 must degrade to None (UnicodeDecodeError is a
        # ValueError), not crash the filter's setup.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'bad.source_uri')
            with open(path, 'wb') as f:
                f.write(b'\xff\xfe not valid utf-8 \x80\x81')
            cfg = adict(override_source_uri_file=path)
            self.assertIsNone(resolve_override_source_uri(cfg))

    def test_plain_dict_config(self):
        # Must work for a plain dict, not only adict (no AttributeError).
        self.assertEqual(
            resolve_override_source_uri({'override_source_uri': 's3://bucket/x.png'}),
            's3://bucket/x.png',
        )
        self.assertIsNone(resolve_override_source_uri({}))

    def test_none_config(self):
        self.assertIsNone(resolve_override_source_uri(None))

    def test_object_config_without_get(self):
        # Arbitrary config object exposing attributes but no .get().
        class Cfg:
            override_source_uri = 's3://bucket/from-attr.png'
        self.assertEqual(resolve_override_source_uri(Cfg()), 's3://bucket/from-attr.png')

    def test_bounded_read_ignores_trailing_garbage(self):
        # A pathological huge file: only the capped prefix is read; the URI (short,
        # first token) is still returned and the read is bounded.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'big.source_uri')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('s3://bucket/real.mp4')
                f.write('x' * (1 << 20))  # 1 MiB of junk after the URI on the same line
            got = resolve_override_source_uri(adict(override_source_uri_file=path))
            self.assertTrue(got.startswith('s3://bucket/real.mp4'))
            self.assertLessEqual(len(got), 4096)


if __name__ == '__main__':
    unittest.main()
