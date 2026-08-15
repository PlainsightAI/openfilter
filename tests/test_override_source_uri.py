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

    def test_null_bytes_stripped(self):
        # A NUL byte is valid UTF-8 and survives decoding, so a corrupt/binary sidecar could
        # otherwise carry \x00 into meta['src']. Embedded NULs must be stripped out.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'nul.source_uri')
            with open(path, 'wb') as f:
                f.write(b's3://bucket/\x00na\x00me.png\n')
            cfg = adict(override_source_uri_file=path)
            self.assertEqual(resolve_override_source_uri(cfg), 's3://bucket/name.png')

    def test_all_null_bytes_returns_none(self):
        # A first line that is only NULs strips to empty -> None, not ''.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'nuls.source_uri')
            with open(path, 'wb') as f:
                f.write(b'\x00\x00\x00')
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

    def test_over_length_first_line_rejected(self):
        # A pathological first line (URI + 1 MiB of junk on the same line) exceeds the cap and is
        # rejected outright — a truncated/contaminated URI must not ride into meta['src'].
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'big.source_uri')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('s3://bucket/real.mp4')
                f.write('x' * (1 << 20))  # 1 MiB of junk after the URI on the same line
            self.assertIsNone(resolve_override_source_uri(adict(override_source_uri_file=path)))

    def test_multibyte_first_line_under_char_cap_accepted(self):
        # The cap is 4096 CHARACTERS, not bytes: a first line of multi-byte characters that is
        # under the char cap but over 4096 bytes must still be accepted (guards the
        # characters-vs-bytes distinction in the cap check and its message).
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'multibyte.source_uri')
            value = 'é' * 3000  # 3000 chars (< 4096) but 6000 bytes (> 4096) in UTF-8
            with open(path, 'w', encoding='utf-8') as f:
                f.write(value + '\n')
            self.assertEqual(resolve_override_source_uri(adict(override_source_uri_file=path)), value)

    def test_exactly_max_length_with_newline_accepted(self):
        # A 4096-character URI followed by a trailing newline must be accepted: the cap applies to
        # the payload, not the newline (regression for an off-by-one where readline's char count
        # included the '\n' and rejected a full-length URI only because it ended with a newline).
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'maxlen.source_uri')
            value = 's3://bucket/' + 'a' * (4096 - len('s3://bucket/'))  # exactly 4096 chars
            self.assertEqual(len(value), 4096)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(value + '\n')
            self.assertEqual(resolve_override_source_uri(adict(override_source_uri_file=path)), value)

    def test_over_max_length_rejected(self):
        # 4097 characters of payload is over the cap -> rejected.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'over.source_uri')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('a' * 4097 + '\n')
            self.assertIsNone(resolve_override_source_uri(adict(override_source_uri_file=path)))

    def test_trailing_lines_ignored(self):
        # Only the first line is read; junk on later lines never rides into meta['src'].
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'multi.source_uri')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('s3://bucket/real.mp4\nignored second line\nmore junk\n')
            self.assertEqual(
                resolve_override_source_uri(adict(override_source_uri_file=path)), 's3://bucket/real.mp4')


if __name__ == '__main__':
    unittest.main()
