#!/usr/bin/env python

import logging
import os
import unittest
from queue import Queue
from threading import Event, Thread

import numpy as np

from openfilter.filter_runtime import Frame
from openfilter.filter_runtime.mq import MQ, MQSender, MQReceiver
from openfilter.filter_runtime.utils import setLogLevelGlobal

logger = logging.getLogger(__name__)

log_level = int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper()))

setLogLevelGlobal(log_level)


from helpers import ThreadMQSender


class ThreadMQReceiver(Thread):
    def __init__(self, *args, **kwargs):
        self.stop_evt = Event()
        self.queue    = Queue()

        super().__init__(target=self.thread_func, args=(args, kwargs), daemon=True)

        self.start()

    def destroy(self):
        self.stop_evt.set()
        self.join()

    def recv(self, timeout: int | None = None) -> dict[str, Frame]:  # timeout is in ms to match MQ
        return self.queue.get(timeout=None if timeout is None else timeout / 1000)

    def thread_func(self, args, kwargs):
        receiver = MQReceiver(*args, **kwargs)  # important to create in this thread

        while not self.stop_evt.is_set():
            if (frames := receiver.recv(10)) is not None:
                self.queue.put(frames)

        receiver.destroy()


class TestMQ(unittest.TestCase):
    def test_tmqsender_mqreciver(self):
        sender = ThreadMQSender('ipc://test-send', 'sender')

        try:
            receiver = MQReceiver('ipc://test-send', 'receiver')

            try:
                for i in range(5):
                    sender.send(frames := {'main': Frame({'count': i})})

                    self.assertEqual(receiver.recv(), frames)

            finally:
                receiver.destroy()

        finally:
            sender.destroy()


    def test_mqsender_tmqreciver(self):
        sender = MQSender('ipc://test-send', 'sender')

        try:
            receiver = ThreadMQReceiver('ipc://test-send', 'receiver')

            try:
                for i in range(5):
                    sender.send(frames := {'main': Frame({'count': i})})

                    self.assertEqual(receiver.recv(), frames)

            finally:
                receiver.destroy()

        finally:
            sender.destroy()


    def test_tmqsender_mq_tmqreceiver(self):
        sender = ThreadMQSender('ipc://test-send', 'sender')

        try:
            receiver = ThreadMQReceiver('ipc://test-mq', 'receiver')

            try:
                mq = MQ('ipc://test-send', 'ipc://test-mq', 'mq', outs_metrics=False)

                try:
                    for i in range(5):
                        sender.send(frames := {'main': Frame({'count': i})})
                        mq.send(mq.recv())

                        self.assertEqual(receiver.recv(), frames)

                finally:
                    mq.destroy()

            finally:
                receiver.destroy()

        finally:
            sender.destroy()


    def test_mq_double_send(self):
        sender = ThreadMQSender('ipc://test-send', 'sender')

        try:
            receiver = ThreadMQReceiver('ipc://test-mq', 'receiver')

            try:
                mq = MQ('ipc://test-send', 'ipc://test-mq', 'mq', outs_metrics=False)

                try:
                    sender.send(frames := {'main': Frame({'count': 0})})

                    frames_mq = mq.recv()

                    mq.send(frames_mq)
                    self.assertEqual(receiver.recv(), frames)

                    mq.send(frames_mq)
                    self.assertEqual(receiver.recv(200), frames)  # in case of incorrect msg_id handling between send and recv this will discard older message and get Empty exception from Queue

                finally:
                    mq.destroy()

            finally:
                receiver.destroy()

        finally:
            sender.destroy()


    def test_mq_double_recv(self):
        sender = ThreadMQSender('ipc://test-send', 'sender')

        try:
            receiver = ThreadMQReceiver('ipc://test-mq', 'receiver')

            try:
                mq = MQ('ipc://test-send', 'ipc://test-mq', 'mq', outs_metrics=False)

                try:
                    sender.send(frames := {'main': Frame({'count': 0})})

                    frames_mq = mq.recv()

                    mq.send(frames_mq)
                    self.assertEqual(receiver.recv(), frames)

                    sender.send(frames := {'main': Frame({'count': 1})})

                    self.assertEqual(mq.recv(), frames)
                    self.assertEqual(mq.recv_state, None)  # this needs to be set to None after second recv because otherwise 'received newer message' warnings will be logged when they should not be

                    sender.send(frames := {'main': Frame({'count': 2})})

                    self.assertEqual(mq.recv(), frames)

                finally:
                    mq.destroy()

            finally:
                receiver.destroy()

        finally:
            sender.destroy()



class TestPairByTsPlumbing(unittest.TestCase):
    """The production path of the capture timestamp `ZMQReceiver.pair_by_ts` pairs on.

    `TestPairByTs` in test_zeromq.py writes `{'ts': ...}` into the per-message `xtra` dict by hand, one layer
    below this, so on its own it proves nothing about how a real frame's `meta['ts']` gets there. These cover
    the two steps it skips: `MQ._frame_ts` reading the frame, `MQ.frames2topicmsgs` lifting it into `xtra`, and
    the config field reaching the receiver that uses it.
    """

    @staticmethod
    def _img_frame(data):
        return Frame(np.zeros((2, 2, 3), np.uint8), data, 'BGR')

    def test_frame_ts_reads_a_numeric_meta_ts(self):
        self.assertEqual(MQ._frame_ts(self._img_frame({'meta': {'ts': 1738000000.25}})), 1738000000.25)
        self.assertEqual(MQ._frame_ts(self._img_frame({'meta': {'ts': 1738000000}})), 1738000000)  # an int is a time too

    def test_frame_ts_rejects_every_other_shape(self):
        """`frame.data` is arbitrary user JSON, so each of these is something a filter is free to produce. None
        of them is a timestamp, and none of them may raise on the send path.
        """

        for data in (
            {},                                 # no meta at all
            {'meta': None},                     # meta present and empty
            {'meta': 'ts=1'},                   # meta is not a dict
            {'meta': ['ts', 1]},                # meta is not a dict, again
            {'meta': {}},                       # meta is a dict with no ts
            {'meta': {'ts': None}},             # ts present and empty
            {'meta': {'ts': '1738000000.25'}},  # ts as a string, which json round trips just fine
            {'meta': {'ts': True}},             # bool is an int subclass, and 1.0 seconds past the epoch is not a capture time
            {'meta': {'ts': False}},
            {'meta': {'ts': {'sec': 1}}},
        ):
            with self.subTest(data=data):
                self.assertIsNone(MQ._frame_ts(self._img_frame(data)))

    def test_frames2topicmsgs_lifts_the_ts_into_xtra(self):
        topicmsgs = MQ.frames2topicmsgs({'main': self._img_frame({'meta': {'ts': 1738000000.25}})}, outs_jpg=False)
        xtra      = topicmsgs['main'][0]

        self.assertEqual(xtra['ts'], 1738000000.25)
        self.assertEqual(xtra['img'], [2, 2, 'BGR', 'raw'])  # and the field the old wire format carries is untouched

    def test_frames2topicmsgs_omits_ts_when_there_is_none(self):
        topicmsgs = MQ.frames2topicmsgs({'main': self._img_frame({'meta': {'ts': 'nope'}})}, outs_jpg=False)

        self.assertNotIn('ts', topicmsgs['main'][0])

    def test_a_frame_with_no_image_keeps_its_wire_shape(self):
        """The lift is inside the has_image branch on purpose: an imageless frame sends `msg[0] = None`, and a
        reader of the old format must not start finding a dict there.
        """

        topicmsgs = MQ.frames2topicmsgs({'main': Frame({'meta': {'ts': 1738000000.25}})}, outs_jpg=False)

        self.assertIsNone(topicmsgs['main'][0])

    def test_the_lifted_ts_does_not_disturb_the_round_trip(self):
        """`topicmsgs2frames` reads `xtra['img']`, which now shares the dict with 'ts'. The frame that comes back
        out is the frame that went in, timestamp included, because 'ts' travels in the data payload as well.
        """

        frames = {'main': self._img_frame({'meta': {'ts': 1738000000.25}, 'count': 7})}
        back   = MQ.topicmsgs2frames(MQ.frames2topicmsgs(frames, outs_jpg=False))

        self.assertEqual(back['main'].data, {'meta': {'ts': 1738000000.25}, 'count': 7})
        self.assertEqual(back['main'].shape, (2, 2, 3))

    def test_the_config_fields_reach_the_receiver(self):
        """FILTER_SOURCES_PAIR_BY_TS / FILTER_SOURCES_TS_TOLERANCE -> config -> MQReceiver -> ZMQReceiver.

        The `Filter` hop in the middle (`srcs_pair_ts=` / `srcs_ts_tol=` in Filter.create_mq) is not covered
        here; it needs a running filter.
        """

        from openfilter.filter_runtime.config import FilterConfigBase

        env = {'FILTER_SOURCES_PAIR_BY_TS': 'true', 'FILTER_SOURCES_TS_TOLERANCE': '0.05'}
        old = {k: os.environ.get(k) for k in env}

        os.environ.update(env)

        try:
            config = FilterConfigBase()

            self.assertIs(config.sources_pair_by_ts, True)
            self.assertEqual(config.sources_ts_tolerance, 0.05)

        finally:
            for k, v in old.items():
                if v is None:
                    del os.environ[k]
                else:
                    os.environ[k] = v

        receiver = MQReceiver(['ipc://test-pair-ts-1', 'ipc://test-pair-ts-2'], 'receiver',
            srcs_pair_ts=config.sources_pair_by_ts, srcs_ts_tol=config.sources_ts_tolerance)

        try:
            self.assertIs(receiver.receiver.pair_by_ts, True)
            self.assertEqual(receiver.receiver.pair_ts_tol, 0.05)
            self.assertIs(receiver.receiver.pair_ts, True)  # two synchronized sources, so it is actually on

        finally:
            receiver.destroy()

    def test_the_tolerance_is_rejected_when_negative(self):
        """A negative tolerance can only come from a config, so the config path is where it has to be caught."""

        with self.assertRaises(ValueError):
            MQReceiver('ipc://test-pair-ts-3', 'receiver', srcs_pair_ts=True, srcs_ts_tol=-0.05)


if __name__ == '__main__':
    unittest.main()
