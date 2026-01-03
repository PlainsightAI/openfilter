"""Message / network handling. Also manages metrics.

Environment variables:
    OUTPUTS_JPG: If 'true'ish then encode output images to network as jpg, 'false'ish only send decoded, 'null' send
        as is as was passed from process().

    OUTPUTS_METRICS: If true then send metrics as '_metrics' on all zeromq outputs. If false then don't send. If string
        then is address of dedicated sender for metrics (will not be sent on normal senders).

    OUTPUTS_METRICS_PUSH: If 'true'ish then will always send metrics on dedicated metrics output regardless of if
        something is officially connected or not. Default true to support doubly ephemeral '??' listeners which are most
        likely the only things connected. Does not affect metrics on normal output channels.

    MQ_LOG: Default outputs logging if not explicitly specified, default 'none'.

    MQ_MSGID_SYNC: Whether to sync expected message IDs between outgoing and incoming zeromq message queues. Advanced
        thing, don't touch unless u know what u doing.
"""

import logging
import os
from json import loads as json_loads, dumps as json_dumps
from time import time
from typing import Callable

import numpy as np

from .frame import Frame
from .metrics import Metrics
from .utils import JSONType, json_getval, rndstr
from .zeromq import ZMQ_POLL_TIMEOUT as POLL_TIMEOUT_MS, is_zeromq_addr as is_mq_addr, ZMQMessage, ZMQSender, ZMQReceiver

__all__ = ['is_mq_addr', 'MQ', 'MQSender', 'MQReceiver']

logger = logging.getLogger(__name__)

OUTPUTS_JPG          = None if (_ := json_getval((os.getenv('OUTPUTS_JPG') or 'true').lower())) is None else bool(_)
OUTPUTS_METRICS      = _ if isinstance(_ := json_getval((os.getenv('OUTPUTS_METRICS') or 'true').lower()), bool) else str(_)
OUTPUTS_METRICS_PUSH = bool(json_getval((os.getenv('OUTPUTS_METRICS_PUSH') or 'true').lower()))
OUTPUTS_FILTER       = bool(json_getval((os.getenv('OUTPUTS_FILTER') or 'true').lower()))

MQ_LOG               = json_getval((os.getenv('MQ_LOG') or 'false').lower())
MQ_MSGID_SYNC        = bool(json_getval((os.getenv('MQ_MSGID_SYNC') or 'true').lower()))


class DummyMetrics:
    def __init__(self): self.uptime_t = time()
    def destroy(self): pass
    def incoming(self, frames=None): pass
    def outgoing(self, frames=None) -> dict[str, JSONType]:
        return {'ts': (t := time()), 'fps': 15.0, 'cpu': 0.0, 'mem': 0.0, 'uptime_count': int(t - self.uptime_t)}


class MQ:
    LOG_MAP = {'all': 'all', 'image': 'image', 'data': 'data', 'pretty': 'pretty', 'metrics': 'metrics', 'none': False,
        True: 'all', False: False}

    def __init__(self,
        srcs_n_topics: str | list[str | tuple[str, list[tuple[str, str]] | None]] = None,
        outs_bind:     str | list[str] | None = None,
        mq_id:         str | None = None,
        *,
        srcs_balance:  bool = False,
        srcs_low_lat:  bool | None = None,
        outs_balance:  bool = False,
        outs_required: list[str] | None = None,
        outs_jpg:      bool | None = None,
        outs_metrics:  str | bool | None = None,
        outs_filter:   bool | None = None,
        metrics_cb:    Callable[[dict], None] | None = None,
        on_exit_msg:   Callable[[str], None] | None = None,
        mq_log:        str | bool | None = None,
        mq_msgid_sync: bool | None = None,
    ):
        self.mq_id         = mq_id or rndstr(8)
        on_exit_msg_       = (lambda m: None) if on_exit_msg is None else (lambda m: on_exit_msg(m[0]))
        self.sender        = ZMQSender(outs_bind, self.mq_id, on_exit_msg_, outs_balance, outs_required) \
            if outs_bind else None
        self.receiver      = ZMQReceiver(srcs_n_topics, self.mq_id, on_exit_msg_, srcs_balance, srcs_low_lat) \
            if srcs_n_topics else None
        self.outs_jpg      = OUTPUTS_JPG if outs_jpg is None else outs_jpg
        self.outs_metrics  = outs_metrics = OUTPUTS_METRICS if outs_metrics is None else outs_metrics
        self.outs_filter   = OUTPUTS_FILTER if outs_filter is None else outs_filter
        self.metrics_cb    = metrics_cb
        self._frame_id     = -1  # frame ID counter for _filter topic
        self.mq_log        = MQ.LOG_MAP.get(MQ_LOG if mq_log is None else mq_log, False)
        self.mq_msgid_sync = MQ_MSGID_SYNC if mq_msgid_sync is None else mq_msgid_sync
        self.send_state    = None
        self.recv_state    = None

        if isinstance(outs_metrics, str):
            self.metrics_sender = ZMQSender(outs_metrics, self.mq_id, on_exit_msg_)
        else:
            self.metrics_sender = None

        self.metrics_ = Metrics() if outs_metrics or metrics_cb else DummyMetrics()
        self.metrics  = {'ts': time(), 'fps': 15.0, 'cpu': 0.0, 'mem': 0.0, 'uptime_count': 0}  # initial guaranteed-to-be-present metrics, for outside querying, not used here

    def _get_filter_data(self, frames: dict[str, Frame]) -> dict:
        """Extract frame IDs from frames or generate one. Returns data for _filter topic."""
        frame_ids = []
        for topic, frame in frames.items():
            if topic.startswith('_'):  # skip hidden topics
                continue
            if frame and frame.data and isinstance(frame.data, dict):
                if (meta := frame.data.get('meta')) and isinstance(meta, dict):
                    if (frame_id := meta.get('id')) is not None:
                        frame_ids.append(frame_id)
        if not frame_ids:
            self._frame_id += 1
            frame_ids = [self._frame_id]
        return {'id': frame_ids[0] if len(frame_ids) == 1 else frame_ids}

    def destroy(self):
        self.metrics_.destroy()

        if self.receiver:
            self.receiver.destroy()
            self.receiver = None

        if self.sender:
            self.sender.destroy()
            self.sender = None

        if self.metrics_sender:
            self.metrics_sender.destroy()
            self.metrics_sender = None

    def send_exit_msg(self, reason: str = ''):
        reason = [reason]

        if self.receiver is not None:
            self.receiver.send_oob(reason)

        if self.sender is not None:
            self.sender.send_oob(reason)

        if self.metrics_sender is not None:
            self.metrics_sender.send_oob(reason)

    def send(self, frames: dict[str, Frame] | Callable[[], dict[str, Frame] | None] | None, timeout: int | None = None) -> bool:
        def outgoing():
            nonlocal frames, metrics

            if callable(frames):
                frames = frames()

            metrics = self.metrics_.outgoing(frames)

            if log_text := Metrics.log_text(self.mq_log, frames, metrics):
                logger.info(f'{self.mq_id} - {log_text}')

            if frames is not None and (frames_metrics := frames.get('_metrics')) is not None:
                metrics = {**frames_metrics.data, **metrics}

            self.metrics = metrics  # store for outside querying

        def outgone():
            if self.metrics_sender is not None:  # send metrics to dedicated output
                self.metrics_sender.send(MQ.frames2topicmsgs({'_metrics': Frame(metrics)}), timeout=0, push=OUTPUTS_METRICS_PUSH)

            if self.metrics_cb:
                self.metrics_cb(metrics)

        def callback():  # callback instead of direct send in order to get metrics at time of actual send to have correct latency (at point of send)
            nonlocal frames, metrics

            outgoing()

            if frames is None:  # callback could have returned None
                return None

            if self.outs_metrics is True:
                frames = {**frames, '_metrics': Frame(metrics)}

            if self.outs_filter is True:
                frames = {**frames, '_filter': Frame(self._get_filter_data(frames))}

            return MQ.frames2topicmsgs(frames, self.outs_jpg)

        metrics = None

        if frames is None or self.sender is None:
            outgoing()
            outgone()

            return True

        if (recv_state := self.sender.send(callback, self.send_state if self.mq_msgid_sync else None, timeout)) is None:
            return False

        self.recv_state = recv_state if frames is not None else None  # callback might haver returned None in which case send returns same state as previously, we don't want this because it will set recv wrong and cause a newer message warning
        self.send_state = None  # in case we get another send() without a matching recv(), will increment msg_id otherwise message would be discarded

        if metrics is not None:  # could be None because nothing sent (NOT due to timeout but maybe msg_id invalidated as outdated by downstream) so callback not called and metrics not set
            outgone()  # we do this after sender.send() to give that data priority

        return True

    def recv(self, timeout: int | None = None) -> dict[str, Frame] | None:
        if self.receiver is None:
            return {}

        if (res := self.receiver.recv(self.recv_state if self.mq_msgid_sync else None, timeout)) is None:
            return None

        topicmsgs, self.send_state = res
        self.recv_state            = None  # we already used up this recv_state so set to None to increment automatically next time in case send() is not called to get new state

        self.metrics_.incoming(frames := MQ.topicmsgs2frames(topicmsgs))

        return frames

    @staticmethod
    def frames2topicmsgs(frames: dict[str, Frame], outs_jpg: bool | None = None) -> dict[str, ZMQMessage]:
        topicmsgs = {}

        for topic, frame in frames.items():
            data = json_dumps(frame.data, separators=(',', ':')).encode() if frame.data else None

            if not frame.has_image:
                msg = [None] if data is None else [None, data]

            else:
                enc  = 'jpg' if (do_jpg := frame.has_jpg if outs_jpg is None else outs_jpg) else 'raw'  # preferentially send jpg if is already encoded
                xtra = {'img': [frame.height, frame.width, frame.format, enc]}
                img  = frame.jpg if do_jpg else bytearray(memoryview(frame.image))
                msg  = [xtra, img] if data is None else [xtra, img, data]

            topicmsgs[topic] = msg

        return topicmsgs

    @staticmethod
    def topicmsgs2frames(topicmsgs: dict[str, ZMQMessage]) -> dict[str, Frame]:
        frames = {}

        for topic, msg in topicmsgs.items():
            xtra    = xtra['img'] if (xtra := msg[0]) else None
            dataidx = 2 if xtra else 1

            if (lmsg := len(msg)) > dataidx + 1:
                raise RuntimeError(f'incorrect number of messages: {lmsg}')

            data  = json_loads(msg[dataidx].decode()) if lmsg > dataidx else None
            frame = (
                Frame(data)
                if xtra is None else
                Frame(np.frombuffer(msg[1], np.uint8).reshape(xtra[:2] if xtra[2] == 'GRAY' else (xtra[0], xtra[1], 3)), data, xtra[2])
                if xtra[3] == 'raw' else
                Frame.from_jpg(msg[1], data, xtra[0], xtra[1], xtra[2])
            )

            frames[topic] = frame

        return frames


class MQSender(MQ):
    """Convenience class for sending only with metrics off by default (no incoming metrics possible)."""

    def __init__(self,
        outs_bind:     str | list[str] | None = None,
        mq_id:         str | None = None,
        *,
        outs_balance:  bool = False,
        outs_required: list[str] | None = None,
        outs_jpg:      bool | None = None,
        outs_metrics:  str | bool | None = False,
        metrics_cb:    Callable[[dict], None] | None = None,
        on_exit_msg:   Callable[[str], None] | None = None,
        mq_log:        str | bool | None = None,
    ):
        super().__init__(
            srcs_n_topics = None,
            outs_bind     = outs_bind,
            mq_id         = mq_id,
            outs_balance  = outs_balance,
            outs_required = outs_required,
            outs_jpg      = outs_jpg,
            outs_metrics  = outs_metrics,
            metrics_cb    = metrics_cb,
            on_exit_msg   = on_exit_msg,
            mq_log        = mq_log,
        )


class MQReceiver(MQ):
    """Convenience class for receiving only with no metrics possible."""

    def __init__(self,
        srcs_n_topics: str | list[str | tuple[str, list[tuple[str, str]] | None]] = None,
        mq_id:         str | None = None,
        *,
        srcs_balance:  bool = False,
        srcs_low_lat:  bool | None = None,
        on_exit_msg:   Callable[[str], None] | None = None,
    ):
        super().__init__(
            srcs_n_topics = srcs_n_topics,
            outs_bind     = None,
            mq_id         = mq_id,
            srcs_balance  = srcs_balance,
            srcs_low_lat  = srcs_low_lat,
            on_exit_msg   = on_exit_msg,
        )
