"""Shared test helpers and fixtures."""

from queue import Queue, Empty
from threading import Thread, Event

from openfilter.filter_runtime import Frame
from openfilter.filter_runtime.mq import MQSender


def assert_empty(q, settle=0.5):
    """Assert that *q* receives no data within *settle* seconds.

    Blocks for *settle* seconds waiting on the queue. Returns
    if the queue stays empty, raises AssertionError otherwise.
    """
    try:
        data = q.get(True, settle)
    except Empty:
        return
    raise AssertionError(f'expected queue to be empty, but got: {data}')


class ThreadMQSender(Thread):
    """Threaded MQ sender for tests — ZMQ sender blocks until a subscriber
    issues a request, so it must run in its own thread."""

    def __init__(self, *args, **kwargs):
        self.stop_evt = Event()
        self.queue = Queue()
        super().__init__(target=self._run, args=(args, kwargs), daemon=True)
        self.start()

    def destroy(self):
        self.queue.put(False)
        self.stop_evt.set()
        self.join(timeout=5)

    def send(self, frames: dict[str, Frame] | None = None):
        self.queue.put(frames)

    def _run(self, args, kwargs):
        sender = MQSender(*args, **kwargs)
        frames = False
        while not self.stop_evt.is_set():
            if frames is False:
                try:
                    frames = self.queue.get(timeout=0.01)
                except Empty:
                    continue
                if frames is False:
                    break
            if sender.send(frames, 10):
                frames = False
        sender.destroy()
