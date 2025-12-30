#!/usr/bin/env python

import gc
import logging
import multiprocessing as mp
import os
import unittest
from multiprocessing import Queue
from multiprocessing.queues import Empty
from time import sleep, time
from pathlib import Path
import tempfile

import numpy as np

from openfilter.filter_runtime import Filter, FilterConfig, Frame, FilterContext
from openfilter.filter_runtime.test import RunnerContext, FiltersToQueue, QueueToFilters
from openfilter.filter_runtime.utils import setLogLevelGlobal
from openfilter.filter_runtime.filters.util import Util

logger = logging.getLogger(__name__)

log_level = int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper()))

setLogLevelGlobal(log_level)

getdatas = lambda q, t=5: {t: f.data for t, f in q.get(True, t).items()}


class FilterFromQueue(Filter):
    def setup(self, config):
        if (start_sleep := config.start_sleep):
            sleep(start_sleep)

    def process(self, frames):
        if (frames := self.config.queue.get()) is None:
            self.exit()

        sleep(self.config.sleep or 0)

        return {t: Frame(d) for t, d in frames.items()}


class FilterToQueue(Filter):
    def setup(self, config):
        if (start_sleep := config.start_sleep):
            sleep(start_sleep)

    def process(self, frames):
        self.config.queue.put(frames)

        sleep(self.config.sleep or 0)


class SendCountOrNone(Filter):
    """Filter that returns None for odd counts and Frame for even counts."""
    def setup(self, config):
        self.count = -1

    def process(self, frames):
        if (count := self.count + 1) == 4:
            self.exit()

        self.count = count

        return None if count & 1 else Frame({'count': count})


class SendCountOrNoneCB(Filter):
    """Filter that returns a callback with None for odd counts and Frame for even counts."""
    def setup(self, config):
        self.count = -1

    def process(self, frames):
        if (count := self.count + 1) == 4:
            self.exit()

        self.count = count

        return lambda: None if count & 1 else Frame({'count': count})


class MyFilter(Filter):
    """Filter that puts frames to a queue and returns them."""
    def process(self, frames):
        self.config.queue.put(frames)

        return frames


class TestFilterOld(unittest.TestCase):
    """Old doesn't mean invalid, just that it was written before some features that would have made these tests simpler
     and different if written today. Many of these are only 99.9% deterministic because of network entropy so if they
     fail treat them as a screen rather than definitive invalidation and try again."""

    def setUp(self):
        self._queues = []

    def tearDown(self):
        # Clean up all queues to prevent file descriptor leaks
        for queue in self._queues:
            try:
                queue.close()
                queue.join_thread()
            except:
                pass
        # Force garbage collection to clean up file descriptors
        gc.collect()

    def _track_queue(self, queue):
        """Track a queue for cleanup in tearDown."""
        self._queues.append(queue)
        return queue

    def test_topo_simple(self):
        qout = Queue(); [qout.put({'main': {'count': i}}) for i in range(5)]; qout.put(None)

        retcodes = Filter.run_multi([
            (FilterFromQueue, dict(outputs='tcp://*', queue=qout, sleep_start=0.5, sleep=0.05)),
            (FilterToQueue,   dict(sources='tcp://127.0.0.1', queue=(qin := Queue()))),
        ], exit_time=10)

        self.assertEqual(retcodes, [0, 0])

        self.assertEqual({t: f.data for t, f in qin.get(0).items()}, {'main': {'count': 0}})
        self.assertEqual({t: f.data for t, f in qin.get(0).items()}, {'main': {'count': 1}})
        self.assertEqual({t: f.data for t, f in qin.get(0).items()}, {'main': {'count': 2}})
        self.assertEqual({t: f.data for t, f in qin.get(0).items()}, {'main': {'count': 3}})
        self.assertEqual({t: f.data for t, f in qin.get(0).items()}, {'main': {'count': 4}})


    def test_topo_tee(self):
        qout = Queue(); [qout.put({'main': {'count': i}}) for i in range(5)]; qout.put(None)

        retcodes = Filter.run_multi([
            (FilterFromQueue, dict(outputs='tcp://*', outputs_required='1, 2', queue=qout, sleep_start=0.5, sleep=0.5)),  # the sleeps because might miss published messages at startup
            (FilterToQueue,   dict(id='1', sources='tcp://127.0.0.1', queue=(qin1 := Queue()))),
            (FilterToQueue,   dict(id='2', sources='tcp://127.0.0.1', queue=(qin2 := Queue()))),
        ], exit_time=10)

        self.assertEqual(retcodes, [0, 0, 0])

        self.assertEqual({t: f.data for t, f in qin1.get(0).items()}, {'main': {'count': 0}})
        self.assertEqual({t: f.data for t, f in qin1.get(0).items()}, {'main': {'count': 1}})
        self.assertEqual({t: f.data for t, f in qin1.get(0).items()}, {'main': {'count': 2}})
        self.assertEqual({t: f.data for t, f in qin1.get(0).items()}, {'main': {'count': 3}})
        self.assertEqual({t: f.data for t, f in qin1.get(0).items()}, {'main': {'count': 4}})

        self.assertEqual({t: f.data for t, f in qin2.get(0).items()}, {'main': {'count': 0}})
        self.assertEqual({t: f.data for t, f in qin2.get(0).items()}, {'main': {'count': 1}})
        self.assertEqual({t: f.data for t, f in qin2.get(0).items()}, {'main': {'count': 2}})
        self.assertEqual({t: f.data for t, f in qin2.get(0).items()}, {'main': {'count': 3}})
        self.assertEqual({t: f.data for t, f in qin2.get(0).items()}, {'main': {'count': 4}})


    def test_topo_tee_rejoin(self):
        qout = Queue(); [qout.put({'main': {'count': i}}) for i in range(5)]; qout.put(None)

        retcodes = Filter.run_multi([
            (FilterFromQueue, dict(id='src', outputs='tcp://*', outputs_required='1, 2', queue=qout, sleep_start=0.5, sleep=0.5)),  # the sleeps because might miss published messages at startup
            (Util,            dict(id='1',   sources='tcp://127.0.0.1', outputs='tcp://*:5552', outputs_required='out')),
            (Util,            dict(id='2',   sources='tcp://127.0.0.1', outputs='tcp://*:5554', outputs_required='out')),
            (FilterToQueue,   dict(id='out', sources='tcp://127.0.0.1:5552, tcp://127.0.0.1:5554;>other', queue=(queue := Queue()))),
        ], exit_time=10)

        self.assertEqual(retcodes, [0, 0, 0, 0])

        self.assertEqual({t: f.data for t, f in queue.get(0).items()}, {'main': {'count': 0}, 'other': {'count': 0}})
        self.assertEqual({t: f.data for t, f in queue.get(0).items()}, {'main': {'count': 1}, 'other': {'count': 1}})
        self.assertEqual({t: f.data for t, f in queue.get(0).items()}, {'main': {'count': 2}, 'other': {'count': 2}})
        self.assertEqual({t: f.data for t, f in queue.get(0).items()}, {'main': {'count': 3}, 'other': {'count': 3}})
        self.assertEqual({t: f.data for t, f in queue.get(0).items()}, {'main': {'count': 4}, 'other': {'count': 4}})


    def test_topo_ephemeral_simple(self):
        qout = Queue(); [qout.put({'main': {'count': i}}) for i in range(8)]; qout.put(None)

        retcodes = Filter.run_multi([
            (FilterFromQueue, dict(outputs='tcp://*', queue=qout, sleep=0.01)),
            (FilterToQueue, dict(sources='tcp://127.0.0.1?', queue=(queue := Queue()))),
        ], exit_time=10)

        self.assertEqual(retcodes, [0, 0])

        self.assertEqual({t: f.data for t, f in queue.get(0).items()}, {'main': {'count': 0}})
        self.assertEqual({t: f.data for t, f in queue.get(0).items()}, {'main': {'count': 1}})
        self.assertEqual({t: f.data for t, f in queue.get(0).items()}, {'main': {'count': 2}})
        self.assertEqual({t: f.data for t, f in queue.get(0).items()}, {'main': {'count': 3}})
        self.assertEqual({t: f.data for t, f in queue.get(0).items()}, {'main': {'count': 4}})


    def test_topo_ephemeral_tee(self):
        qout = Queue(); [qout.put({'main': {'count': i}, **({} if i & 1 else {'other': {'count': i}})}) for i in range(5)]; qout.put(None)

        retcodes = Filter.run_multi([
            (FilterFromQueue, dict(outputs='tcp://*', queue=qout, start_sleep=0.1, sleep=0.05)),
            (FilterToQueue,   dict(sources='tcp://127.0.0.1', queue=(qin1 := Queue()))),
            (FilterToQueue,   dict(sources='tcp://127.0.0.1?;other', queue=(qin2 := Queue()))),
        ], exit_time=10)

        self.assertEqual(retcodes, [0, 0, 0])

        self.assertEqual({t: f.data for t, f in qin1.get(0).items()}, {'main': {'count': 0}, 'other': {'count': 0}})
        self.assertEqual({t: f.data for t, f in qin1.get(0).items()}, {'main': {'count': 1}})
        self.assertEqual({t: f.data for t, f in qin1.get(0).items()}, {'main': {'count': 2}, 'other': {'count': 2}})
        self.assertEqual({t: f.data for t, f in qin1.get(0).items()}, {'main': {'count': 3}})
        self.assertEqual({t: f.data for t, f in qin1.get(0).items()}, {'main': {'count': 4}, 'other': {'count': 4}})

        self.assertEqual({t: f.data for t, f in qin2.get(0).items()}, {'other': {'count': 0}})
        self.assertEqual({t: f.data for t, f in qin2.get(0).items()}, {'other': {'count': 2}})
        self.assertEqual({t: f.data for t, f in qin2.get(0).items()}, {'other': {'count': 4}})


    # WARNING! `prop_exit` and `stop_exit` are temporary hacks for exit control in this case, they should be made more determiniztic.
    def test_topo_ephemeral_tee_rejoin(self):
        qout = Queue(); [qout.put({'main': {'count': i}, **({} if i & 1 or i > 4 else {'other': {'count': i}})}) for i in range(8)]; qout.put(None)

        retcodes = Filter.run_multi([
            (FilterFromQueue, dict(id='src', outputs='tcp://*', outputs_required='u0, u1', queue=qout, start_sleep=0.1, sleep=0.08)),
            (Util,            dict(id='u0',  sources='tcp://127.0.0.1;', outputs='tcp://*:5552', outputs_required='dst')),
            (Util,            dict(id='u1',  sources='tcp://127.0.0.1?;other', outputs='tcp://*:5554', outputs_required='dst')),
            (FilterToQueue,   dict(id='dst', sources='tcp://127.0.0.1:5552, tcp://127.0.0.1:5554?', queue=(qin := Queue()))),
        ], prop_exit='none', stop_exit='all', exit_time=10)

        self.assertEqual(retcodes, [0, 0, 0, 0])

        msgs = set()

        for _ in range(9):
            try:
                msgs.update(f'{t}{f.data["count"]}' for t, f in qin.get(0).items())
            except Empty:
                pass

        self.assertEqual(msgs, set(('main0', 'main5', 'main4', 'main7', 'main3', 'main6', 'other0', 'main1', 'other2', 'other4', 'main2')))


    def test_topo_ephemeral_join_step(self):
        qout1, qout2 = Queue(), Queue()

        runner = Filter.Runner([
            (FilterFromQueue, dict(id='inc', outputs='tcp://*:5550', queue=qout1, start_sleep=0.1, sleep=0.02)),
            (FilterFromQueue, dict(id='ine', outputs='tcp://*:5552', queue=qout2, start_sleep=0.1, sleep=0.02)),
            (FilterToQueue,   dict(id='out', sources='tcp://127.0.0.1:5550, tcp://127.0.0.1:5552?', queue=(qin := Queue()))),
        ], prop_exit='all', stop_exit='all', sig_stop=False, exit_time=10)

        try:
            qout1.put(d := {'main': {'val': 0}})

            sleep(0.05)

            self.assertIs(runner.step(), False)
            self.assertEqual(getdatas(qin), d)

            qout2.put(e := {'other': {'val': 1}})

            sleep(0.05)

            self.assertIs(runner.step(), False)
            self.assertRaises(Empty, lambda: getdatas(qin, 0.05))

            qout1.put(d := {'main': {'val': 1}})

            sleep(0.05)

            self.assertIs(runner.step(), False)
            self.assertEqual(getdatas(qin), {**d, **e})

            qout1.put(d := {'main': {'val': 2}})

            sleep(0.05)

            self.assertIs(runner.step(), False)
            self.assertEqual(getdatas(qin), d)

            qout2.put(e := {'other': {'val': 3}})

            sleep(0.05)

            self.assertIs(runner.step(), False)
            self.assertRaises(Empty, lambda: getdatas(qin, 0.05))

            qout1.put(d := {'main': {'val': 3}})

            sleep(0.05)

            self.assertIs(runner.step(), False)
            self.assertEqual(getdatas(qin), {**d, **e})

            qout2.put(e := {'other': {'val': 4}})

            sleep(0.05)

            self.assertIs(runner.step(), False)
            self.assertRaises(Empty, lambda: getdatas(qin, 0.05))

            qout1.put(d := {'main': {'val': 4}})

            sleep(0.05)

            self.assertIs(runner.step(), False)
            self.assertEqual(getdatas(qin), {**d, **e})

            qout1.put(None)  # tell them nicely to stop
            qout2.put(None)
            self.assertEqual(runner.step(), [0, 0, 0])

        finally:
            runner.stop()


    def test_topo_doubly_ephemeral_tee_step(self):
        runner1 = Filter.Runner([
            (FilterFromQueue, dict(outputs='tcp://*', queue=(qout := Queue()), start_sleep=0.1)),
            (FilterToQueue,   dict(sources='tcp://127.0.0.1??', queue=(qin1 := Queue()))),
        ], exit_time=10)

        try:
            sleep(0.2)

            qout.put(d := {'main': {'val': 0}})
            self.assertIs(runner1.step(), False)

            sleep(0.1)

            self.assertRaises(Empty, lambda: getdatas(qin1, 0.1))

            runner2 = Filter.Runner([
                (FilterToQueue, dict(sources='tcp://127.0.0.1?', queue=(qin2 := Queue()))),
            ], exit_time=10)

            try:
                self.assertIs(runner2.step(), False)

                sleep(0.1)

                self.assertEqual(getdatas(qin2), d)
                self.assertEqual(getdatas(qin1), d)

                qout.put(d := {'main': {'val': 1}})
                self.assertIs(runner1.step(), False)
                self.assertIs(runner2.step(), False)

                sleep(0.1)

                self.assertEqual(getdatas(qin2), d)
                self.assertEqual(getdatas(qin1), d)

                qout.put(None)  # tell it nicely to stop
                self.assertEqual(runner2.step(), [0])

            finally:
                runner2.stop()

            self.assertEqual(runner1.step(), [0, 0])

        finally:
            runner1.stop()


    def test_topo_subscribe_wildcard_all_step(self):
        runner = Filter.Runner([
            (FilterFromQueue, dict(id='inc', outputs='tcp://*:5550', queue=(qout := Queue()), start_sleep=0.1, sleep=0.01)),
            (FilterToQueue,   dict(id='out', sources='tcp://127.0.0.1:5550;*', queue=(qin := Queue()))),
        ], prop_exit='all', stop_exit='all', sig_stop=False, exit_time=10)

        try:
            qout.put(d := {'main': {'val': 0}})
            self.assertIs(runner.step(), False)
            r = getdatas(qin)
            self.assertEqual(r['main'], d['main'])
            self.assertEqual(set(r), set(('main', '_metrics', '_filter')))

            qout.put(d := {'main': {'val': 1}})
            self.assertIs(runner.step(), False)
            r = getdatas(qin)
            self.assertEqual(r['main'], d['main'])
            self.assertEqual(set(r), set(('main', '_metrics', '_filter')))

            qout.put(d := {'main': {'val': 2}})
            self.assertIs(runner.step(), False)
            r = getdatas(qin)
            self.assertEqual(r['main'], d['main'])
            self.assertEqual(set(r), set(('main', '_metrics', '_filter')))

            qout.put(None)  # tell it nicely to stop
            self.assertEqual(runner.step(), [0, 0])

        finally:
            runner.stop()


    def test_topo_balance_step(self):
        runner = Filter.Runner([
            (FilterFromQueue, dict(id='src', outputs='tcp://*:5550, tcp://*:5552, tcp://*:5554', outputs_balance=True, queue=(qout := Queue()), start_sleep=0.1)),
            (MyFilter,        dict(id='worker1', sources='tcp://localhost:5550', outputs='tcp://*:5560', queue=(qworker1 := Queue()))),
            (MyFilter,        dict(id='worker2', sources='tcp://localhost:5552', outputs='tcp://*:5562', queue=(qworker2 := Queue()))),
            (MyFilter,        dict(id='worker3', sources='tcp://localhost:5554', outputs='tcp://*:5564', queue=(qworker3 := Queue()))),
            (FilterToQueue,   dict(id='out', sources='tcp://127.0.0.1:5560, tcp://127.0.0.1:5562, tcp://127.0.0.1:5564', sources_balance=True, queue=(qin := Queue()))),
        ], prop_exit='all', stop_exit='all', sig_stop=False, exit_time=10)

        last_qworker = None

        def getworkerdatas():  # because order is not guaranteed
            nonlocal last_qworker

            self.assertEqual((qe1 := qworker1.empty()) + (qe2 := qworker2.empty()) + (qe3 := qworker3.empty()), 2)

            qworker = qworker1 if qe2 and qe3 else qworker2 if qe1 and qe3 else qworker3

            self.assertIsNot(qworker, last_qworker)

            last_qworker = qworker

            return getdatas(qworker)

        try:
            qout.put(d := {'main': {'val': 0}})
            self.assertIs(runner.step(), False)
            self.assertIs(runner.step(), False)

            sleep(0.05)

            self.assertEqual(getdatas(qin), d)
            self.assertEqual(getworkerdatas(), d)
            # self.assertEqual(getdatas(qworker1), d)
            # self.assertTrue(qworker2.empty())
            # self.assertTrue(qworker3.empty())

            qout.put(d := {'main': {'val': 1}})
            self.assertIs(runner.step(), False)
            self.assertIs(runner.step(), False)

            sleep(0.05)

            self.assertEqual(getdatas(qin), d)
            self.assertEqual(getworkerdatas(), d)
            # self.assertEqual(getdatas(qworker2), d)
            # self.assertTrue(qworker1.empty())
            # self.assertTrue(qworker3.empty())

            qout.put(d := {'main': {'val': 2}})
            self.assertIs(runner.step(), False)
            self.assertIs(runner.step(), False)

            sleep(0.05)

            self.assertEqual(getdatas(qin), d)
            self.assertEqual(getworkerdatas(), d)
            # self.assertEqual(getdatas(qworker3), d)
            # self.assertTrue(qworker1.empty())
            # self.assertTrue(qworker2.empty())

            qout.put(d := {'main': {'val': 3}})
            self.assertIs(runner.step(), False)
            self.assertIs(runner.step(), False)

            sleep(0.05)

            self.assertEqual(getdatas(qin), d)
            self.assertEqual(getworkerdatas(), d)
            # self.assertEqual(getdatas(qworker1), d)
            # self.assertTrue(qworker2.empty())
            # self.assertTrue(qworker3.empty())

            qout.put(d := {'main': {'val': 4}})
            self.assertIs(runner.step(), False)
            self.assertIs(runner.step(), False)

            sleep(0.05)

            self.assertEqual(getdatas(qin), d)
            self.assertEqual(getworkerdatas(), d)
            # self.assertEqual(getdatas(qworker2), d)
            # self.assertTrue(qworker1.empty())
            # self.assertTrue(qworker3.empty())

            qout.put(d := {'main': {'val': 5}})
            self.assertIs(runner.step(), False)
            self.assertIs(runner.step(), False)

            sleep(0.05)

            self.assertEqual(getdatas(qin), d)
            self.assertEqual(getworkerdatas(), d)
            # self.assertEqual(getdatas(qworker3), d)
            # self.assertTrue(qworker1.empty())
            # self.assertTrue(qworker2.empty())

            qout.put(d := {'main': {'val': 6}})
            self.assertIs(runner.step(), False)
            self.assertIs(runner.step(), False)

            sleep(0.05)

            self.assertEqual(getdatas(qin), d)
            self.assertEqual(getworkerdatas(), d)
            # self.assertEqual(getdatas(qworker1), d)
            # self.assertTrue(qworker2.empty())
            # self.assertTrue(qworker3.empty())

            qout.put(d := {'main': {'val': 7}})
            self.assertIs(runner.step(), False)
            self.assertIs(runner.step(), False)

            sleep(0.05)

            self.assertEqual(getdatas(qin), d)
            self.assertEqual(getworkerdatas(), d)
            # self.assertEqual(getdatas(qworker2), d)
            # self.assertTrue(qworker1.empty())
            # self.assertTrue(qworker3.empty())

            qout.put(d := {'main': {'val': 8}})
            self.assertIs(runner.step(), False)
            self.assertIs(runner.step(), False)

            sleep(0.05)

            self.assertEqual(getdatas(qin), d)
            self.assertEqual(getworkerdatas(), d)
            # self.assertEqual(getdatas(qworker3), d)
            # self.assertTrue(qworker1.empty())
            # self.assertTrue(qworker2.empty())

            qout.put(None)  # tell it nicely to stop
            self.assertEqual(runner.step(), [0, 0, 0, 0, 0])

        finally:
            runner.stop()


class TestFilter(unittest.TestCase):
    def tearDown(self):
        # Force garbage collection to clean up file descriptors
        gc.collect()

    def test_normalize_config(self):
        scfg = dict(
            id                  = 'filter',
            sources             = 'tcp://localhost:5552;main, ipc://myipcin;other',
            sources_balance     = True,
            sources_timeout     = 100,
            sources_low_latency = True,
            outputs             = 'tcp://*:5554; ipc://myipcout',
            outputs_balance     = True,
            outputs_timeout     = 200,
            outputs_required    = 'filter1, filter2',
            outputs_metrics     = 'tcp://*:5554',
            outputs_jpg         = False,
            exit_after          = '@2024-09-17T06:26:20.189123-04:00',
            environment         = 'production',
            log_path            = 'logs',
            metrics_interval    = 120,
            extra_metrics       = [('my_int_metric', 1), ('my_str_metric', 'str')],
            mq_log              = 'pretty',
            mq_msgid_sync       = False,
        )

        dcfg = FilterConfig(
            id                  = 'filter',
            sources             = ['tcp://localhost:5552;main', 'ipc://myipcin;other'],
            sources_balance     = True,
            sources_timeout     = 100,
            sources_low_latency = True,
            outputs             = ['tcp://*:5554; ipc://myipcout'],
            outputs_balance     = True,
            outputs_timeout     = 200,
            outputs_required    = ['filter1', 'filter2'],
            outputs_metrics     = 'tcp://*:5554',
            outputs_jpg         = False,
            exit_after          = '@2024-09-17T06:26:20.189123-04:00',
            environment         = 'production',
            log_path            = 'logs',
            metrics_interval    = 120,
            extra_metrics       = {'my_int_metric': 1, 'my_str_metric': 'str'},
            mq_log              = 'pretty',
            mq_msgid_sync       = False,
        )

        ncfg1 = Filter.normalize_config(scfg)
        ncfg2 = Filter.normalize_config(ncfg1)

        self.assertIsInstance(ncfg1, FilterConfig)
        self.assertIsInstance(ncfg2, FilterConfig)
        self.assertEqual(ncfg1, dcfg)
        self.assertEqual(ncfg1, ncfg2)


    def test_process_return_none(self):
        with RunnerContext([
            (SendCountOrNone, dict(
                outputs = 'ipc://test-filter',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-filter',
                queue   = (queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], [queue], exit_time=3) as runner:

            self.assertTrue(queue.get()['main'].data == {'count': 0})
            self.assertTrue(queue.get()['main'].data == {'count': 2})
            self.assertFalse(queue.get())
            self.assertEqual(runner.wait(), [0, 0])


    def test_process_return_none_callback(self):
        with RunnerContext([
            (SendCountOrNoneCB, dict(
                outputs = 'ipc://test-filter',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-filter',
                queue   = (queue := FiltersToQueue.Queue()).child_queue,
            )),
        ], [queue], exit_time=3) as runner:

            self.assertTrue(queue.get()['main'].data == {'count': 0})
            self.assertTrue(queue.get()['main'].data == {'count': 2})
            self.assertFalse(queue.get())
            self.assertEqual(runner.wait(), [0, 0])


    def test_metrics_topic_subscribe(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs = 'ipc://test-Q2F',
                queue   = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources = 'ipc://test-Q2F',
                outputs = 'ipc://test-util',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util;_metrics',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put({'main': Frame(np.zeros((100, 160, 3)), {'meta': {'ts': time()}}, 'BGR')})
            qin.put(False)

            frames = qout.get()

            self.assertTrue(metrics := frames.get('_metrics'))

            keys = set(metrics.data.keys())

            self.assertIn('ts', keys)  # we don't test for correctness, just that they are there
            self.assertIn('fps', keys)
            self.assertIn('cpu', keys)
            self.assertIn('mem', keys)
            self.assertIn('lat_in', keys)
            self.assertIn('lat_out', keys)
            self.assertIn('uptime_count', keys)
            self.assertIn('frame_count', keys)
            self.assertIn('megapx_count', keys)

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_metrics_topic_wildcard(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs = 'ipc://test-Q2F',
                queue   = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources = 'ipc://test-Q2F',
                outputs = 'ipc://test-util',
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util;*',
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put({'main': Frame(np.zeros((100, 160, 3)), {'meta': {'ts': time()}}, 'BGR')})
            qin.put(False)

            frames = qout.get()

            self.assertTrue(metrics := frames.get('_metrics'))

            keys = set(metrics.data.keys())

            self.assertIn('ts', keys)  # we don't test for correctness, just that they are there
            self.assertIn('fps', keys)
            self.assertIn('cpu', keys)
            self.assertIn('mem', keys)
            self.assertIn('lat_in', keys)
            self.assertIn('lat_out', keys)
            self.assertIn('uptime_count', keys)
            self.assertIn('frame_count', keys)
            self.assertIn('megapx_count', keys)

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_metrics_dedicated_sender(self):
        with RunnerContext([
            (QueueToFilters, dict(
                outputs = 'ipc://test-Q2F',
                queue   = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources         = 'ipc://test-Q2F',
                outputs         = 'ipc://test-util',
                outputs_metrics = 'ipc://test-util-metrics'
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util;*',
                queue   = (qout1 := FiltersToQueue.Queue()).child_queue,
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util-metrics;*',
                queue   = (qout2 := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout1, qout2], exit_time=3) as runner:

            qin.put({'main': Frame(np.zeros((100, 160, 3)), {'meta': {'ts': time()}}, 'BGR')})
            qin.put(False)

            frames1 = qout1.get()
            frames2 = qout2.get()

            self.assertEqual(set(frames1), {'main', '_filter'})
            self.assertEqual(list(frames2), ['_metrics'])

            keys = set(frames2['_metrics'].data.keys())

            self.assertIn('ts', keys)  # we don't test for correctness, just that they are there
            self.assertIn('fps', keys)
            self.assertIn('cpu', keys)
            self.assertIn('mem', keys)
            self.assertIn('lat_in', keys)
            self.assertIn('lat_out', keys)
            self.assertIn('uptime_count', keys)
            self.assertIn('frame_count', keys)
            self.assertIn('megapx_count', keys)

            self.assertFalse(qout1.get())
            self.assertFalse(qout2.get())
            self.assertEqual(runner.wait(), [0, 0, 0, 0])


    def test_filter_context_initialization(self):
        """Test FilterContext initialization and basic functionality."""
        # Reset the context to ensure clean state
        FilterContext._data = {}
        
        # Test initialization
        FilterContext.init()
        
        # Verify that data is populated
        self.assertIsInstance(FilterContext._data, dict)
        self.assertIn('filter_version', FilterContext._data)
        self.assertIn('version_sha', FilterContext._data)
        self.assertIn('models', FilterContext._data)
        self.assertIn('resource_bundle_version', FilterContext._data)
        self.assertIn('openfilter_version', FilterContext._data)
        
        # Test that subsequent calls don't reinitialize
        original_data = FilterContext._data.copy()
        FilterContext.init()
        self.assertEqual(FilterContext._data, original_data)


    def test_filter_context_get_method(self):
        """Test FilterContext.get() method."""
        FilterContext.init()
        
        # Test getting existing keys
        self.assertIsInstance(FilterContext.get('filter_version'), (str, type(None)))
        self.assertIsInstance(FilterContext.get('resource_bundle_version'), (str, type(None)))
        self.assertIsInstance(FilterContext.get('version_sha'), (str, type(None)))
        self.assertIsInstance(FilterContext.get('models'), dict)
        self.assertIsInstance(FilterContext.get('openfilter_version'), (str, type(None)))
        
        # Test getting non-existent key
        self.assertIsNone(FilterContext.get('non_existent_key'))


    def test_filter_context_as_dict_method(self):
        """Test FilterContext.as_dict() method."""
        FilterContext.init()
        
        context_dict = FilterContext.as_dict()
        
        self.assertIsInstance(context_dict, dict)
        self.assertIn('filter_version', context_dict)
        self.assertIn('resource_bundle_version', context_dict)
        self.assertIn('version_sha', context_dict)
        self.assertIn('models', context_dict)
        self.assertIn('openfilter_version', context_dict)
        
        # Verify it's a copy, not a reference
        self.assertIsNot(context_dict, FilterContext._data)


    def test_filter_context_read_file_method(self):
        """Test FilterContext._read_file() static method."""
        # Test with non-existent file
        result = FilterContext._read_file("non_existent_file.txt")
        self.assertIsNone(result)
        
        # Test with existing file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content\n")
            temp_file = f.name
        
        try:
            result = FilterContext._read_file(temp_file)
            self.assertEqual(result, "test content")
        finally:
            os.unlink(temp_file)


    def test_filter_context_read_models_toml_method(self):
        """Test FilterContext._read_models_toml() static method."""
        # Test with non-existent models.toml
        result = FilterContext._read_models_toml()
        self.assertEqual(result, {})
        
        # Test with valid models.toml
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.toml', delete=False) as f:
            toml_content = """
[model1]
version = "1.0.0"
path = "/path/to/model1"

[model2]
version = "2.0.0"
path = "/path/to/model2"

[model3]
version = "3.0.0"
"""
            f.write(toml_content.encode())
            temp_file = f.name
        
        try:
            # Temporarily rename the temp file to models.toml in current directory
            original_models_toml = Path("models.toml")
            if original_models_toml.exists():
                original_models_toml.rename("models.toml.backup")
            
            Path(temp_file).rename("models.toml")
            
            try:
                result = FilterContext._read_models_toml()
                
                self.assertIn('model1', result)
                self.assertIn('model2', result)
                self.assertIn('model3', result)
                
                self.assertEqual(result['model1']['version'], "1.0.0")
                self.assertEqual(result['model1']['path'], "/path/to/model1")
                self.assertEqual(result['model2']['version'], "2.0.0")
                self.assertEqual(result['model2']['path'], "/path/to/model2")
                self.assertEqual(result['model3']['version'], "3.0.0")
                self.assertEqual(result['model3']['path'], "No path")
                
            finally:
                # Restore original models.toml if it existed
                if Path("models.toml").exists():
                    Path("models.toml").unlink()
                if Path("models.toml.backup").exists():
                    Path("models.toml.backup").rename("models.toml")
        except:
            # Clean up temp file if rename failed
            if Path(temp_file).exists():
                Path(temp_file).unlink()
            raise


    def test_filter_context_read_models_toml_invalid_format(self):
        """Test FilterContext._read_models_toml() with invalid TOML format."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.toml', delete=False) as f:
            invalid_toml = """
[model1]
version = "1.0.0"

[model2]
# Missing version field

[model3]
invalid_field = "value"
"""
            f.write(invalid_toml.encode())
            temp_file = f.name
        
        try:
            # Temporarily rename the temp file to models.toml in current directory
            original_models_toml = Path("models.toml")
            if original_models_toml.exists():
                original_models_toml.rename("models.toml.backup")
            
            Path(temp_file).rename("models.toml")
            
            try:
                result = FilterContext._read_models_toml()
                
                # Should only include model1 since it has a version field
                self.assertIn('model1', result)
                self.assertNotIn('model2', result)
                self.assertNotIn('model3', result)
                
            finally:
                # Restore original models.toml if it existed
                if Path("models.toml").exists():
                    Path("models.toml").unlink()
                if Path("models.toml.backup").exists():
                    Path("models.toml.backup").rename("models.toml")
        except:
            # Clean up temp file if rename failed
            if Path(temp_file).exists():
                Path(temp_file).unlink()
            raise


    def test_filter_context_log_method(self):
        """Test FilterContext.log() method."""
        FilterContext.init()
        
        # This test mainly verifies that the log method doesn't raise exceptions
        # The actual logging output is hard to test without mocking
        try:
            FilterContext.log()
        except Exception as e:
            self.fail(f"FilterContext.log() raised an exception: {e}")


    def test_filter_context_with_actual_files(self):
        """Test FilterContext with actual version files if they exist."""
        FilterContext.init()
        
        # Test that we can get context data
        context_data = FilterContext.as_dict()
        
        # Verify structure
        self.assertIsInstance(context_data['filter_version'], (str, type(None)))
        self.assertIsInstance(context_data['resource_bundle_version'], (str, type(None)))
        self.assertIsInstance(context_data['version_sha'], (str, type(None)))
        self.assertIsInstance(context_data['models'], dict)
        self.assertIsInstance(context_data['openfilter_version'], (str, type(None)))
        
        # If VERSION file exists, test that it's read correctly
        version_file = Path("VERSION")
        if version_file.exists():
            expected_version = version_file.read_text().strip()
            self.assertEqual(context_data['filter_version'], expected_version)
        
        # If RESOURCE_BUNDLE_VERSION file exists, test that it's read correctly
        resource_bundle_version_file = Path("RESOURCE_BUNDLE_VERSION")
        if resource_bundle_version_file.exists():
            expected_resource_bundle_version = resource_bundle_version_file.read_text().strip()
            self.assertEqual(context_data['resource_bundle_version'], expected_resource_bundle_version)
        
        # If VERSION_SHA file exists, test that it's read correctly
        version_sha_file = Path("VERSION_SHA")
        if version_sha_file.exists():
            expected_sha = version_sha_file.read_text().strip()
            self.assertEqual(context_data['version_sha'], expected_sha)


    def test_filter_context_error_handling(self):
        """Test FilterContext error handling for file operations."""
        # Test with a file that can't be read (directory)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = FilterContext._read_file(temp_dir)
            self.assertIsNone(result)
        
        # Test with a file that has permission issues
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test")
            temp_file = f.name
        
        try:
            # Make file read-only for owner
            os.chmod(temp_file, 0o000)
            
            # Should handle permission error gracefully
            result = FilterContext._read_file(temp_file)
            self.assertIsNone(result)
            
        finally:
            # Restore permissions and clean up
            os.chmod(temp_file, 0o644)
            os.unlink(temp_file)


    def test_filter_context_get_context_classmethod(self):
        """Test Filter.get_context() class method."""
        context_data = Filter.get_context()

        self.assertIsInstance(context_data, dict)
        self.assertIn('filter_version', context_data)
        self.assertIn('resource_bundle_version', context_data)
        self.assertIn('version_sha', context_data)
        self.assertIn('models', context_data)
        self.assertIn('openfilter_version', context_data)


    def test_filter_topic_with_frame_id_from_meta(self):
        """Test _filter topic is emitted with frame IDs extracted from meta.id."""
        with RunnerContext([
            (QueueToFilters, dict(
                outputs = 'ipc://test-Q2F-filter',
                queue   = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources        = 'ipc://test-Q2F-filter',
                outputs        = 'ipc://test-util-filter',
                outputs_filter = True,  # enable _filter topic
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util-filter;*',  # wildcard to get _filter topic
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            # Send frame with meta.id
            qin.put({'main': Frame(np.zeros((100, 160, 3)), {'meta': {'id': 42, 'ts': time()}}, 'BGR')})
            qin.put(False)

            frames = qout.get()

            # Verify _filter topic is present
            self.assertTrue(filter_frame := frames.get('_filter'))
            self.assertIsNotNone(filter_frame.data)

            # Verify id contains the input frame ID
            self.assertIn('id', filter_frame.data)
            self.assertEqual(filter_frame.data['id'], 42)

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_filter_topic_generates_frame_id_when_no_meta(self):
        """Test _filter topic generates frame IDs when input has no meta.id."""
        with RunnerContext([
            (QueueToFilters, dict(
                outputs = 'ipc://test-Q2F-filter2',
                queue   = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources        = 'ipc://test-Q2F-filter2',
                outputs        = 'ipc://test-util-filter2',
                outputs_filter = True,  # enable _filter topic
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util-filter2;*',  # wildcard to get _filter topic
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            # Send frames without meta.id - should generate sequential IDs
            qin.put({'main': Frame(np.zeros((100, 160, 3)), {}, 'BGR')})
            frames1 = qout.get()

            qin.put({'main': Frame(np.zeros((100, 160, 3)), {}, 'BGR')})
            frames2 = qout.get()

            qin.put(False)

            # Verify both frames have _filter topic with sequential IDs
            self.assertTrue(filter1 := frames1.get('_filter'))
            self.assertTrue(filter2 := frames2.get('_filter'))

            self.assertEqual(filter1.data['id'], 0)
            self.assertEqual(filter2.data['id'], 1)

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_filter_topic_enabled_by_default(self):
        """Test _filter topic is emitted by default when outputs_filter is not set."""
        with RunnerContext([
            (QueueToFilters, dict(
                outputs = 'ipc://test-Q2F-filter3',
                queue   = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources = 'ipc://test-Q2F-filter3',
                outputs = 'ipc://test-util-filter3',
                # outputs_filter not set - should be enabled by default
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util-filter3;*',  # wildcard to get all topics
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put({'main': Frame(np.zeros((100, 160, 3)), {'meta': {'id': 1, 'ts': time()}}, 'BGR')})
            qin.put(False)

            frames = qout.get()

            # Verify _filter topic IS present (enabled by default)
            self.assertIsNotNone(frames.get('_filter'))
            self.assertEqual(frames.get('_filter').data['id'], 1)

            # _metrics should also be present
            self.assertIsNotNone(frames.get('_metrics'))

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


    def test_filter_topic_subscribe_explicit(self):
        """Test subscribing explicitly to _filter topic."""
        with RunnerContext([
            (QueueToFilters, dict(
                outputs = 'ipc://test-Q2F-filter4',
                queue   = (qin := mp.Queue()),
            )),
            (Util, dict(
                sources        = 'ipc://test-Q2F-filter4',
                outputs        = 'ipc://test-util-filter4',
                outputs_filter = True,
            )),
            (FiltersToQueue, dict(
                sources = 'ipc://test-util-filter4;_filter',  # explicit _filter subscription
                queue   = (qout := FiltersToQueue.Queue()).child_queue,
            )),
        ], [qin, qout], exit_time=3) as runner:

            qin.put({'main': Frame(np.zeros((100, 160, 3)), {'meta': {'id': 99, 'ts': time()}}, 'BGR')})
            qin.put(False)

            frames = qout.get()

            # Should only have _filter topic (explicit subscription)
            self.assertTrue(filter_frame := frames.get('_filter'))
            self.assertEqual(filter_frame.data['id'], 99)

            # Should NOT have main or _metrics (not subscribed)
            self.assertIsNone(frames.get('main'))

            self.assertFalse(qout.get())
            self.assertEqual(runner.wait(), [0, 0, 0])


if __name__ == '__main__':
    unittest.main()
