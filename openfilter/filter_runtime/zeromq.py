"""Send and receive over ZeroMQ with topics and flow control. Outside code can connect to PUB sockets to read same data
as filters, they just need to understand the multi-message header and how the image and data are sent. The image is
either raw or jpg encoded, or not present at all, as specified by the first message. The data portion may also not be
present, in which case it implies an empty {} dict. The first message of the bunch is a short header with the topic,
msg_id, server_id, list of all topics the server publishes and the dimensions and format of image (if present). See code
for details.

Ephemeral channels:

These are sources specified by the RECEIVER by appending a '?' character to the address, e.g. 'tcp://127.0.0.1?'. This
is NOT the same thing as the '?' in a URL. An ephemeral channel is meant for a filter to subscribe to a single explicit
topic and receive messages and not hold up the rest of the system while it does long processing on those messages. It
is possible to subscribe to more than one topic, or even subscrive to all (no explicit topic). In this case messages
will not be returned until all of a given block have been received.

Message delivery is not guaranteed and messages in a sequence may be skipped if more than one next message comes in
while the filter is processing. Message IDs are not checked but order is most likely preserved.

If you have an ephemeral filter and you wish to rejoin its output with the normal synchronous stream of messages then
you MUST mark the source coming from the ephemeral filter pipeline at the point of the rejoin as ephemeral as well,
otherwise bad things will happen (messages will start queueing up in buffers and eventually throughput will stall, after
using up lots of memory). Further downstream of the join everything normal (except frame times and ids won't match).
Example:

    FilterA: outputs ...

    FilterB: sources=['tcp://FilterA']
    FilterC: sources=['tcp://FilterB']

    FilterD: sources=['tcp://FilterA?']
    FilterE: sources=['tcp://FilterD']

    FilterF: sources=['tcp://FilterC', 'tcp://FilterE?']
    FilterG: sources=['tcp://FilterF']

Environment variables:
    DEBUG_ZEROMQ: If 'true'ish and logging is set to 'debug' then will log each message sent and received (not the
        full contents, just basic info).

    ZMQ_RECONNECT_IVL: Reconnect wait in milliseconds.

    ZMQ_RECONNECT_IVL_MAX: Reconnect exponential backoff max value in milliseconds, 0 for no backoff (default).

    ZMQ_EXPLICIT_LINGER: Because sometimes zmq.LINGER just doesn't do it. Milliseconds to wait after last send before
        allowing socket close to make sure important messages (exit) get out. Because really, sometimes it just drops
        the last messages even with LINGER set high.

    ZMQ_POLL_TIMEOUT: Length to wait in milliseconds each poll for a message to come in in milliseconds. Requests for
        more frames are sent at this interval as well.

    ZMQ_CONN_TIMEOUT: Length of time in milliseconds without receiving anything from a downstream connection in order to
        consider that client timed out and no longer require a request from it to allow publish of frames.

    ZMQ_CONN_HANDSHAKE: Since we are using two separate sockets for communication it is possible that the requestor
        socket connects before the subscriber socket and causes messages to be sent which are missed. This is not
        usually a problem during normal operation but may be during testing or in special circumstances. For this reason
        handshake exists so that a sender does not recognize a receiver until that receiver has indicated in its request
        packets that it has received at least one message from the sender. Set this to False to turn this behavior off
        if for some reason it is causing a problem or if you want the absolute fastest connections without regard for
        possibly lost initial packets. Set on upstream side, default True.

    ZMQ_PUSH_HWM: For emergencies.
    ZMQ_PUB_HWM: For emergencies.

    ZMQ_LOW_LATENCY: If 'true'ish then favor lower latency over higher throughput. Will only help in some cases with
        the right properties. Really on things immediately downstream of VideoIn.

    ZMQ_WARN_NEWER: Warn on newer messages than expected.
    ZMQ_WARN_OLDER: Warn on older messages than expected.
"""

import logging
import os
import re
from json import dumps as json_dumps, loads as json_loads
from time import time_ns, sleep
from typing import Callable, NamedTuple

import zmq

from .utils import JSONType, json_getval, rndstr, once

__all__ = ['is_zeromq_addr', 'ZMQMessage', 'ZMQReceiver', 'ZMQSender']

logger = logging.getLogger(__name__)

DEBUG_ZEROMQ          = bool(json_getval((os.getenv('DEBUG_ZEROMQ') or 'false').lower()))

TCP_DEFAULT_PORT      = 5550
TCP_RE_ADDR           = re.compile(r'^(.*?)(?::(\d+))?$')

IPC_REQREP_SUFFIX     = '.req'
IPC_PUBSUB_SUFFIX     = ''

ZMQ_RECONNECT_IVL     = int(os.getenv('ZMQ_RECONNECT_IVL') or 100)    # in milliseconds, see zeromq documentation
ZMQ_RECONNECT_IVL_MAX = int(os.getenv('ZMQ_RECONNECT_IVL_MAX') or 0)  # in milliseconds, see zeromq documentation
ZMQ_EXPLICIT_LINGER   = int(os.getenv('ZMQ_EXPLICIT_LINGER') or 20)   # in milliseconds
ZMQ_POLL_TIMEOUT      = int(os.getenv('ZMQ_POLL_TIMEOUT') or 100)     # in milliseconds, unanswered request resend time and exit check
ZMQ_CONN_TIMEOUT      = int(os.getenv('ZMQ_CONN_TIMEOUT') or 5000)    # in milliseconds
ZMQ_CONN_HANDSHAKE    = bool(json_getval((os.getenv('ZMQ_CONN_HANDSHAKE') or 'true').lower()))
ZMQ_PUSH_HWM          = int(os.getenv('ZMQ_PUSH_HWM') or max(3, min(100, ZMQ_CONN_TIMEOUT // max(1, ZMQ_POLL_TIMEOUT))))  # will start complaining after this many push sends pending
ZMQ_PUB_HWM           = int(os.getenv('ZMQ_PUB_HWM') or 4 * 5)        # will start dropping after this many messages are backed up, low because messages are expected to be large and we don't want latency building up, 4 because 4 parts per message (each part message counts as individual message I guess?)
ZMQ_LOW_LATENCY       = bool(json_getval((os.getenv('ZMQ_LOW_LATENCY') or 'false').lower()))
ZMQ_WARN_NEWER        = bool(json_getval((os.getenv('ZMQ_WARN_NEWER') or 'true').lower()))
ZMQ_WARN_OLDER        = bool(json_getval((os.getenv('ZMQ_WARN_OLDER') or 'true').lower()))

MSG_ID_INITIAL        = 0
MSG_ID_INITIAL_PREV   = -1

MSG_ID_SPECIAL        = -2
MSG_ID_OOB            = -2
MSG_ID_CLOSE          = -3
MSG_ID_HELLO          = -4

TOPIC_DELIM           = '/'
TOPIC_DELIM_B         = b'/'
TOPIC_DELIM2          = TOPIC_DELIM * 2
TOPIC_DELIM_B2        = TOPIC_DELIM_B * 2

is_zeromq_addr        = lambda addr: addr.startswith('tcp://') or addr.startswith('ipc://')

ZMQMessage            = list[JSONType | bytes]  # only the first OBLIGATORY element is arbitrary JSONType, rest (if present) MUST be bytes
ZMQState              = tuple                   # for passing info between a Receiver and Sender


class ZMQStateSend(NamedTuple):  # for ZMQSender.send() from ZMQReceiver.recv()
    msg_id:   int
    balanced: bool = False


class ZMQStateRecv(NamedTuple):  # for ZMQReceiver.recv() from ZMQSender.send()
    msg_id: int


class ZMQContext:
    context = (None, 0)

    @staticmethod
    def get():
        ZMQContext.context = (ZMQContext.context[0], c + 1) if (c := ZMQContext.context[1]) else (zmq.Context(), 1)

        return ZMQContext.context[0]

    @staticmethod
    def free():
        ZMQContext.context = (ZMQContext.context[0], (c := ZMQContext.context[1] - 1))

        if not c:
            ZMQContext.context[0].destroy()  # linger=0)


class ZMQSender:
    class Client(NamedTuple):
        client_id: str
        pull:      zmq.Socket
        t_last:    int
        requested: bool
        ephemeral: int
        prev_id:   int

    def __init__(self,
        addrs_bind:    str | list[str] | None = None,
        server_id:     str | None = None,
        message_oob:   Callable[[ZMQMessage], None] | None = None,
        balance:       bool = False,
        outs_required: list[str] | None = None,
    ):
        """Publisher of messages (upon request) to possibly multiple clients at multiple bind addresses.

        Args:
            addrs_bind: Single or list of strings of bind addresses to listen on, forms can take:
                "tcp://*", "tcp:127.0.0.1:5552", "ipc://./pipe_in_cwd", "ipc:///abs_path/subdir/pipe"

            server_id: String ID for this server, if None then will be random string each time.

            outs_required: List of client_ids which need to be connected before anything is sent.

            message_oob: Optional callback for out-of-band messages.

            balance: Whether to send messages round-robin across connections for load balancing or not.
        """

        self.server_id     = server_id or rndstr(8, 64)
        self.message_oob   = (lambda l: None) if message_oob is None else message_oob
        self.balance       = balance
        self.outs_required = outs_required or []
        self.clients       = {}  # {'full_id': Client, ...}
        self.min_send_id   = MSG_ID_INITIAL
        self.pull2addr     = pull2addr = {}  # {PULL Socket: 'addr', ...}
        context            = ZMQContext.get()
        self.pulls         = pulls  = []
        self.pubs          = pubs   = []
        self.poller        = poller = zmq.Poller()

        for addr_bind in ('tcp://*',) if addrs_bind is None else (addrs_bind,) if isinstance(addrs_bind, str) else addrs_bind:
            pulls.append(pull := context.socket(zmq.PULL))
            pubs.append(pub := context.socket(zmq.PUB))

            pull2addr[pull] = addr_bind

            if addr_bind.startswith('tcp://'):
                host, port = TCP_RE_ADDR.match(addr_bind).groups()
                port       = TCP_DEFAULT_PORT if not port else int(port)
                pull_addr  = f'{host}:{port + 1}'
                pub_addr   = f'{host}:{port}'

            elif addr_bind.startswith('ipc://'):
                pull_addr = f'{addr_bind}{IPC_REQREP_SUFFIX}'
                pub_addr  = f'{addr_bind}{IPC_PUBSUB_SUFFIX}'

            else:
                raise ValueError(f'invalid bind address {addr_bind!r}')

            pub.setsockopt(zmq.SNDHWM, ZMQ_PUB_HWM)
            # pub.setsockopt(zmq.LINGER, 0)
            pub.setsockopt(zmq.RECONNECT_IVL, ZMQ_RECONNECT_IVL)
            pub.setsockopt(zmq.RECONNECT_IVL_MAX, ZMQ_RECONNECT_IVL_MAX)
            pub.bind(pub_addr)

            # pull.setsockopt(zmq.LINGER, 0)
            pull.setsockopt(zmq.RECONNECT_IVL, ZMQ_RECONNECT_IVL)
            pull.setsockopt(zmq.RECONNECT_IVL_MAX, ZMQ_RECONNECT_IVL_MAX)
            pull.bind(pull_addr)

            poller.register(pull, zmq.POLLIN)

            logger.info(f'sender {server_id}: publishing on {pub_addr}, listening on {pull_addr}')

    def destroy(self):
        msg_close = [TOPIC_DELIM_B2, json_dumps({'sid': self.server_id, 'mid': MSG_ID_CLOSE}, separators=(',', ':')).encode()]  # courtesy inform connection close

        for pub in self.pubs:
            pub.send_multipart(msg_close)

        sleep(ZMQ_EXPLICIT_LINGER / 1000)

        for pull, pub in zip(self.pulls, self.pubs):
            pub.close()
            pull.close()

            if (addr_bind := self.pull2addr[pull]).startswith('ipc://'):
                fnm = addr_bind[6:]

                try:
                    os.unlink(f'{fnm}{IPC_REQREP_SUFFIX}')
                except Exception:
                    pass

                try:
                    os.unlink(f'{fnm}{IPC_PUBSUB_SUFFIX}')
                except Exception:
                    pass

        ZMQContext.free()

    def send_oob(self, msg: ZMQMessage):
        msg_ = [TOPIC_DELIM_B2, json_dumps({'sid': self.server_id, 'mid': MSG_ID_OOB, 'xtra': msg[0]},
            separators=(',', ':')).encode(), *msg[1:]]

        if DEBUG_ZEROMQ:
            logger.debug(f'send msg OOB to {", ".join(c.client_id for c in self.clients.values())}: {str(msg[0])[:50]}')

        for pub in self.pubs:
            pub.send_multipart(msg_)

    def send(self,
        topicmsgs: dict[str, ZMQMessage] | Callable[[], dict[str, ZMQMessage]],
        state:     ZMQStateSend | None = None,
        timeout:   int | None = None,
        push:      bool = False,
    ) -> ZMQStateRecv | None:  # next send / request-1 msg_id, None if not sent
        """Send a list of messages to a list of topics. Will only send once all tracked clients have requested a message
        with a `msg_id` equal to or below the `msg_id` of this message send.

        Args:
            topicmsgs: A string topic indexed dictionary of lists of bytes messages (or objects with buffer interfaces).
                The first message in each list must be present and is treated specially, it can be any json.dumps()able
                puthon object and is sent in the message envelope to allow small chunks of metadata to not use up a
                whole message. This could also be a callable which will be called when a request is received from all
                downstream clients. Meant for getting latest frames from cameras right at the time they are requested.
                If the callable returns None to the sender then the sender doesn't send anything and returns
                immediately, not incrementing the send `msg_id`.

            state: If not coupling with a ZMQReceiver then set this to None and the message id counter will be kept
                internally. Otherwise, this must be a state returned from ZMQReceiver.recv() or None for the initial
                `state`, NOT the ZMQState returned from this function, that state is for ZMQReceiver.recv().

                If the message id tracked by this state has been sent before or a higher one, or a downstream client
                requested a higher index message, then this message is discarded and the function returns immediately
                with a message id number in the `state` for the next message that can be sent successfully.

            timeout:
                Timeout in milliseconds or None if no timeout. If the send times out then None is returned.

            push: If True then will publish message regardless of connections or synchronization. Needless to say this
                breaks the synchronization mechanism and is only meant for channels where receivers only listen, like
                metrics. Default False obviously.

        Returns:
            Integer number of the next message `msg_id` that will be accepted (not discarded) for send, or None if the
            send timed out.
        """

        if state is None:
            msg_id   = self.min_send_id
            balanced = False

        else:
            if (msg_id := state.msg_id) < self.min_send_id:
                return ZMQStateRecv(self.min_send_id)  # ZMQState for ZMQReceiver

            balanced = state.balanced

        server_id = self.server_id
        balance   = self.balance
        clients   = self.clients
        poller    = self.poller
        do_send   = False
        do_hello  = False
        outputs   = None

        def poll_recv(poll_timeout: int | None) -> bool | None:
            nonlocal do_send, do_hello, outputs

            ret = False

            while True:  # this loop only exists to potentially soak up all pending NEW connection requests so that only one HELLO message is queued, otherwise any other received message returns
                if not (socks := poller.poll(poll_timeout)):
                    return ret

                pull, flags = socks[0]

                if flags != zmq.POLLIN:
                    raise RuntimeError(f'unexpected poll flags {flags}')

                msg = pull.recv_multipart()

                env       = json_loads(msg[0].decode())
                client_id = env['cid']
                full_id   = client_id + env.get('uid', '')
                prev_id   = env['mid']
                ephemeral = env.get('eph', 0)
                t         = time_ns() // 1_000_000  # ns -> ms

                if prev_id <= MSG_ID_SPECIAL:
                    if prev_id == MSG_ID_OOB:  # out-of-band message
                        if DEBUG_ZEROMQ:
                            logger.debug(f'recv msg OOB from {client_id}: {str(env["xtra"])[:50]}')

                        self.message_oob([env.get('xtra'), *msg[1:]])

                    elif prev_id == MSG_ID_CLOSE:  # close message
                        logger.debug(f'recv msg CLOSE from {client_id}')

                        if full_id in clients:
                            del clients[full_id]

                            logger.info(f'disconnected output: {client_id}  @ {self.pull2addr.get(pull, "???")}  (close)')

                    return True

                if full_id not in clients:  # this is because we use two sockets, the request socket may connect before the subscribe socket and a message may be sent before the client is ready, give the subscribe socket some extra time to complete the connection
                    if ZMQ_CONN_HANDSHAKE and env.get('new'):  # client hasn't received a message from us yet so we can not be sure that the PUB/SUB connection has been established yet
                        if DEBUG_ZEROMQ:
                            logger.debug(f'recv msg new conn req from {client_id}')  # DEBUG!

                        do_hello     = True
                        ret          = True
                        poll_timeout = 0

                        continue

                    logger.info(f'connected output: {client_id}  @ {self.pull2addr.get(pull, "???")}')

                break

            clients[full_id] = ZMQSender.Client(client_id, pull, t, True, ephemeral, prev_id)

            if prev_id >= msg_id and not ephemeral:  # if requesting higher frame number than we are sending then discard and return
                self.min_send_id = min_send_id = prev_id + 1

                if msg_id != MSG_ID_INITIAL:
                    logger.warning(f'downstream requested newer message id {min_send_id} than we are sending {msg_id}')

                return None  # this will cause outer function to exit as if message was sent

            t_min      = t - ZMQ_CONN_TIMEOUT
            client_ids = set(client.client_id for client in clients.values())
            do_send    = all(client_id in client_ids for client_id in self.outs_required)  # True if there are no required outputsset()
            outputs    = {}  # {pull: (output specific do_send, # requested, max prev_id), ...}

            for full_id, (client_id, pull, t_last, requested, ephemeral, prev_id) in list(clients.items()):
                if t_last < t_min:  # if connection timed out then remove it from further consideration
                    del clients[full_id]

                    logger.info(f'disconnected output: {client_id}  @ {self.pull2addr.get(pull, "???")}  (timeout)')

                elif balance:  # if doing this then only one bound output endpoint needs to have all clients requested in order to send to that endpoint only
                    out_do_send, out_nrequested, out_prev_id = \
                        (True, 0, MSG_ID_INITIAL_PREV) if (output := outputs.get(pull)) is None else output

                    outputs[pull] = (
                        out_do_send and (requested or ephemeral),
                        out_nrequested + requested,
                        max(out_prev_id, prev_id),
                    )

                elif not requested and not ephemeral:  # if at least one non-ephemeral connection hasn't requested yet then we don't send
                    do_send = False

            if balance and all(not (out_do_send and out_nrequested) for out_do_send, out_nrequested, _ in outputs.values()):
                do_send = False

            return True

        def send_maybe() -> bool:
            nonlocal do_hello, topicmsgs

            ret = None

            if (not do_send or not clients) and not push:
                ret = False

            elif not isinstance(topicmsgs, dict):  # callable(topicmsgs)
                if (topicmsgs := topicmsgs()) is None:  # if no frames to send just-in-time then say that frames have been sent
                    ret = True

            if do_hello:
                do_hello = False

                if ret is not None or balance:  # send HELLO only if no other message is going to be sent to ALL clients as that message would serve the same purpose
                    if DEBUG_ZEROMQ:
                        logger.debug(f'send msg HELLO to all')

                    msg_hello = [TOPIC_DELIM_B2, json_dumps({'sid': self.server_id, 'mid': MSG_ID_HELLO}, separators=(',', ':')).encode()]

                    for pub in self.pubs:
                        pub.send_multipart(msg_hello)

            if ret is not None:
                return ret

            if balance:
                _, out_pull = min([(out_prev_id, out_pull)  # get the output with the oldest max prev_id across its clients
                        for out_pull, (out_do_send, out_nrequested, out_prev_id) in outputs.items()
                        if out_do_send and out_nrequested
                    ], key=lambda o: o[0]
                )

                pubs        = [self.pubs[self.pulls.index(out_pull)]]
                pub_clients = [(full_id, (client_id, pull, t_last, _, ephemeral, prev_id))
                    for full_id, (client_id, pull, t_last, _, ephemeral, prev_id) in clients.items()
                    if pull is out_pull
                ]

            else:
                pubs        = self.pubs
                pub_clients = list(clients.items())

            for full_id, (client_id, pull, t_last, _, ephemeral, prev_id) in pub_clients:  # mark all as sent so they don't trigger another send until requested again
                clients[full_id] = ZMQSender.Client(client_id, pull, t_last, False, ephemeral, prev_id)

            if DEBUG_ZEROMQ:
                logger.debug(f'send msg {msg_id} to ({", ".join(clt[0] for _, clt in pub_clients)}): ({", ".join(topicmsgs)}){"  - push" if push else ""}')

            env = {'sid': server_id, 'mid': msg_id, 'topics': list(topicmsgs)}

            if balance or balanced:
                env['bal'] = balance or balanced + 1  # increment balanced index if that is coming from upstream

            msg_topics = [TOPIC_DELIM_B2, json_dumps(env, separators=(',', ':')).encode()]

            for topic, msg in topicmsgs.items():
                env['xtra'] = msg[0]
                topic       = f'{"" if topic.startswith("_") else TOPIC_DELIM}{topic}{TOPIC_DELIM}'.encode()
                msg         = [topic, json_dumps(env, separators=(',', ':')).encode(), *msg[1:]]

                for pub in pubs:
                    pub.send_multipart(msg)

            for pub in pubs:  # publish heartbeat / topics informative message
                pub.send_multipart(msg_topics)

            self.min_send_id = msg_id + 1

            return True

        while res := poll_recv(0):  # eat up any requests sitting in queues
            pass

        if res is None:  # someone requested larger message id than currently sending, discard and return
            return ZMQStateRecv(self.min_send_id)

        if timeout is None:
            while not send_maybe():  # only after eating up all requests do we check and send if all downstreams requested
                if poll_recv(None) is None:
                    break

        else:  # there is a timeout
            t_timeout = time_ns() + timeout * 1_000_000

            while not send_maybe():
                if not (timeout := max(0, t_timeout - time_ns())):
                    return None

                if poll_recv(timeout // 1_000_000) is None:
                    break

        return ZMQStateRecv(self.min_send_id)  # ZMQState for ZMQReceiver


class ZMQReceiver:
    class Sender:
        def __init__(self, context: zmq.Context, addr_connect: str, topics: list[tuple[str, str]] | None, client_id: str):
            if (ephemeral := addr_connect.endswith('?') + addr_connect.endswith('??')):
                addr_connect = addr_connect.rstrip('? ')

            self.ephemeral   = ephemeral
            self.addr        = addr_connect
            self.push        = push = context.socket(zmq.PUSH) if ephemeral < 2 else None
            self.sub         = sub  = context.socket(zmq.SUB)
            self.conn        = False  # if the server is "connected" or not
            self.server_id   = None
            self.unique_id   = rndstr(12, 64)  # unique id for connection because otherwise upstream has no way to differentiate between clients with same client_id on same requestor socket
            self.min_recv_id = MSG_ID_INITIAL  # this is only used by ephemeral channels individually, synchronized channels have a shared global value
            self.init_recvd  = lambda msg, topic, topics: {t: msg if t == topic else None for t in topics if not t.startswith('_')}  # subscribed to lowercase all so we don't include '_' prefix hidden topics

            if addr_connect.startswith('tcp://'):
                host, port = TCP_RE_ADDR.match(addr_connect).groups()
                port       = TCP_DEFAULT_PORT if not port else int(port)
                push_addr  = f'{host}:{port + 1}'
                sub_addr   = f'{host}:{port}'

            elif addr_connect.startswith('ipc://'):
                push_addr = f'{addr_connect}{IPC_REQREP_SUFFIX}'
                sub_addr  = f'{addr_connect}{IPC_PUBSUB_SUFFIX}'

            else:
                raise ValueError(f'invalid bind address {addr_connect!r}')

            if ephemeral < 2:  # doubly ephemeral doesn't even bother with request socket
                push.setsockopt(zmq.SNDHWM, ZMQ_PUSH_HWM)
                push.setsockopt(zmq.LINGER, 0)
                push.setsockopt(zmq.RECONNECT_IVL, ZMQ_RECONNECT_IVL)
                push.setsockopt(zmq.RECONNECT_IVL_MAX, ZMQ_RECONNECT_IVL_MAX)
                push.connect(push_addr)

            # sub.setsockopt(zmq.LINGER, 0)
            sub.setsockopt(zmq.RECONNECT_IVL, ZMQ_RECONNECT_IVL)
            sub.setsockopt(zmq.RECONNECT_IVL_MAX, ZMQ_RECONNECT_IVL_MAX)
            sub.connect(sub_addr)

            # from zmq import ssh
            # ssh.tunnel_connection(push, push_addr, "ubuntu@141.148.71.212")  # if want to do automatic ssh tunnel in future

            logger.info(f'receiver {client_id}: subscribed on {sub_addr}{f", requesting on {push_addr}" if ephemeral < 2 else ""}')

            if (topic_is_none := topics is None) or topics == [('*', '*')]:
                sub.setsockopt_string(zmq.SUBSCRIBE, TOPIC_DELIM if topic_is_none else '')  # all messages starting with TOPIC_DELIM if not '*' else EVERYTHING

                self.recvd_new = None
                self.topic_map = {}

                if not topic_is_none:
                    self.init_recvd = lambda msg, topic, topics: {t: msg if t == topic else None for t in topics}  # subscribed to "*" ALL so include EVERYTHING

            else:
                sub.setsockopt_string(zmq.SUBSCRIBE, TOPIC_DELIM2)  # only for getting the published topics and heartbeats for sent empty messages

                for src, dst in topics:
                    if '*' in src or '*' in dst:
                        raise ValueError(f'invalid use of * wildcard in topic map {((src, dst))}')

                    sub.setsockopt_string(zmq.SUBSCRIBE, (src if src.startswith('_') else TOPIC_DELIM + src) + TOPIC_DELIM)

                self.recvd_new = {src: None for src, _ in topics}
                self.topic_map = dict(topics)

        @property
        def subscribed_all(self):
            return self.recvd_new is None

        @property
        def got_all(self):
            return (recvd := self.recvd) is not None and all(v is not None for v in recvd.values())

        @property  # just a single pass to determine, otherwise it bothers me
        def got(self):
            return (
                'none' if (recvd := self.recvd) is None else
                'all'  if not (c := sum(v is None for v in recvd.values())) else
                'none' if c == len(recvd) else
                'some'
            )

        def new_recv(self, msg: ZMQMessage | None = None, topic: str | None = None, topics: list[str] | None = None,
                poller: zmq.Poller | None = None) -> dict[str, ZMQMessage] | None:
            recvd_new = self.recvd_new

            if msg is None:
                recvd = None if recvd_new is None else recvd_new.copy()
            elif recvd_new is None:
                recvd = self.init_recvd(msg, topic, topics)
            elif topic:
                recvd = {**recvd_new, topic: msg}
            else:
                recvd = recvd_new.copy()

            self.recvd = recvd

            if poller is not None:
                poller.register(self.sub, zmq.POLLIN)

            return recvd

        def send_push(self, msg0: dict[str, JSONType], msg_: list[bytes] = ()):  # WARNING! `msg0` is MUTATED!
            if self.ephemeral < 2:  # do not anything to doubly-ephemeral channels
                msg0['uid'] = self.unique_id

                try:
                    self.push.send_multipart([json_dumps(msg0, separators=(',', ':')).encode(), *msg_], zmq.DONTWAIT)

                except zmq.Again:
                    if self.conn:
                        self.conn = False

                        logger.info(f'disconnected source: {self.server_id}  @ {self.addr}  (timeout)')

    def __init__(self,
        addrs_n_topics: str | list[str | tuple[str, list[tuple[str, str]] | None]],
        client_id:      str | None = None,
        message_oob:    Callable[[ZMQMessage], None] | None = None,
        balance:        bool = False,
        low_latency:    bool | None = None,
    ):
        """Consumer of published messages (upon request) from possibly multiple publishers at multiple addresses.

        Args:
            addrs_n_topics: Single or list of strings and optionally topics to subscribe to, forms can take:
                "tcp://127.0.0.1:5552",
                ["tcp:127.0.0.1:5552", ("ipc://./pipe_in_cwd", [("src1", "dst1"), ("src2", "dst2")])]

            client_id: String ID for this client, if None then will be random string each time.

            message_oob: Function to call on out-of-band messages.

            balance: Indicates that incoming data is load balanced, needed to work properly in that case.

            low_latency: Low latency mode means that next message is NOT preemptively requested when current message is
                received, leads to lower latency but also lower throughput.

        Notes:
            * An address can have a trailing '?' character which will not be considered part of the address but will
            rather indicate that address to be ephemeral. An ephemeral channel will not hold up a sender for
            synchronization and will not enforce id sequence numbers, and so may or may not get current or past messages
            in any receive. This is intended for a single topic receiver that may do occasional slow processing on
            something coming from upstream, so upstream keeps going while it is processing.

            * If an address has two trailing '??' characters then it is doubly-ephemeral and does not send any message
            requests on its own, which means it can never "steal" messages from other ephemeral channels or advance the
            pipeline, it is only a listener. It will still send OOB messages though. This is only intended for passively
            plugging into a pipeline to see what's going on.
        """

        self.client_id   = client_id or rndstr(8, 64)
        self.message_oob = (lambda m: None) if message_oob is None else message_oob
        self.balance     = balance
        self.low_latency = ZMQ_LOW_LATENCY if low_latency is None else low_latency
        self.prev_id     = MSG_ID_INITIAL_PREV
        self.senders     = senders = {}
        context          = ZMQContext.get()

        for addr_n_topics in [addrs_n_topics] if isinstance(addrs_n_topics, str) else addrs_n_topics:
            addr, topics        = (addr_n_topics, None) if isinstance(addr_n_topics, str) else addr_n_topics
            sender              = self.Sender(context, addr, topics, client_id)
            senders[sender.sub] = sender

            if balance and sender.ephemeral:
                raise ValueError(f"balanced sources can not be ephemeral '?' like {addr!r}")

        self.new_recv()

    def destroy(self):
        msg_close = {'cid': self.client_id, 'mid': MSG_ID_CLOSE}  # courtesy inform connection close

        for sender in self.senders.values():
            sender.send_push(msg_close)

        sleep(ZMQ_EXPLICIT_LINGER / 1000)

        for sender in self.senders.values():
            sender.sub.close()

            if sender.ephemeral < 2:
                sender.push.close()

        ZMQContext.free()

    def send_oob(self, msg: ZMQMessage):
        msg0 = {'cid': self.client_id, 'mid': MSG_ID_OOB, 'xtra': msg[0]}
        msg_ = msg[1:]

        if DEBUG_ZEROMQ:
            logger.debug(f'send msg OOB to {", ".join(s.server_id or s.addr for s in self.senders.values())}: {str(msg[0])[:50]}')

        for sender in self.senders.values():
            sender.send_push(msg0, msg_)

    def new_recv(self):
        self.poller = poller = zmq.Poller()

        for sender in self.senders.values():
            sender.new_recv(poller=poller)

    def recv(self,
        state:   ZMQStateRecv | None = None,
        timeout: int | None = None,
    ) -> tuple[dict[str, ZMQMessage], ZMQStateSend] | None:  # (data, state) or None if timeout
        """Receive a list of messages from a list of topics or all topics (as configured in __init__). Will only return
        once all messages with the same msg_id, numerically higher than prev_id, are received.

        Args:
            state: If not coupling with a ZMQSender then set this to None and the message id counter will be kept
                internally. Otherwise, this must be a state returned from ZMQSender.send() or None for the initial
                `state`, NOT the ZMQState returned from this function, that state is for ZMQSender.send().

                Contains the message id of the next minimum number message that can be received. Will only return a
                message with an message id strictly greater than or equal to this and with all messages from all sources
                in all topics having the samemessage id.

            timeout: Timeout in milliseconds or None if no timeout. If the recv times out, then None is returned.

        Returns:
            Integer number of the message id that was received from send and a dictionary of topics to messages received
            or None if the recv timed out.

        TODO: a bit messy, refactor maybe?
        """

        client_id   = self.client_id
        balance     = self.balance  # whether we are balancing incoming source messages
        balanced    = False         # whether any of the incoming source messages arrived balanced
        min_recv_id = self.prev_id + 1 if state is None else state.msg_id
        senders     = self.senders
        sendervs    = senders.values()
        poller      = self.poller

        def recv_once(timeout) -> bool:  # got_all
            nonlocal balanced, min_recv_id

            while socks := poller.poll(timeout):
                while socks:  # we do like this instead of iterate because socks may need to be zeroed out in the loop
                    sub, flags = socks.pop()

                    if flags != zmq.POLLIN:
                        raise RuntimeError(f'unexpected poll flags {flags}')

                    msg = sub.recv_multipart(copy=False)  # payload parts stay as zmq.Frame so np.frombuffer can view them zero-copy downstream

                    sender     = senders[sub]
                    sender_eph = sender.ephemeral
                    topic_b    = msg[0].bytes  # topic/env are small control parts, copy them out eagerly
                    topic      = topic_b[topic_b.startswith(TOPIC_DELIM_B) : -1].decode()  # empty topics indicates ignore actual message (topics count tho for information)
                    env        = json_loads(msg[1].bytes.decode())
                    server_id  = sender.server_id = env['sid']
                    msg_id     = env['mid']
                    topics     = env.get('topics')
                    msg        = [env.get('xtra'), *msg[2:]]
                    t          = time_ns() // 1_000_000  # ns -> ms

                    if msg_balanced := not sender_eph and env.get('bal', False):  # ephemeral channels do not transfer balanced message status
                        balanced = msg_balanced  # because we want 'bal' index if balanced pipeline longer than one filter

                    if not sender.conn:
                        logger.info(f'connected source: {server_id}  @ {sender.addr}')

                        sender.conn = True

                    if DEBUG_ZEROMQ:
                        if msg_id > MSG_ID_SPECIAL:
                            logger.debug(f'recv msg {msg_id} from {server_id}: {topic}')
                        elif msg_id == MSG_ID_OOB:
                            logger.debug(f'recv msg OOB from {server_id}: {str(env["xtra"])[:50]}')
                        else:
                            logger.debug(f"""recv msg {"HELLO" if msg_id == MSG_ID_HELLO else
                                "CLOSE" if msg_id == MSG_ID_CLOSE else msg_id} from {server_id}""")

                    if msg_id <= MSG_ID_SPECIAL:
                        if msg_id == MSG_ID_OOB:  # out-of-band message
                            self.message_oob(msg)

                        elif msg_id == MSG_ID_CLOSE:  # close message
                            sender.min_recv_id = MSG_ID_INITIAL  # for ephemeral only, so that if sender restarts we don't get barrage of older message warnings

                            if sender.conn:
                                logger.info(f'disconnected source: {server_id}  @ {sender.addr}  (close)')

                                sender.conn = False

                        # else:  # msg_id == MSG_ID_HELLO

                        continue

                    def process_msg(min_recv_id_: int) -> bool:
                        nonlocal recvd

                        if msg_id < min_recv_id_:  # discard older messages if we are expecting newer
                            if topic and ZMQ_WARN_OLDER:
                                logger.warning(f'received older message id {msg_id} than expected {min_recv_id_} from {server_id}  ({topic})')

                            return None

                        if (recvd := sender.recvd) is None:
                            recvd = sender.recvd = sender.init_recvd(msg, topic, topics)

                        elif msg_id == min_recv_id_:
                            if topic:  # topic == '' is only an informative topics message from the server by this point
                                recvd[topic] = msg  # topic guaranteed to be one we want because of zmq.SUBSCRIBE

                        else:  # msg_id > min_recv_id_, topic == '' msg still useful here for invalidating older messages
                            recvd = sender.new_recv(msg, topic, topics)  # note that we don't reset 'balanced' here because sender can not change that state from one msg to another

                            return True

                        return False

                    if sender_eph:  # ephemeral sender
                        if process_msg(sender.min_recv_id) is None:
                            continue

                        sender.min_recv_id = msg_id

                    else:  # synchronized sender
                        if msg_id > min_recv_id and not msg_balanced and min_recv_id != MSG_ID_INITIAL and ZMQ_WARN_NEWER:
                            logger.warning(f'received newer message id {msg_id} than expected {min_recv_id} from {server_id}  ({topic})')

                        if (res := process_msg(min_recv_id)) is None:
                            continue

                        elif res and not balance:
                            for s in sendervs:  # invalidate all other (non-ephemeral) sender frames and reregister for polling if needed
                                if s is not sender and not s.ephemeral:
                                    if s.got_all:
                                        poller.register(s.sub, zmq.POLLIN)  # regerister because was unregistered if got_all, sender itself is known to be registered since we just got a message from it

                                    s.new_recv()

                        min_recv_id = msg_id

                        if balance:
                            if topic:  # topic informative message may be late partial from previous message so we don't allow it to lock sender
                                for s in sendervs:  # remove all other channels from polling because we are balancing and there may be other messages from other senders if we took too long to process and we do not want to mix sources
                                    if s is not sender and s.sub in poller:
                                        poller.unregister(s.sub)

                                socks = None  # force poll again from scratch because there may be other senders that have been polled that have just been removed from checking

                    if not sender.subscribed_all and (diff := (sr := set(recvd)) - (st := set(topics))) and (not sender_eph or sr & st):
                        for t in diff:
                            if t != '-':  # special topic name '-' is treated as a topic that will never exist and is subscribed to only to create the connection, so we don't warn on it not being present
                                once(logger.warning, f'subscribed topic {t!r} not in source topics {topics}', t=60*60)

                            del recvd[t]

                    if sender.got_all:  # unregister sender from polling if complete because we don't want newer messages
                        poller.unregister(sender.sub)

                # Return True condition is that all synchronized sender topics received and if any ephemeral senders
                # then all the individual sender topics must have been received or none at all, no partials. Do not
                # return if nothing received at all. Also return if a single channel from balaning received entirely.

                got_all_synced   = True   # should really be 'got_all_synced_or_sources_are_balanced' but that is too long
                got_any_complete = False
                got_any_partial  = False

                for s in sendervs:
                    if (got := s.got) == 'all':
                        got_any_complete = True

                    elif got != 'none':
                        got_any_partial = True

                        break

                    elif not s.ephemeral and not balance:
                        got_all_synced = False

                        break

                if got_all_synced and got_any_complete and not got_any_partial and not poller.poll(0):  # if more messages waiting then they are more ephemeral messages, try to get them before returning
                    return True

            return False  # should only get here due to timeout with negative return condition

        def request(prev_id):
            msg_req = {'cid': client_id, 'mid': prev_id}

            for sender in sendervs:
                if sender.ephemeral:
                    msg_req['eph'] = sender.ephemeral
                elif 'eph' in msg_req:
                    del msg_req['eph']

                if not sender.conn:
                    msg_req['new'] = True
                elif 'new' in msg_req:
                    del msg_req['new']

                sender.send_push(msg_req)

        got_all = recv_once(0)

        t_timeout = float('inf') if timeout is None else time_ns() + timeout * 1_000_000

        while True:
            if got_all:
                if not self.low_latency and balanced != 1:  # first receiver after load balancing split never prefetches because that can confuse splitter, TODO: fix that
                    request(min_recv_id)  # preemptively request the next expected frame before returning, sacrifices latency for throughput

                self.prev_id = min_recv_id
                data         = {}

                for sender in sendervs:
                    topic_map = sender.topic_map

                    for topic, frame in (recvd.items() if (recvd := sender.recvd) is not None else ()):
                        if frame is not None:
                            if (topic := topic_map.get(topic, topic)) in data:
                                raise RuntimeError(f'duplicate topic {topic!r} from: {sender.server_id}  @ {sender.addr}')

                            data[topic] = frame

                self.new_recv()

                if balance and not balanced:
                    once(logger.warning, f'balanced sources receiver received non-balanced message(s)', t=60*60)

                return (data, ZMQStateSend(min_recv_id, balanced))

            request(min_recv_id - 1)

            if timeout is None:
                recv_once_timeout = ZMQ_POLL_TIMEOUT
            elif not (timeout := max(0, t_timeout - time_ns()) // 1_000_000):
                return None
            else:
                recv_once_timeout = min(timeout, ZMQ_POLL_TIMEOUT)

            got_all = recv_once(recv_once_timeout)
