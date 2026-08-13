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
            with open(path, 'w') as f:
                f.write('s3://bucket/path/from-file.mp4\n')  # trailing newline must be stripped
            cfg = adict(override_source_uri_file=path)
            self.assertEqual(resolve_override_source_uri(cfg), 's3://bucket/path/from-file.mp4')

    def test_direct_value_wins_over_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'input.source_uri')
            with open(path, 'w') as f:
                f.write('s3://bucket/from-file')
            cfg = adict(override_source_uri='s3://bucket/direct', override_source_uri_file=path)
            self.assertEqual(resolve_override_source_uri(cfg), 's3://bucket/direct')

    def test_missing_file_returns_none(self):
        cfg = adict(override_source_uri_file='/no/such/file.source_uri')
        self.assertIsNone(resolve_override_source_uri(cfg))

    def test_empty_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'empty')
            open(path, 'w').close()
            cfg = adict(override_source_uri_file=path)
            self.assertIsNone(resolve_override_source_uri(cfg))


if __name__ == '__main__':
    unittest.main()
