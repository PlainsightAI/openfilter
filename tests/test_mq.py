#!/usr/bin/env python

import logging
import os
import unittest
from queue import Queue
from threading import Event, Thread

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



if __name__ == '__main__':
    unittest.main()
