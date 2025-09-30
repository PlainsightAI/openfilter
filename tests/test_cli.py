#!/usr/bin/env python

import ast
import inspect
import logging
import os
import subprocess
import textwrap
import unittest
from time import sleep

from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.utils import setLogLevelGlobal

logger = logging.getLogger(__name__)

os.environ["LOG_LEVEL"] = LOG_LEVEL = (
    os.getenv("LOG_LEVEL") or "CRITICAL"
).upper()  # because we want to pass it down to subprocess.run()

setLogLevelGlobal(int(getattr(logging, LOG_LEVEL)))

TEST_VIDEO_FNM = "test_video.mp4"
TEST_VIDEO_OUT_FNM = "test_video_out.mp4"

RED_THEN_GREEN_THEN_BLUE_FRAME_MP4 = (
    b"\x00\x00\x00 ftypisom\x00\x00\x02\x00isomiso2avc1mp41\x00\x00\x00\x08free\x00\x00\x03\xabmdat\x00\x00\x02\xad"
    b"\x06\x05\xff\xff\xa9\xdcE\xe9\xbd\xe6\xd9H\xb7\x96,\xd8 \xd9#\xee\xefx264 - core 163 r3060 5db6aa6 - H.264/MPEG-4"
    b" AVC codec - Copyleft 2003-2021 - http://www.videolan.org/x264.html - options: cabac=1 ref=2 deblock=1:0:0 analys"
    b"e=0x3:0x113 me=hex subme=6 psy=1 psy_rd=1.00:0.00 mixed_ref=1 me_range=16 chroma_me=1 trellis=1 8x8dct=1 cqm=0 de"
    b"adzone=21,11 fast_pskip=1 chroma_qp_offset=4 threads=6 lookahead_threads=1 sliced_threads=0 nr=0 decimate=1 inter"
    b"laced=0 bluray_compat=0 constrained_intra=0 bframes=3 b_pyramid=2 b_adapt=1 b_bias=0 direct=1 weightb=1 open_gop="
    b"0 weightp=1 keyint=250 keyint_min=25 scenecut=40 intra_refresh=0 rc_lookahead=30 rc=crf mbtree=1 crf=18.0 qcomp=0"
    b".60 qpmin=0 qpmax=69 qpstep=4 ip_ratio=1.40 aq=1:1.00\x00\x80\x00\x00\x007e\x88\x84\x00+\xff\xfe\xf7#\xfc\ni\x83"
    b"\xff\xf0)\x8d\xbd\xff\x02\x9a\xf0g\x7f\xff\xcb\xff\x1a\xb7\\\xabR@d|\x00\x12\xbd\xc8\x02U\x8c\xb3\r\x86\x80\x00"
    b"\x00\x03\x00\x00\x03\x00\rY\x00\x00\x00UA\x9a!i\xe8\x04\x04\x04\x00\x12@\xac\x03\xfd\t\xff\x95@\xf9Oc\xe6\x07\xf6"
    b"Dt\xbe''g~\xaaS\xc1\xeb\xaf\xe0\x10\xd4\x16]|_\xd07\xc3\xb8\xdd\x8bu6\xd0\x91.w\x10j\x1f\xb9\xea\xe8\x00\x00"
    b"\x0b\xfc\x00\x00\x03\x00\xa3\x00\x1f\xe6\xd6\xb1\xa9\xe8\x94v\xb6\xe4d\x00\x1f\x10\x00\x00\x00ZA\x9aB\x13\xd0\r"
    b"\x18\x0f\xe0\x1f\xc0 \x00K\x08O\xff\x90\x1f\xe9\x7f\xfc,&\xa9\xeb\xf2k\xed\xb3<\xfb\xa1\xde\x0f\x1d\x10\xa7\x83"
    b'\xd7_\xc0!\xa8,\xba\xf8\xbf\xa0o\x87q\xbb\x16\xeam\xa1"\\\xee \xd4?s\xd5\xd0\x00\x00\x17\xf8\x00\x00\x03\x01F\x00'
    b"?\xcd\xadcS\xd1(\xedm\xc8\xc8\x00>!\x00\x00\x03?moov\x00\x00\x00lmvhd\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x03\xe8\x00\x00\x00d\x00\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00@"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x02\x00\x00\x02itrak\x00\x00\x00\\tkhd\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01"
    b"\x00\x00\x00\x00\x00\x00\x00d\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00@\x00"
    b"\x00\x00\x01@\x00\x00\x00\xc8\x00\x00\x00\x00\x00$edts\x00\x00\x00\x1celst\x00\x00\x00\x00\x00\x00\x00\x01\x00"
    b"\x00\x00d\x00\x00\x04\x00\x00\x01\x00\x00\x00\x00\x01\xe1mdia\x00\x00\x00 mdhd\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00<\x00\x00\x00\x06\x00U\xc4\x00\x00\x00\x00\x00-hdlr\x00\x00\x00\x00\x00\x00\x00\x00vide"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00VideoHandler\x00\x00\x00\x01\x8cminf\x00\x00\x00\x14vmhd\x00\x00"
    b"\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00$dinf\x00\x00\x00\x1cdref\x00\x00\x00\x00\x00\x00\x00\x01\x00"
    b"\x00\x00\x0curl \x00\x00\x00\x01\x00\x00\x01Lstbl\x00\x00\x00\xb0stsd\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00"
    b"\xa0avc1\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01@\x00"
    b"\xc8\x00H\x00\x00\x00H\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x18\xff\xff\x00\x00\x006avcC\x01\xf4"
    b"\x00\r\xff\xe1\x00\x18g\xf4\x00\r\x91\x9b((7\xf10\x80\x00\x00\x03\x00\x80\x00\x00\x1e\x07\x8a\x14\xcb\x01\x00\x07"
    b'h\xea\xe0\x8cD\x84@\xff\xf8\xf8\x00\x00\x00\x00\x14btrt\x00\x00\x00\x00\x00\x01"\xf0\x00\x01"\xf0\x00\x00\x00\x18'
    b"stts\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x03\x00\x00\x02\x00\x00\x00\x00\x14stss\x00\x00\x00\x00\x00\x00"
    b"\x00\x01\x00\x00\x00\x01\x00\x00\x00\x18ctts\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x03\x00\x00\x04\x00\x00"
    b"\x00\x00\x1cstsc\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x03\x00\x00\x00\x01\x00\x00\x00 stsz"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\x00\x00\x02\xec\x00\x00\x00Y\x00\x00\x00^\x00\x00\x00\x14stco"
    b"\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x000\x00\x00\x00budta\x00\x00\x00Zmeta\x00\x00\x00\x00\x00\x00\x00!hdlr"
    b"\x00\x00\x00\x00\x00\x00\x00\x00mdirappl\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00-ilst\x00\x00\x00%\xa9too"
    b"\x00\x00\x00\x1ddata\x00\x00\x00\x01\x00\x00\x00\x00Lavf58.76.100"
)


def quiet_unlink(fnm):
    try:
        os.unlink(fnm)
    except FileNotFoundError:
        pass

def parse_dry_output(output: str) -> dict:
    """Parse dry-run CLI output into a dict keyed by filter ID."""
    sections = output.strip().split("\n\n")
    parsed = {}
    for section in sections:
        lines = section.splitlines()
        if not lines:
            continue
        filter_id = lines[0].rstrip(":")
        dict_str = "\n".join(lines[2:])  # skip header and dashed line
        parsed[filter_id] = ast.literal_eval(dict_str)
    return parsed

class TestCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(TEST_VIDEO_FNM, "wb") as f:
            f.write(RED_THEN_GREEN_THEN_BLUE_FRAME_MP4)

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(TEST_VIDEO_FNM)
        except Exception:
            pass

    def test_info(self):
        res = subprocess.run(
            ["openfilter", "info", "openfilter.filter_runtime.filter.Filter"], stdout=subprocess.PIPE, text=True
        )

        self.assertEqual(res.returncode, 0)
        self.assertTrue(inspect.cleandoc(Filter.__doc__).strip() in res.stdout)

    def test_run_dry(self):
        res = subprocess.run(
            [
                "openfilter",
                "run",
                "--dry",
                *"""
                - VideoIn
                    --sources file:///home/tom/D/Downloads/turosi_geelong_2024-01-23-truck-6-05_49_47.mp4
                - Util
                    --sources VideoIn;main;test
                    --misc1 file://testdir/testfile
                    --misc2 file://./testdir/testfile
                    --misc3 file://testfile
                    --misc4 file://./testfile
                    --log pretty
                - Webvis
                - VideoOut
                    --outputs file://videoout.mpg
            """.strip().split(),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(res.returncode, 0)
        actual = parse_dry_output(res.stdout)

        self.assertEqual(actual["VideoIn"]["sources"], "file:///home/tom/D/Downloads/turosi_geelong_2024-01-23-truck-6-05_49_47.mp4")
        self.assertEqual(actual["Util"]["misc1"], "file://testdir/testfile")
        self.assertEqual(actual["Util"]["log"], "pretty")
        self.assertIn("Webvis", actual)

    def test_run(self):
        quiet_unlink(TEST_VIDEO_OUT_FNM)

        res = subprocess.run(
            [
                "openfilter",
                "run",
                *f"""
            - VideoIn
                --sources file://{TEST_VIDEO_FNM}!loop=3
            - Util
            - VideoOut
                --outputs file://{TEST_VIDEO_OUT_FNM}
        """.strip().split(),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )

        try:
            sleep(0.5)  # maybe ffmpeg didn't finish writing out the file yet

            self.assertEqual(res.returncode, 0)
            self.assertTrue(os.path.isfile(TEST_VIDEO_OUT_FNM))
            self.assertGreater(
                os.stat(TEST_VIDEO_OUT_FNM).st_size, 0
            )  # just make sure it exists and has data, correctness is tested elsewhere

        finally:
            quiet_unlink(TEST_VIDEO_OUT_FNM)


if __name__ == "__main__":
    unittest.main()
