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

import contextlib
import logging
import os
from json import loads as json_loads, dumps as json_dumps
from time import time, time_ns
from typing import Callable

import numpy as np
from opentelemetry import context as otel_context, trace as otel_trace

from openfilter.observability.tracing import register_hop_tracer as _register_hop_tracer

from .frame import Frame
from .metrics import Metrics
from .shm_transport import SHMAttachCache, SHMPool, shm_enabled
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
        tracer:        "otel_trace.Tracer | None" = None,
    ):
        self.mq_id         = mq_id or rndstr(8)
        # Cached tracer for hop spans (mq.send / mq.recv and children). Passed in by
        # Filter.init when telemetry is on; None when tracing is disabled so the hot
        # path short-circuits before allocating any Span objects.
        self.tracer        = tracer
        # Register (or clear) the module-level hop tracer used by the codec /
        # kernel sub-span helper (maybe_start_span). Doing this unconditionally
        # — including the None case — prevents a torn-down tracer from a previous
        # MQ instance from being reused; the helper still no-ops in the
        # no-tracer case because maybe_start_span first checks is_recording() on
        # the current span, which is False without an outer mq.send / mq.recv.
        _register_hop_tracer(tracer)
        # Per-frame trace context extracted from the last received envelope. Filter
        # consults this to parent the {FilterClass}.process span so that downstream
        # spans on this filter join the producer's per-frame distributed trace.
        self.recv_parent_ctx = None
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

        self.shm_pool  = SHMPool(prefix=f'of-{self.mq_id}') if (shm_enabled() and self.sender is not None) else None
        self.shm_cache = SHMAttachCache() if (shm_enabled() and self.receiver is not None) else None

    @staticmethod
    def _hop_attrs(frames: dict[str, Frame] | None) -> dict:
        """Best-effort extraction of frame.id / frame.format / topic for hop span attrs.

        Hidden topics (``_metrics``, ``_filter``) are ignored — the hop span describes
        the user-visible frames, and metrics-only sends should still produce a span
        (just without frame.id / frame.format) so the trace shows the hop happened.
        """
        attrs: dict = {}
        if not frames:
            return attrs
        topics: list[str] = []
        frame_id = None
        fmt = None
        for topic, frame in frames.items():
            if topic.startswith('_'):
                continue
            topics.append(topic)
            if frame_id is None and frame is not None and isinstance(frame.data, dict):
                meta = frame.data.get('meta')
                if isinstance(meta, dict) and meta.get('id') is not None:
                    frame_id = meta['id']
            if fmt is None and frame is not None and getattr(frame, 'format', None):
                fmt = frame.format
        if topics:
            attrs['topic'] = topics[0] if len(topics) == 1 else ','.join(topics)
        if frame_id is not None:
            attrs['frame.id'] = str(frame_id)
        if fmt:
            attrs['frame.format'] = fmt
        return attrs

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

        if self.shm_pool is not None:
            self.shm_pool.destroy()
            self.shm_pool = None
        if self.shm_cache is not None:
            self.shm_cache.destroy()
            self.shm_cache = None

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

        tracer = self.tracer

        def callback():  # callback instead of direct send in order to get metrics at time of actual send to have correct latency (at point of send)
            nonlocal frames, metrics

            outgoing()

            if frames is None:  # callback could have returned None
                return None

            if self.outs_metrics is True:
                frames = {**frames, '_metrics': Frame(metrics)}

            if self.outs_filter is True:
                frames = {**frames, '_filter': Frame(self._get_filter_data(frames))}

            # frame.serialize wraps frames2topicmsgs so the trace breaks out CPU /
            # codec cost (frame.encode_jpg fires as a child here when jpg transport
            # is selected) from the kernel cost (zmq.send_multipart, sibling).
            ser_cm = tracer.start_as_current_span("frame.serialize") if tracer else contextlib.nullcontext()
            with ser_cm:
                return MQ.frames2topicmsgs(frames, self.outs_jpg, pool=self.shm_pool)

        metrics = None

        if frames is None or self.sender is None:
            outgoing()
            outgone()

            return True

        # mq.send hop span wraps the entire ZMQSender.send call (which is what blocks
        # for downstream readiness, runs the callback, and pushes bytes on the wire).
        # The trace context active here is what gets injected into the outgoing envelope
        # by ZMQSender.send_maybe via opentelemetry.propagate.inject, so the downstream
        # filter's mq.recv / {Filter}.process spans nest under THIS span across the wire.
        send_cm = tracer.start_as_current_span("mq.send", attributes=MQ._hop_attrs(frames if isinstance(frames, dict) else None)) if tracer else contextlib.nullcontext()
        with send_cm as send_span:
            recv_state = self.sender.send(callback, self.send_state if self.mq_msgid_sync else None, timeout)
            # Gate on `tracer` rather than `send_span is not None` — the latter happens to
            # work today because contextlib.nullcontext() yields None, but a future refactor
            # to nullcontext(some_obj) would silently break the guard.
            if tracer:
                # Stamp payload_bytes once we know what actually got pushed on the wire,
                # and re-stamp frame attrs in case the callback resolved a lazy frames
                # source (frames was a Callable when send() was invoked).
                send_span.set_attribute("payload_bytes", int(self.sender.last_send_bytes))
                if isinstance(frames, dict):
                    for k, v in MQ._hop_attrs(frames).items():
                        send_span.set_attribute(k, v)
                send_span.set_attribute("mq.id", self.mq_id)

        if recv_state is None:
            return False

        self.recv_state = recv_state if frames is not None else None  # callback might haver returned None in which case send returns same state as previously, we don't want this because it will set recv wrong and cause a newer message warning
        self.send_state = None  # in case we get another send() without a matching recv(), will increment msg_id otherwise message would be discarded

        if metrics is not None:  # could be None because nothing sent (NOT due to timeout but maybe msg_id invalidated as outdated by downstream) so callback not called and metrics not set
            outgone()  # we do this after sender.send() to give that data priority

        return True

    def recv(self, timeout: int | None = None) -> dict[str, Frame] | None:
        if self.receiver is None:
            self.recv_parent_ctx = None
            return {}

        tracer = self.tracer
        # Wall-clock start of the retroactive mq.recv span. The matching end_time is
        # captured AFTER the deserialize work completes (further down) so the span
        # window encloses its frame.deserialize child rather than ending right after
        # the recv() syscall returns. Includes poll wait time — operationally useful
        # because an idle filter shows up as a long mq.recv with almost no
        # zmq.recv_multipart sibling time, immediately distinguishable from a slow
        # kernel copy (long mq.recv AND long zmq.recv_multipart).
        # Only pay for time_ns() when tracing is on — cheap, but adds up at 30 fps per hop.
        t_recv_start = time_ns() if tracer is not None else 0
        res = self.receiver.recv(self.recv_state if self.mq_msgid_sync else None, timeout)
        if res is None:
            # Symmetric with the `self.receiver is None` early return: clear so a
            # caller (or a future read) can't see a stale per-frame context from a
            # previous successful recv(). Currently benign because callers don't read
            # recv_parent_ctx after recv() returns None, but the asymmetry was a trap
            # waiting for a future maintainer.
            self.recv_parent_ctx = None
            return None

        topicmsgs, self.send_state = res
        self.recv_state            = None  # we already used up this recv_state so set to None to increment automatically next time in case send() is not called to get new state

        # Stash extracted W3C trace context so Filter._process_frames_single can use it
        # as the parent context for the {FilterClass}.process span, joining this filter's
        # per-frame work onto the producer's distributed trace.
        #
        # Fan-in caveat: when this receiver subscribes to multiple upstream senders, the
        # last envelope parsed during the recv() call wins (see ZMQReceiver.recv_once
        # `last_extracted_ctx = otel_extract(env)`). Frames produced by other upstreams in
        # the same recv batch end up parented under that one arbitrary upstream's mq.send
        # context. Joining all of them properly would require span links across producer
        # traces, which is intentionally out of scope for PLAT-866 — flagging here so a
        # future maintainer investigating "incomplete fan-in traces" finds the explanation.
        extracted_ctx = self.receiver.last_extracted_ctx
        self.recv_parent_ctx = extracted_ctx

        if tracer is None:
            self.metrics_.incoming(frames := MQ.topicmsgs2frames(topicmsgs, cache=self.shm_cache))
            return frames

        # Retroactive mq.recv span — created with the extracted context as parent so the
        # consumer-side hop nests under the producer's mq.send span across the wire.
        recv_attrs = {"mq.id": self.mq_id}
        recv_span = tracer.start_span(
            "mq.recv",
            context=extracted_ctx,
            start_time=t_recv_start,
            attributes=recv_attrs,
        )
        try:
            recv_ctx = otel_trace.set_span_in_context(recv_span)

            # zmq.recv_multipart sibling span captures cumulative kernel-copy cost across
            # whatever recv_multipart syscalls fired inside the wait/poll loop. Its
            # duration minus the (zero) sibling spans inside is the raw kernel cost —
            # the diagnostic signal that motivates work like FILTER-419 (SHM transport).
            # Skip the span when ZMQReceiver didn't observe a recv_multipart that updated
            # its timing state (e.g., a degenerate path where only special / OOB messages
            # arrived) rather than emit a zero-duration span pinned to t_recv_start.
            zmq_t_start = self.receiver.last_recv_t_start_ns
            zmq_t_end   = self.receiver.last_recv_t_end_ns
            zmq_bytes   = int(self.receiver.last_recv_bytes)
            if zmq_t_start and zmq_t_end:
                zmq_span = tracer.start_span(
                    "zmq.recv_multipart",
                    context=recv_ctx,
                    start_time=zmq_t_start,
                    attributes={"payload_bytes": zmq_bytes},
                )
                try:
                    zmq_span.end(end_time=zmq_t_end)
                except Exception:  # pragma: no cover - end() shouldn't raise
                    pass

            # frame.deserialize wraps topicmsgs2frames; frame.decode_jpg fires as a child
            # only when the jpg transport is in use (via maybe_start_span inside Frame.decode).
            # Use start_as_current_span here so Frame.decode's maybe_start_span sees a recording
            # parent and creates the codec child span correctly.
            token = otel_context.attach(recv_ctx)
            try:
                with tracer.start_as_current_span("frame.deserialize"):
                    self.metrics_.incoming(frames := MQ.topicmsgs2frames(topicmsgs, cache=self.shm_cache))
            finally:
                otel_context.detach(token)

            # Stamp frame-derived attributes onto the recv span now that we have decoded frames.
            for k, v in MQ._hop_attrs(frames).items():
                recv_span.set_attribute(k, v)
            recv_span.set_attribute("payload_bytes", zmq_bytes)
        except Exception as e:
            # tracer.start_span + manual .end() does NOT auto-record exceptions the way
            # `with start_as_current_span` does, so without this the span would close
            # successfully but land in Cloud Trace as a normal-looking recv with no error
            # indication — making genuine deserialize bugs hide as missing data, not
            # failures.
            recv_span.record_exception(e)
            recv_span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR, str(e)))
            raise
        finally:
            # End the span post-deserialize and inside finally so an exception in
            # topicmsgs2frames / metrics_.incoming can't drop the span on the floor.
            # End time is captured here (not at the t_recv_end snapshot above) so the
            # span window encloses its child frame.deserialize, instead of ending before
            # its own children — t_recv_end is captured pre-deserialize and would
            # produce a span whose children appear to live outside its time window.
            recv_span.end(end_time=time_ns())
        return frames

    @staticmethod
    def frames2topicmsgs(frames: dict[str, Frame], outs_jpg: bool | None = None, *, pool: SHMPool | None = None) -> dict[str, ZMQMessage]:
        topicmsgs = {}

        for topic, frame in frames.items():
            data = json_dumps(frame.data, separators=(',', ':')).encode() if frame.data else None

            if not frame.has_image:
                msg = [None] if data is None else [None, data]

            else:
                enc  = 'jpg' if (do_jpg := frame.has_jpg if outs_jpg is None else outs_jpg) else 'raw'  # preferentially send jpg if is already encoded
                xtra = {'img': [frame.height, frame.width, frame.format, enc]}

                if pool is not None and not do_jpg:
                    shm_name, shm_nbytes = pool.put(memoryview(frame.image).cast('B'))
                    xtra['shm'] = [shm_name, shm_nbytes]
                    msg = [xtra] if data is None else [xtra, data]
                else:
                    img = frame.jpg if do_jpg else memoryview(frame.image).cast('B')
                    msg = [xtra, img] if data is None else [xtra, img, data]

            topicmsgs[topic] = msg

        return topicmsgs

    @staticmethod
    def topicmsgs2frames(topicmsgs: dict[str, ZMQMessage], *, cache: SHMAttachCache | None = None) -> dict[str, Frame]:
        frames = {}

        for topic, msg in topicmsgs.items():
            xtra_dict = msg[0]
            xtra      = xtra_dict['img'] if xtra_dict else None
            shm_info  = xtra_dict.get('shm') if xtra_dict else None

            if shm_info is not None:
                if cache is None:
                    raise RuntimeError('received SHM frame reference but SHM is not enabled on this receiver')
                shm_name, shm_nbytes = shm_info
                shm     = cache.get(shm_name)
                shape   = xtra[:2] if xtra[2] == 'GRAY' else (xtra[0], xtra[1], 3)
                image   = np.frombuffer(shm.buf, np.uint8, count=shm_nbytes).reshape(shape)
                dataidx = 1
            else:
                dataidx = 2 if xtra else 1

            if (lmsg := len(msg)) > dataidx + 1:
                raise RuntimeError(f'incorrect number of messages: {lmsg}')

            # Payload parts may be raw bytes (metrics/OOB path) or zmq.Frame
            # (the main recv path uses copy=False). bytes(...) handles both;
            # the data JSON is small so the copy is negligible.
            data = json_loads(bytes(msg[dataidx]).decode()) if lmsg > dataidx else None

            if shm_info is not None:
                # SHM slots are recycled by the sender; downstream mutation would corrupt live buffers.
                image.flags.writeable = False
                frame = Frame(image, data, xtra[2])
            elif xtra is None:
                frame = Frame(data)
            elif xtra[3] == 'raw':
                image = np.frombuffer(msg[1], np.uint8).reshape(xtra[:2] if xtra[2] == 'GRAY' else (xtra[0], xtra[1], 3))
                image.flags.writeable = False
                frame = Frame(image, data, xtra[2])
            else:
                frame = Frame.from_jpg(msg[1], data, xtra[0], xtra[1], xtra[2])

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
        tracer:        "otel_trace.Tracer | None" = None,
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
            tracer        = tracer,
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
        tracer:        "otel_trace.Tracer | None" = None,
    ):
        super().__init__(
            srcs_n_topics = srcs_n_topics,
            outs_bind     = None,
            mq_id         = mq_id,
            srcs_balance  = srcs_balance,
            srcs_low_lat  = srcs_low_lat,
            on_exit_msg   = on_exit_msg,
            tracer        = tracer,
        )
