#!/usr/bin/env python

import gc
import logging
import multiprocessing as mp
import os
import unittest
from time import time

from openfilter.filter_runtime import Frame
from openfilter.filter_runtime.test import RunnerContext, FiltersToQueue, QueueToFilters
from openfilter.filter_runtime.utils import setLogLevelGlobal
from openfilter.filter_runtime.filters.util import Util, UtilConfig

import numpy as np

logger = logging.getLogger(__name__)

log_level = int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper()))

setLogLevelGlobal(log_level)

# BGR is in effect
REDPX          = np.array((0, 0, 255), np.uint8)
GREENPX        = np.array((0, 255, 0), np.uint8)
BLUEPX         = np.array((255, 0, 0), np.uint8)
WHITEPX        = np.array((255, 255, 255), np.uint8)
GRAY8PX        = np.array((136, 136, 136), np.uint8)
GRAYREDPX      = np.array(76, np.uint8)
GRAYGREENPX    = np.array(150, np.uint8)
GRAYBLUEPX     = np.array(29, np.uint8)
GRAYWHITEPX    = np.array(255, np.uint8)
CH3GRAYREDPX   = np.array((76, 76, 76), np.uint8)
CH3GRAYGREENPX = np.array((150, 150, 150), np.uint8)
CH3GRAYBLUEPX  = np.array((29, 29, 29), np.uint8)
CH3GRAYWHITEPX = np.array((255, 255, 255), np.uint8)
IMAGE          = np.zeros((200, 320, 3), np.uint8)
IMAGE[0,0]     = IMAGE[0,1]     = IMAGE[1,0]     = IMAGE[1,1]     = REDPX  # 4 pixels for resize down maintain same color
IMAGE[0,319]   = IMAGE[0,318]   = IMAGE[1,319]   = IMAGE[1,318]   = GREENPX
IMAGE[199,0]   = IMAGE[199,1]   = IMAGE[198,0]   = IMAGE[198,1]   = BLUEPX
IMAGE[199,319] = IMAGE[199,318] = IMAGE[198,319] = IMAGE[198,318] = WHITEPX
FRAME          = Frame(IMAGE, format='BGR')
GRAYFRAME      = FRAME.gray


class TestUtil(unittest.TestCase):
    def tearDown(self):
        # Force garbage collection to clean up file descriptors
        gc.collect()

    def test_normalize_config(self):
        scfg  = dict(id='util', sources='tcp://localhost', sleep=1.23, exit_after=4.56, xforms=''
            'flipx, flipy, flipboth, rotcw, rotccw, swaprgb, fmtrgb, fmtbgr, fmtgray, '
            'resize 123x456, maxsize 321 + 654 lin, minsize 135x246C, '
            'box 0+0x1x1 #fdb975, box .1 + 0.2 x 0.3 x 0.4 #246'
        )
        dcfg  = UtilConfig({'id': 'util', 'sources': ['tcp://localhost'], 'sleep': 1.23, 'exit_after': 4.56, 'xforms': [
            {'action': 'flipx'}, {'action': 'flipy'}, {'action': 'flipboth'}, {'action': 'rotcw'}, {'action': 'rotccw'},
            {'action': 'swaprgb'}, {'action': 'fmtrgb'}, {'action': 'fmtbgr'}, {'action': 'fmtgray'},
            {'action': 'resize', 'width': 123, 'height': 456},
            {'action': 'maxsize', 'width': 321, 'height': 654, 'aspect': False, 'interp': 'L'},
            {'action': 'minsize', 'width': 135, 'height': 246, 'interp': 'C'},
            {'action': 'box', 'x': 0.0, 'y': 0.0, 'width': 1.0, 'height': 1.0, 'color': (253, 185, 117)},
            {'action': 'box', 'x': 0.1, 'y': 0.2, 'width': 0.3, 'height': 0.4, 'color': (34, 68, 102)}],})
        ncfg1 = Util.normalize_config(scfg)
        ncfg2 = Util.normalize_config(ncfg1)

        self.assertIsInstance(ncfg1, UtilConfig)
        self.assertIsInstance(ncfg2, UtilConfig)
        self.assertEqual(ncfg1, dcfg)
        self.assertEqual(ncfg1, ncfg2)


    def test_sleep(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs = 'ipc://test-Q2F',
                queue   = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources = 'ipc://test-Q2F',
                outputs = 'ipc://test-util',
                sleep   = 0.1,
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            datas = []
            t0    = time()

            for i in range(5):
                datas.append(data := {'test': i})
                qin.put(dict(main=Frame(data)))

            qin.put(False)

            for i in range(5):
                self.assertEqual((qout.get()['main']).data, datas[i])

            self.assertFalse(qout.get())
            self.assertGreater(time() - t0, 0.5)
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_maxfps(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs = 'ipc://test-Q2F',
                queue   = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources = 'ipc://test-Q2F',
                outputs = 'ipc://test-util',
                maxfps  = 10,
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            datas = []
            t0    = time()

            for i in range(5):
                datas.append(data := {'test': i})
                qin.put(dict(main=Frame(data)))

            qin.put(False)

            for i in range(5):
                self.assertEqual((qout.get()['main']).data, datas[i])

            self.assertFalse(qout.get())
            self.assertGreater(time() - t0, 0.5)
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_xforms_flip(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs     = 'ipc://test-Q2F',
                outputs_jpg = False,  # because otherwise colors are not exact
                queue       = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources     = 'ipc://test-Q2F',
                outputs     = 'ipc://test-util',
                outputs_jpg = False,
                xforms      = 'flipx;tflipx, flipy;tflipy, flipboth;tflipboth',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put(dict(tflipx=FRAME, tflipy=FRAME, tflipboth=FRAME))
            qin.put(False)

            frames    = qout.get()
            iflipx    = (fflipx := frames['tflipx']).image
            iflipy    = (fflipy := frames['tflipy']).image
            iflipboth = (fflipboth := frames['tflipboth']).image

            self.assertEqual(str(fflipx), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(fflipy), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(fflipboth), 'Frame(320x200xBGR-ro)')

            self.assertTrue(np.array_equal(iflipx[0, 0], GREENPX))
            self.assertTrue(np.array_equal(iflipx[0, 319], REDPX))
            self.assertTrue(np.array_equal(iflipx[199, 0], WHITEPX))
            self.assertTrue(np.array_equal(iflipx[199, 319], BLUEPX))

            self.assertTrue(np.array_equal(iflipy[0, 0], BLUEPX))
            self.assertTrue(np.array_equal(iflipy[0, 319], WHITEPX))
            self.assertTrue(np.array_equal(iflipy[199, 0], REDPX))
            self.assertTrue(np.array_equal(iflipy[199, 319], GREENPX))

            self.assertTrue(np.array_equal(iflipboth[0, 0], WHITEPX))
            self.assertTrue(np.array_equal(iflipboth[0, 319], BLUEPX))
            self.assertTrue(np.array_equal(iflipboth[199, 0], GREENPX))
            self.assertTrue(np.array_equal(iflipboth[199, 319], REDPX))

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_xforms_rot(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs     = 'ipc://test-Q2F',
                outputs_jpg = False,  # because otherwise colors are not exact
                queue       = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources     = 'ipc://test-Q2F',
                outputs     = 'ipc://test-util',
                outputs_jpg = False,
                xforms      = 'rotcw;trotcw, rotccw;trotccw',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put(dict(trotcw=FRAME, trotccw=FRAME, tflipboth=FRAME))
            qin.put(False)

            frames  = qout.get()
            irotcw  = (frotcw := frames['trotcw']).image
            irotccw = (frotccw := frames['trotccw']).image

            self.assertEqual(str(frotcw), 'Frame(200x320xBGR-ro)')
            self.assertEqual(str(frotccw), 'Frame(200x320xBGR-ro)')

            self.assertTrue(np.array_equal(irotcw[0, 0], BLUEPX))
            self.assertTrue(np.array_equal(irotcw[0, 199], REDPX))
            self.assertTrue(np.array_equal(irotcw[319, 0], WHITEPX))
            self.assertTrue(np.array_equal(irotcw[319, 199], GREENPX))

            self.assertTrue(np.array_equal(irotccw[0, 0], GREENPX))
            self.assertTrue(np.array_equal(irotccw[0, 199], WHITEPX))
            self.assertTrue(np.array_equal(irotccw[319, 0], REDPX))
            self.assertTrue(np.array_equal(irotccw[319, 199], BLUEPX))

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_xforms_swap_fmt(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs     = 'ipc://test-Q2F',
                outputs_jpg = False,  # because otherwise colors are not exact
                queue       = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources     = 'ipc://test-Q2F',
                outputs     = 'ipc://test-util',
                outputs_jpg = False,
                xforms      = 'swaprgb;tswaprgb, fmtrgb;tfmtrgb, fmtbgr;tfmtbgr, fmtgray;tfmtgray',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put(dict(tswaprgb=FRAME, tfmtrgb=FRAME, tfmtbgr=FRAME, tfmtgray=FRAME))
            qin.put(False)

            frames   = qout.get()
            iswaprgb = (fswaprgb := frames['tswaprgb']).image
            ifmtrgb  = (ffmtrgb := frames['tfmtrgb']).image
            ifmtbgr  = (ffmtbgr := frames['tfmtbgr']).image
            ifmtgray = (ffmtgray := frames['tfmtgray']).image

            self.assertEqual(str(fswaprgb), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(ffmtrgb), 'Frame(320x200xRGB-ro)')
            self.assertEqual(str(ffmtbgr), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(ffmtgray), 'Frame(320x200xGRAY-ro)')

            self.assertTrue(np.array_equal(iswaprgb[0, 0], BLUEPX))
            self.assertTrue(np.array_equal(iswaprgb[0, 319], GREENPX))
            self.assertTrue(np.array_equal(iswaprgb[199, 0], REDPX))
            self.assertTrue(np.array_equal(iswaprgb[199, 319], WHITEPX))

            self.assertTrue(np.array_equal(ifmtrgb[0, 0], BLUEPX))
            self.assertTrue(np.array_equal(ifmtrgb[0, 319], GREENPX))
            self.assertTrue(np.array_equal(ifmtrgb[199, 0], REDPX))
            self.assertTrue(np.array_equal(ifmtrgb[199, 319], WHITEPX))

            self.assertTrue(np.array_equal(ifmtbgr[0, 0], REDPX))
            self.assertTrue(np.array_equal(ifmtbgr[0, 319], GREENPX))
            self.assertTrue(np.array_equal(ifmtbgr[199, 0], BLUEPX))
            self.assertTrue(np.array_equal(ifmtbgr[199, 319], WHITEPX))

            self.assertTrue(np.array_equal(ifmtgray[0, 0], GRAYREDPX))
            self.assertTrue(np.array_equal(ifmtgray[0, 319], GRAYGREENPX))
            self.assertTrue(np.array_equal(ifmtgray[199, 0], GRAYBLUEPX))
            self.assertTrue(np.array_equal(ifmtgray[199, 319], GRAYWHITEPX))

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_xforms_swap_fmt_from_gray(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs     = 'ipc://test-Q2F',
                outputs_jpg = False,  # because otherwise colors are not exact
                queue       = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources     = 'ipc://test-Q2F',
                outputs     = 'ipc://test-util',
                outputs_jpg = False,
                xforms      = 'swaprgb;tswaprgb, fmtrgb;tfmtrgb, fmtbgr;tfmtbgr, fmtgray;tfmtgray',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put(dict(tswaprgb=GRAYFRAME, tfmtrgb=GRAYFRAME, tfmtbgr=GRAYFRAME, tfmtgray=GRAYFRAME))
            qin.put(False)

            frames   = qout.get()
            iswaprgb = (fswaprgb := frames['tswaprgb']).image
            ifmtrgb  = (ffmtrgb := frames['tfmtrgb']).image
            ifmtbgr  = (ffmtbgr := frames['tfmtbgr']).image
            ifmtgray = (ffmtgray := frames['tfmtgray']).image

            self.assertEqual(str(fswaprgb), 'Frame(320x200xGRAY-ro)')
            self.assertEqual(str(ffmtrgb), 'Frame(320x200xRGB-ro)')
            self.assertEqual(str(ffmtbgr), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(ffmtgray), 'Frame(320x200xGRAY-ro)')

            self.assertTrue(np.array_equal(iswaprgb[0, 0], GRAYREDPX))
            self.assertTrue(np.array_equal(iswaprgb[0, 319], GRAYGREENPX))
            self.assertTrue(np.array_equal(iswaprgb[199, 0], GRAYBLUEPX))
            self.assertTrue(np.array_equal(iswaprgb[199, 319], GRAYWHITEPX))

            self.assertTrue(np.array_equal(ifmtrgb[0, 0], CH3GRAYREDPX))
            self.assertTrue(np.array_equal(ifmtrgb[0, 319], CH3GRAYGREENPX))
            self.assertTrue(np.array_equal(ifmtrgb[199, 0], CH3GRAYBLUEPX))
            self.assertTrue(np.array_equal(ifmtrgb[199, 319], CH3GRAYWHITEPX))

            self.assertTrue(np.array_equal(ifmtbgr[0, 0], CH3GRAYREDPX))
            self.assertTrue(np.array_equal(ifmtbgr[0, 319], CH3GRAYGREENPX))
            self.assertTrue(np.array_equal(ifmtbgr[199, 0], CH3GRAYBLUEPX))
            self.assertTrue(np.array_equal(ifmtbgr[199, 319], CH3GRAYWHITEPX))

            self.assertTrue(np.array_equal(ifmtgray[0, 0], GRAYREDPX))
            self.assertTrue(np.array_equal(ifmtgray[0, 319], GRAYGREENPX))
            self.assertTrue(np.array_equal(ifmtgray[199, 0], GRAYBLUEPX))
            self.assertTrue(np.array_equal(ifmtgray[199, 319], GRAYWHITEPX))

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_xforms_resize(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs     = 'ipc://test-Q2F',
                outputs_jpg = False,  # because otherwise colors are not exact
                queue       = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources     = 'ipc://test-Q2F',
                outputs     = 'ipc://test-util',
                outputs_jpg = False,
                xforms      = 'resize 160x100;t160x100, resize 160x120;t160x120, resize 160+120;t160p120, resize 640x400;t640x400',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put(dict(t160x100=FRAME, t160x120=FRAME, t160p120=FRAME, t640x400=FRAME))
            qin.put(False)

            frames   = qout.get()
            i160x100 = (f160x100 := frames['t160x100']).image
            i160x120 = (f160x120 := frames['t160x120']).image
            i160p120 = (f160p120 := frames['t160p120']).image
            i640x400 = (f640x400 := frames['t640x400']).image

            self.assertEqual(str(f160x100), 'Frame(160x100xBGR-ro)')
            self.assertEqual(str(f160x120), 'Frame(160x120xBGR-ro)')
            self.assertEqual(str(f160p120), 'Frame(160x120xBGR-ro)')
            self.assertEqual(str(f640x400), 'Frame(640x400xBGR-ro)')

            self.assertTrue(np.array_equal(i160x100[0, 0], REDPX))
            self.assertTrue(np.array_equal(i160x100[0, 159], GREENPX))
            self.assertTrue(np.array_equal(i160x100[99, 0], BLUEPX))
            self.assertTrue(np.array_equal(i160x100[99, 159], WHITEPX))

            self.assertTrue(np.array_equal(i160x120[0, 0], REDPX))
            self.assertTrue(np.array_equal(i160x120[0, 159], GREENPX))
            self.assertTrue(np.array_equal(i160x120[119, 0], BLUEPX))
            self.assertTrue(np.array_equal(i160x120[119, 159], WHITEPX))

            self.assertTrue(np.array_equal(i160p120[0, 0], REDPX))
            self.assertTrue(np.array_equal(i160p120[0, 159], GREENPX))
            self.assertTrue(np.array_equal(i160p120[119, 0], BLUEPX))
            self.assertTrue(np.array_equal(i160p120[119, 159], WHITEPX))

            self.assertTrue(np.array_equal(i640x400[0, 0], REDPX))
            self.assertTrue(np.array_equal(i640x400[0, 639], GREENPX))
            self.assertTrue(np.array_equal(i640x400[399, 0], BLUEPX))
            self.assertTrue(np.array_equal(i640x400[399, 639], WHITEPX))

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_xforms_maxsize(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs     = 'ipc://test-Q2F',
                outputs_jpg = False,  # because otherwise colors are not exact
                queue       = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources     = 'ipc://test-Q2F',
                outputs     = 'ipc://test-util',
                outputs_jpg = False,
                xforms      = 'maxsize 160x100;t160x100, maxsize 160x120;t160x120, maxsize 160+120;t160p120, maxsize 640x400;t640x400',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put(dict(t160x100=FRAME, t160x120=FRAME, t160p120=FRAME, t640x400=FRAME))
            qin.put(False)

            frames   = qout.get()
            i160x100 = (f160x100 := frames['t160x100']).image
            i160x120 = (f160x120 := frames['t160x120']).image
            i160p120 = (f160p120 := frames['t160p120']).image
            i640x400 = (f640x400 := frames['t640x400']).image

            self.assertEqual(str(f160x100), 'Frame(160x100xBGR-ro)')
            self.assertEqual(str(f160x120), 'Frame(160x100xBGR-ro)')
            self.assertEqual(str(f160p120), 'Frame(160x120xBGR-ro)')
            self.assertEqual(str(f640x400), 'Frame(320x200xBGR-ro)')

            self.assertTrue(np.array_equal(i160x100[0, 0], REDPX))
            self.assertTrue(np.array_equal(i160x100[0, 159], GREENPX))
            self.assertTrue(np.array_equal(i160x100[99, 0], BLUEPX))
            self.assertTrue(np.array_equal(i160x100[99, 159], WHITEPX))

            self.assertTrue(np.array_equal(i160x120[0, 0], REDPX))
            self.assertTrue(np.array_equal(i160x120[0, 159], GREENPX))
            self.assertTrue(np.array_equal(i160x120[99, 0], BLUEPX))
            self.assertTrue(np.array_equal(i160x120[99, 159], WHITEPX))

            self.assertTrue(np.array_equal(i160p120[0, 0], REDPX))
            self.assertTrue(np.array_equal(i160p120[0, 159], GREENPX))
            self.assertTrue(np.array_equal(i160p120[119, 0], BLUEPX))
            self.assertTrue(np.array_equal(i160p120[119, 159], WHITEPX))

            self.assertTrue(np.array_equal(i640x400[0, 0], REDPX))
            self.assertTrue(np.array_equal(i640x400[0, 319], GREENPX))
            self.assertTrue(np.array_equal(i640x400[199, 0], BLUEPX))
            self.assertTrue(np.array_equal(i640x400[199, 319], WHITEPX))

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_xforms_minsize(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs     = 'ipc://test-Q2F',
                outputs_jpg = False,  # because otherwise colors are not exact
                queue       = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources     = 'ipc://test-Q2F',
                outputs     = 'ipc://test-util',
                outputs_jpg = False,
                xforms      = 'minsize 160x100;t160x100, minsize 160x120;t160x120, minsize 160+120;t160p120, minsize 640x400;t640x400',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put(dict(t160x100=FRAME, t160x120=FRAME, t160p120=FRAME, t640x400=FRAME))
            qin.put(False)

            frames   = qout.get()
            i160x100 = (f160x100 := frames['t160x100']).image
            i160x120 = (f160x120 := frames['t160x120']).image
            i160p120 = (f160p120 := frames['t160p120']).image
            i640x400 = (f640x400 := frames['t640x400']).image

            self.assertEqual(str(f160x100), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(f160x120), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(f160p120), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(f640x400), 'Frame(640x400xBGR-ro)')

            self.assertTrue(np.array_equal(i160x100[0, 0], REDPX))
            self.assertTrue(np.array_equal(i160x100[0, 319], GREENPX))
            self.assertTrue(np.array_equal(i160x100[199, 0], BLUEPX))
            self.assertTrue(np.array_equal(i160x100[199, 319], WHITEPX))

            self.assertTrue(np.array_equal(i160x120[0, 0], REDPX))
            self.assertTrue(np.array_equal(i160x120[0, 319], GREENPX))
            self.assertTrue(np.array_equal(i160x120[199, 0], BLUEPX))
            self.assertTrue(np.array_equal(i160x120[199, 319], WHITEPX))

            self.assertTrue(np.array_equal(i160p120[0, 0], REDPX))
            self.assertTrue(np.array_equal(i160p120[0, 319], GREENPX))
            self.assertTrue(np.array_equal(i160p120[199, 0], BLUEPX))
            self.assertTrue(np.array_equal(i160p120[199, 319], WHITEPX))

            self.assertTrue(np.array_equal(i640x400[0, 0], REDPX))
            self.assertTrue(np.array_equal(i640x400[0, 639], GREENPX))
            self.assertTrue(np.array_equal(i640x400[399, 0], BLUEPX))
            self.assertTrue(np.array_equal(i640x400[399, 639], WHITEPX))

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_xforms_box(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs     = 'ipc://test-Q2F',
                outputs_jpg = False,  # because otherwise colors are not exact
                queue       = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources     = 'ipc://test-Q2F',
                outputs     = 'ipc://test-util',
                outputs_jpg = False,
                xforms      = 'box 0+0x.5x.5#888;tupperleft, box .5+0x.5x.5#888;tupperright, box 0+.5x.5x.5#888;tlowerleft, box .5+.5x.5x.5#888;tlowerright',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put(dict(tupperleft=FRAME, tupperright=FRAME, tlowerleft=FRAME, tlowerright=FRAME))
            qin.put(False)

            frames      = qout.get()
            iupperleft  = (fupperleft := frames['tupperleft']).image
            iupperright = (fupperright := frames['tupperright']).image
            ilowerleft  = (flowerleft := frames['tlowerleft']).image
            ilowerright = (flowerright := frames['tlowerright']).image

            self.assertEqual(str(fupperleft), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(fupperright), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(flowerleft), 'Frame(320x200xBGR-ro)')
            self.assertEqual(str(flowerright), 'Frame(320x200xBGR-ro)')

            self.assertTrue(np.array_equal(iupperleft[0, 0], GRAY8PX))
            self.assertTrue(np.array_equal(iupperleft[0, 319], GREENPX))
            self.assertTrue(np.array_equal(iupperleft[199, 0], BLUEPX))
            self.assertTrue(np.array_equal(iupperleft[199, 319], WHITEPX))

            self.assertTrue(np.array_equal(iupperright[0, 0], REDPX))
            self.assertTrue(np.array_equal(iupperright[0, 319], GRAY8PX))
            self.assertTrue(np.array_equal(iupperright[199, 0], BLUEPX))
            self.assertTrue(np.array_equal(iupperright[199, 319], WHITEPX))

            self.assertTrue(np.array_equal(ilowerleft[0, 0], REDPX))
            self.assertTrue(np.array_equal(ilowerleft[0, 319], GREENPX))
            self.assertTrue(np.array_equal(ilowerleft[199, 0], GRAY8PX))
            self.assertTrue(np.array_equal(ilowerleft[199, 319], WHITEPX))

            self.assertTrue(np.array_equal(ilowerright[0, 0], REDPX))
            self.assertTrue(np.array_equal(ilowerright[0, 319], GREENPX))
            self.assertTrue(np.array_equal(ilowerright[199, 0], BLUEPX))
            self.assertTrue(np.array_equal(ilowerright[199, 319], GRAY8PX))

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


if __name__ == '__main__':
    # mp.set_start_method('spawn')
    unittest.main()
