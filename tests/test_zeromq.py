#!/usr/bin/env python

import gc
import logging
import os
import unittest
from queue import Queue
from random import randint
from threading import Event, Thread
from time import sleep, time_ns

import zmq
from openfilter.filter_runtime import utils
from openfilter.filter_runtime.zeromq import ZMQStateRecv, ZMQStateSend, ZMQReceiver, ZMQSender, logger as zeromq_logger

zeromq_logger.setLevel(int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper())))


def recvstate(msg_id):
    return ZMQStateRecv(msg_id)

def sendstate(msg_id):
    return ZMQStateSend(msg_id)

def send(sendr, *args, **kwargs):
    return None if (res := sendr.send(*args, **kwargs)) is None else res[0]

def _materialize(v):  # ZMQReceiver uses recv_multipart(copy=False), so payload parts arrive as zmq.Frame
    return bytes(v) if isinstance(v, zmq.Frame) else v

def _materialize_parts(parts):
    return [_materialize(p) for p in parts]

def _materialize_topicmsgs(topicmsgs):
    return {topic: _materialize_parts(parts) for topic, parts in topicmsgs.items()}

def recvl(recvr, *args, **kwargs):
    if (res := recvr.recv(*args, **kwargs)) is None:
        return None
    return (res[1][0], _materialize_topicmsgs(res[0]))

def recv(recvr, *args, **kwargs):
    if (res := recvr.recv(*args, **kwargs)) is None:
        return None
    return (_materialize_topicmsgs(res[0]), res[1])


class TestZeroMQOld(unittest.TestCase):
    def tearDown(self):
        # Force garbage collection to clean up file descriptors
        gc.collect()

    def test_old_general(self):
        def thread(queue: Queue, queue_oob: Queue):
            sendr = ZMQSender(['tcp://*:5550', 'ipc://./tmp_pipe'], 'server', lambda m: queue_oob.put(_materialize_parts(m)))

            while (msg := queue.get()) is not None:
                if isinstance(msg, dict):  # topicmsgs
                    sendr.send(msg)
                else:
                    sendr.send_oob(msg)

            sendr.destroy()

        queue     = Queue()
        queue_oob = Queue()
        sendt     = Thread(target=thread, args=(queue, queue_oob))
        send      = lambda msg: (queue.put(msg), msg)[1]
        recvr     = ZMQReceiver('tcp://127.0.0.1:5550', 'client')  # just to start the zmq.Context in this thread

        sendt.start()
        recvr.destroy()

        try:
            recvr = ZMQReceiver([('tcp://127.0.0.1:5550', [('main', 'main')])], 'client1')

            sleep((0.1))  # needed because no stateful connections

            try:
                self.assertEqual(send({'main': [None]}), recvl(recvr)[1])
                self.assertEqual(send({'main': ['test']}), recvl(recvr)[1])
                self.assertEqual(send({'main': [None, b'data']}), recvl(recvr)[1])
                self.assertEqual(send({'main': ['test', b'data']}), recvl(recvr)[1])
                self.assertEqual(send({'main': ['test', b'data'], 'other': ['more', b'datums']})['main'], recvl(recvr)[1]['main'])

            finally:
                recvr.destroy()

            recvr1 = ZMQReceiver([('tcp://127.0.0.1:5550', [('other', 'other')])], 'client1')

            sleep((0.1))  # needed because no stateful connections

            try:
                self.assertEqual(send({'main': ['test', b'data'], 'other': ['more', b'datums']})['other'], recvl(recvr1)[1]['other'])

                queue2_oob = Queue()
                recvr2     = ZMQReceiver([('ipc://./tmp_pipe', [('main', 'main')])], 'client2', lambda m: queue2_oob.put(_materialize_parts(m)))

                sleep((0.1))  # needed because no stateful connections

                try:
                    send({'main': ['test', b'data'], 'other': ['more', b'datums']})
                    self.assertEqual(recvl(recvr1)[1], {'other': ['more', b'datums']})
                    self.assertEqual(recvl(recvr2)[1], {'main': ['test', b'data']})

                    recvr3 = ZMQReceiver([('tcp://127.0.0.1:5550', [('main', 'main'), ('other', 'other')])], 'client3')

                    sleep((0.1))  # needed because no stateful connections

                    try:
                        msg = send({'main': ['test', b'data'], 'other': ['more', b'datums']})

                        self.assertEqual(recvl(recvr1)[1], {'other': ['more', b'datums']})
                        self.assertEqual(recvl(recvr2)[1], {'main': ['test', b'data']})
                        self.assertEqual(recvl(recvr3)[1], msg)

                    finally:
                        recvr3.destroy()

                    send({'main': ['test', b'data'], 'other': ['more', b'datums']})
                    self.assertEqual(recvl(recvr1)[1], {'other': ['more', b'datums']})
                    self.assertEqual(recvl(recvr2)[1], {'main': ['test', b'data']})

                    oob = send(['Woohoo!', b"I'm an out of band message!"])
                    send({'main': ['test', b'data'], 'other': ['more', b'datums']})
                    self.assertEqual(recvl(recvr1)[1], {'other': ['more', b'datums']})
                    self.assertEqual(recvl(recvr2)[1], {'main': ['test', b'data']})
                    self.assertEqual(queue2_oob.get(), oob)

                    recvr1.send_oob(oob)
                    sleep(0.1)  # because of oob, otherwise might miss it?
                    send({'main': ['test', b'data'], 'other': ['more', b'datums']})
                    self.assertEqual(recvl(recvr1)[1], {'other': ['more', b'datums']})
                    self.assertEqual(recvl(recvr2)[1], {'main': ['test', b'data']})
                    self.assertEqual(queue_oob.get(), oob)

                finally:
                    recvr2.destroy()

            finally:
                recvr1.destroy()

            recvr4 = ZMQReceiver(['tcp://127.0.0.1:5550'], 'client4')

            sleep((0.1))  # needed because no stateful connections

            try:
                self.assertEqual(send({}), recvl(recvr4)[1])  # test empty message

            finally:
                recvr4.destroy()

        finally:
            queue.put(None)
            sendt.join()


class TestZeroMQTCP(unittest.TestCase):
    """This test was written before the ZMQ_CONN_HANDSHAKE mechanism was implemented. Which changes the startup, but
    does not invalidate the packet flow expected in these tests. For this reason the test is left as it is still very
    useful but ZMQ_CONN_HANDSHAKE is turned off."""

    @classmethod
    def setUpClass(cls):
        os.environ['ZMQ_CONN_HANDSHAKE'] = 'false'
        from openfilter.filter_runtime import zeromq
        assert zeromq.ZMQ_CONN_HANDSHAKE is True or zeromq.ZMQ_CONN_HANDSHAKE is False
        zeromq.ZMQ_CONN_HANDSHAKE = False  # HACK! HACK! HACK! HACK! HACK! HACK! HACK! HACK! HACK! HACK! HACK! for fork


    SERVER1 = 'tcp://*:5550'
    SERVER2 = 'tcp://*:5552'
    SERVER3 = 'tcp://*:5554'
    CLIENT1 = 'tcp://127.0.0.1:5550'
    CLIENT2 = 'tcp://127.0.0.1:5552'
    CLIENT3 = 'tcp://127.0.0.1:5554'

    def tearDown(self):
        # Force garbage collection to clean up file descriptors
        gc.collect()

    def test_send_recv(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr = ZMQReceiver(self.CLIENT1, 'client')

            try:
                self.assertEqual(recvl(recvr, timeout=0), None)  # prime the sender by sending a request for first message

                sleep(0.1)  # make sure recvr connected (both sockets must connect, PUB/SUB and PUSH/PULL for the requests)

                for i in range(120):
                    self.assertEqual(send(sendr, d := {'main': [None, str(i).encode()]}), i + 1)
                    self.assertEqual(recvl(recvr, timeout=1000), (i, d))

                    sleep(0.01)  # because otherwise request packets can double up and once one is missed sender doesn't send

            finally:
                recvr.destroy()

        finally:
            sendr.destroy()


    def test_tee(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr1 = ZMQReceiver(self.CLIENT1, 'client1')

            try:
                recvr2 = ZMQReceiver(self.CLIENT1, 'client2')

                try:
                    self.assertEqual(recvl(recvr1, timeout=0), None)
                    self.assertEqual(recvl(recvr2, timeout=0), None)

                    sleep(0.1)

                    for i in range(120):
                        self.assertEqual(send(sendr, d := {'main': [None, str(i).encode()]}), i + 1)
                        self.assertEqual(recvl(recvr1, timeout=1000), (i, d))
                        self.assertEqual(recvl(recvr2, timeout=1000), (i, d))

                        sleep(0.0002)

                finally:
                    recvr2.destroy()

            finally:
                recvr1.destroy()

        finally:
            sendr.destroy()


    def test_join(self):
        sendr1 = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                recvr = ZMQReceiver([self.CLIENT1, self.CLIENT2], 'client')

                try:
                    self.assertEqual(recvl(recvr, timeout=0), None)

                    sleep(0.1)

                    for i in range(120):
                        self.assertEqual(send(sendr1, d1 := {'main': [None, f'm{i}'.encode()]}), i + 1)
                        self.assertEqual(send(sendr2, d2 := {'othr': [None, f'o{i}'.encode()]}), i + 1)
                        self.assertEqual(recvl(recvr, timeout=1000), (i, {**d1, **d2}))

                        sleep(0.0002)

                finally:
                    recvr.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()


    def test_tee_and_join(self):
        sendr1 = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                recvr1 = ZMQReceiver([self.CLIENT1, self.CLIENT2], 'client1')

                try:
                    recvr2 = ZMQReceiver([self.CLIENT1, self.CLIENT2], 'client1')

                    try:
                        self.assertEqual(recvl(recvr1, timeout=0), None)
                        self.assertEqual(recvl(recvr2, timeout=0), None)

                        sleep(0.1)

                        for i in range(120):
                            self.assertEqual(send(sendr1, d1 := {'main': [None, f'm{i}'.encode()]}), i + 1)
                            self.assertEqual(send(sendr2, d2 := {'othr': [None, f'o{i}'.encode()]}), i + 1)
                            self.assertEqual(recvl(recvr1, timeout=1000), (i, e := {**d1, **d2}))
                            self.assertEqual(recvl(recvr2, timeout=1000), (i, e))

                            sleep(0.0002)

                    finally:
                        recvr2.destroy()

                finally:
                    recvr1.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()


    def test_tee_and_join_topics(self):
        sendr1 = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                recvr1 = ZMQReceiver([[self.CLIENT1, [('main', 'main')]], [self.CLIENT2, [('othr', 'othr')]]], 'client1')

                try:
                    recvr2 = ZMQReceiver([[self.CLIENT1, [('naim', 'naim')]], [self.CLIENT2, [('rhto', 'rhto')]]], 'client1')

                    try:
                        self.assertEqual(recvl(recvr1, timeout=0), None)
                        self.assertEqual(recvl(recvr2, timeout=0), None)

                        sleep(0.1)

                        for i in range(120):
                            self.assertEqual(send(sendr1, {**(d1m := {'main': [None, f'm{i}'.encode()]}), **(d1n := {'naim': [None, f'n{i}'.encode()]})}), i + 1)
                            self.assertEqual(send(sendr2, {**(d2o := {'othr': [None, f'o{i}'.encode()]}), **(d2r := {'rhto': [None, f'r{i}'.encode()]})}), i + 1)
                            self.assertEqual(recvl(recvr1, timeout=1000), (i, {**d1m, **d2o}))
                            self.assertEqual(recvl(recvr2, timeout=1000), (i, {**d1n, **d2r}))

                            sleep(0.0002)

                    finally:
                        recvr2.destroy()

                finally:
                    recvr1.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()


    def test_tee_topics(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr1 = ZMQReceiver([(self.CLIENT1, [('top0', 'top0')])], 'client1')

            try:
                recvr2 = ZMQReceiver([(self.CLIENT1, [('top1', 'top1')])], 'client2')

                try:
                    recvr3 = ZMQReceiver([(self.CLIENT1, [('top2', 'top2')])], 'client3')

                    try:
                        sleep(0.1)

                        self.assertEqual(recvl(recvr1, timeout=0), None)
                        self.assertEqual(recvl(recvr2, timeout=0), None)
                        self.assertEqual(recvl(recvr3, timeout=0), None)

                        sleep(0.1)

                        for i in range(0, 120, 8):
                            self.assertEqual(send(sendr, {**(d0 := {'top0': [None, f't0{i}'.encode()]})}, timeout=100), i + 1)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr1, timeout=1000), (i, d0))
                            self.assertEqual(recvl(recvr2, timeout=1), (i, {}))
                            self.assertEqual(recvl(recvr3, timeout=1), (i, {}))

                            sleep(0.01)

                            self.assertEqual(send(sendr, {**(d1 := {'top1': [None, f't1{i + 1}'.encode()]})}, timeout=100), i + 2)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr2, timeout=1000), (i + 1, d1))
                            self.assertEqual(recvl(recvr1, timeout=1), (i + 1, {}))
                            self.assertEqual(recvl(recvr3, timeout=1), (i + 1, {}))

                            sleep(0.01)

                            self.assertEqual(send(sendr, {**(d2 := {'top2': [None, f't2{i + 2}'.encode()]})}, timeout=100), i + 3)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr3, timeout=1000), (i + 2, d2))
                            self.assertEqual(recvl(recvr2, timeout=1), (i + 2, {}))
                            self.assertEqual(recvl(recvr1, timeout=1), (i + 2, {}))

                            sleep(0.01)

                            self.assertEqual(send(sendr, {**(d0 := {'top0': [None, f't0{i + 3}'.encode()]}), **(d1 := {'top1': [None, f't1{i + 3}'.encode()]})}, timeout=100), i + 4)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr1, timeout=1), (i + 3, d0))
                            self.assertEqual(recvl(recvr2, timeout=1), (i + 3, d1))
                            self.assertEqual(recvl(recvr3, timeout=1), (i + 3, {}))

                            sleep(0.01)

                            self.assertEqual(send(sendr, {**(d0 := {'top0': [None, f't0{i + 4}'.encode()]}), **(d2 := {'top2': [None, f't2{i + 4}'.encode()]})}, timeout=100), i + 5)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr1, timeout=1), (i + 4, d0))
                            self.assertEqual(recvl(recvr3, timeout=1), (i + 4, d2))
                            self.assertEqual(recvl(recvr2, timeout=1), (i + 4, {}))

                            sleep(0.01)

                            self.assertEqual(send(sendr, {**(d1 := {'top1': [None, f't1{i + 5}'.encode()]}), **(d2 := {'top2': [None, f't2{i + 5}'.encode()]})}, timeout=100), i + 6)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr2, timeout=1), (i + 5, d1))
                            self.assertEqual(recvl(recvr3, timeout=1), (i + 5, d2))
                            self.assertEqual(recvl(recvr1, timeout=1), (i + 5, {}))

                            sleep(0.01)

                            self.assertEqual(send(sendr, {**(d0 := {'top0': [None, f't0{i + 6}'.encode()]}), **(d1 := {'top1': [None, f't1{i + 6}'.encode()]}), **(d2 := {'top2': [None, f't2{i + 6}'.encode()]})}, timeout=100), i + 7)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr1, timeout=1), (i + 6, d0))
                            self.assertEqual(recvl(recvr2, timeout=1), (i + 6, d1))
                            self.assertEqual(recvl(recvr3, timeout=1), (i + 6, d2))

                            sleep(0.01)

                            self.assertEqual(send(sendr, {}, timeout=100), i + 8)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr1, timeout=1), (i + 7, {}))
                            self.assertEqual(recvl(recvr2, timeout=1), (i + 7, {}))
                            self.assertEqual(recvl(recvr3, timeout=1), (i + 7, {}))

                            sleep(0.01)

                    finally:
                        recvr3.destroy()

                finally:
                    recvr2.destroy()

            finally:
                recvr1.destroy()

        finally:
            sendr.destroy()


    def test_join_topics(self):
        sendr1 = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                sendr3 = ZMQSender(self.SERVER3, 'server3')

                try:
                    recvr = ZMQReceiver([self.CLIENT1, self.CLIENT2, self.CLIENT3], 'client')

                    try:
                        sleep(0.1)

                        self.assertEqual(recvl(recvr, timeout=0), None)

                        sleep(0.1)

                        for i in range(0, 120, 8):
                            self.assertEqual(send(sendr1, {**(d0 := {'top0': [None, f't0{i}'.encode()]})}, timeout=100), i + 1)
                            self.assertEqual(send(sendr2, {**(d1 := {})}, timeout=100), i + 1)
                            self.assertEqual(send(sendr3, {**(d2 := {})}, timeout=100), i + 1)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=1000), (i, {**d0, **d1, **d2}))

                            sleep(0.01)

                            self.assertEqual(send(sendr1, {**(d0 := {})}, timeout=100), i + 2)
                            self.assertEqual(send(sendr2, {**(d1 := {'top1': [None, f't1{i + 1}'.encode()]})}, timeout=100), i + 2)
                            self.assertEqual(send(sendr3, {**(d2 := {})}, timeout=100), i + 2)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=1000), (i + 1, {**d0, **d1, **d2}))

                            sleep(0.01)

                            self.assertEqual(send(sendr1, {**(d0 := {})}, timeout=100), i + 3)
                            self.assertEqual(send(sendr2, {**(d1 := {})}, timeout=100), i + 3)
                            self.assertEqual(send(sendr3, {**(d2 := {'top2': [None, f't2{i + 2}'.encode()]})}, timeout=100), i + 3)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=1000), (i + 2, {**d0, **d1, **d2}))

                            sleep(0.01)

                            self.assertEqual(send(sendr1, {**(d0 := {'top0': [None, f't0{i + 3}'.encode()]})}, timeout=100), i + 4)
                            self.assertEqual(send(sendr2, {**(d1 := {'top1': [None, f't1{i + 3}'.encode()]})}, timeout=100), i + 4)
                            self.assertEqual(send(sendr3, {**(d2 := {})}, timeout=100), i + 4)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=1000), (i + 3, {**d0, **d1, **d2}))

                            sleep(0.01)

                            self.assertEqual(send(sendr1, {**(d0 := {'top0': [None, f't0{i + 4}'.encode()]})}, timeout=100), i + 5)
                            self.assertEqual(send(sendr2, {**(d1 := {})}, timeout=100), i + 5)
                            self.assertEqual(send(sendr3, {**(d2 := {'top2': [None, f't2{i + 4}'.encode()]})}, timeout=100), i + 5)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=1000), (i + 4, {**d0, **d1, **d2}))

                            sleep(0.01)

                            self.assertEqual(send(sendr1, {**(d0 := {})}, timeout=100), i + 6)
                            self.assertEqual(send(sendr2, {**(d1 := {'top1': [None, f't1{i + 5}'.encode()]})}, timeout=100), i + 6)
                            self.assertEqual(send(sendr3, {**(d2 := {'top2': [None, f't2{i + 5}'.encode()]})}, timeout=100), i + 6)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=1000), (i + 5, {**d0, **d1, **d2}))

                            sleep(0.01)

                            self.assertEqual(send(sendr1, {**(d0 := {'top0': [None, f't0{i + 6}'.encode()]})}, timeout=100), i + 7)
                            self.assertEqual(send(sendr2, {**(d1 := {'top1': [None, f't1{i + 6}'.encode()]})}, timeout=100), i + 7)
                            self.assertEqual(send(sendr3, {**(d2 := {'top2': [None, f't2{i + 6}'.encode()]})}, timeout=100), i + 7)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=1000), (i + 6, {**d0, **d1, **d2}))

                            sleep(0.01)

                            self.assertEqual(send(sendr1, {**(d0 := {})}, timeout=100), i + 8)
                            self.assertEqual(send(sendr2, {**(d1 := {})}, timeout=100), i + 8)
                            self.assertEqual(send(sendr3, {**(d2 := {})}, timeout=100), i + 8)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=1000), (i + 7, {**d0, **d1, **d2}))

                            sleep(0.01)

                    finally:
                        recvr.destroy()

                finally:
                    sendr3.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()


    def test_topics_multi_present_and_absent(self):
        sendr1 = ZMQSender(self.SERVER1, 'server1', outs_required=['client1', 'client2', 'client3'])

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2', outs_required=['client1', 'client2', 'client3'])

            try:
                sendr3 = ZMQSender(self.SERVER3, 'server3', outs_required=['client1', 'client2', 'client3'])

                try:
                    recvr1 = ZMQReceiver([(self.CLIENT1, [('s1t1', 's1t1')]), (self.CLIENT2, [('s2t1', 's2t1')]), (self.CLIENT3, [('s3t1', 's3t1')])], 'client1')

                    try:
                        recvr2 = ZMQReceiver([(self.CLIENT1, [('s1t2', 's1t2')]), (self.CLIENT2, [('s2t2', 's2t2')]), (self.CLIENT3, [('s3t2', 's3t2')])], 'client2')

                        try:
                            recvr3 = ZMQReceiver([(self.CLIENT1, [('s1t3', 's1t3')]), (self.CLIENT2, [('s2t3', 's2t3')]), (self.CLIENT3, [('s3t3', 's3t3')])], 'client3')

                            try:
                                sleep(0.1)

                                self.assertEqual(recvl(recvr1, timeout=0), None)
                                self.assertEqual(recvl(recvr2, timeout=0), None)
                                self.assertEqual(recvl(recvr3, timeout=0), None)

                                sleep(0.01)

                                for i in range(0, 120):
                                    d11 = {f's1t1': [None, f's1t1-{i}'.encode()]} if randint(0, 1) else {}
                                    d12 = {f's1t2': [None, f's1t2-{i}'.encode()]} if randint(0, 1) else {}
                                    d13 = {f's1t3': [None, f's1t3-{i}'.encode()]} if randint(0, 1) else {}
                                    d21 = {f's2t1': [None, f's2t1-{i}'.encode()]} if randint(0, 1) else {}
                                    d22 = {f's2t2': [None, f's2t2-{i}'.encode()]} if randint(0, 1) else {}
                                    d23 = {f's2t3': [None, f's2t3-{i}'.encode()]} if randint(0, 1) else {}
                                    d31 = {f's3t1': [None, f's3t1-{i}'.encode()]} if randint(0, 1) else {}
                                    d32 = {f's3t2': [None, f's3t2-{i}'.encode()]} if randint(0, 1) else {}
                                    d33 = {f's3t3': [None, f's3t3-{i}'.encode()]} if randint(0, 1) else {}

                                    self.assertEqual(send(sendr1, {**d11, **d12, **d13}, timeout=100), i + 1)
                                    self.assertEqual(send(sendr2, {**d21, **d22, **d23}, timeout=100), i + 1)
                                    self.assertEqual(send(sendr3, {**d31, **d32, **d33}, timeout=100), i + 1)

                                    sleep(0.01)

                                    self.assertEqual(recvl(recvr1, timeout=1000), (i, {**d11, **d21, **d31}))
                                    self.assertEqual(recvl(recvr2, timeout=1000), (i, {**d12, **d22, **d32}))
                                    self.assertEqual(recvl(recvr3, timeout=1000), (i, {**d13, **d23, **d33}))

                                    sleep(0.01)

                            finally:
                                recvr3.destroy()

                        finally:
                            recvr2.destroy()

                    finally:
                        recvr1.destroy()

                finally:
                    sendr3.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()


    def test_send_recv_ephemeral(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr = ZMQReceiver(self.CLIENT1+'?', 'client')

            try:
                self.assertEqual(recvl(recvr, timeout=0), None)  # prime the sender by sending a request for first message

                sleep(0.1)  # make sure recvr connected (both sockets must connect, PUB/SUB and PUSH/PULL for the requests)

                for i in range(120):
                    self.assertEqual(send(sendr, d := {'main': [None, str(i).encode()]}), i + 1)
                    self.assertEqual(recvl(recvr, timeout=1000), (i, d))

                    sleep(0.01)  # because otherwise request packets can double up and once one is missed sender doesn't send

            finally:
                recvr.destroy()

        finally:
            sendr.destroy()


    def test_tee_both_ephemeral(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr1 = ZMQReceiver([(self.CLIENT1+'?', [('main', 'main')])], 'client1')

            try:
                recvr2 = ZMQReceiver([(self.CLIENT1+'?', [('othr', 'othr')])], 'client2')

                try:
                    self.assertEqual(recvl(recvr1, timeout=0), None)
                    self.assertEqual(recvl(recvr2, timeout=0), None)

                    sleep(0.1)

                    self.assertEqual(send(sendr, {**(dm := {'main': [None, f'm{0}'.encode()]}), **(do := {'othr': [None, f'o{0}'.encode()]})}), 1)
                    self.assertEqual(recvl(recvr1, timeout=1000), (0, dm))
                    self.assertEqual(recvl(recvr2, timeout=1000), (0, do))

                    sleep(0.0002)

                    for i in range(1, 120):
                        self.assertEqual(recvl(recvr1, timeout=0), None)  # prime sender
                        self.assertEqual(send(sendr, dm := {'main': [None, f'm{i}'.encode()]}), 2 * i)
                        self.assertEqual(recvl(recvr1, timeout=1000), (i, dm))

                        sleep(0.0002)

                        self.assertEqual(recvl(recvr2, timeout=0), None)  # prime sender
                        self.assertEqual(send(sendr, do := {'othr': [None, f'o{i}'.encode()]}), 2 * i + 1)
                        self.assertEqual(recvl(recvr2, timeout=1000), (i, do))

                        sleep(0.0002)

                finally:
                    recvr2.destroy()

            finally:
                recvr1.destroy()

        finally:
            sendr.destroy()


    def test_tee_synced_and_ephemeral(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr1 = ZMQReceiver([(self.CLIENT1, [('main', 'main')])], 'client1')

            try:
                recvr2 = ZMQReceiver([(self.CLIENT1+'?', [('othr', 'othr')])], 'client2')

                try:
                    self.assertEqual(recvl(recvr1, timeout=0), None)
                    self.assertEqual(recvl(recvr2, timeout=0), None)

                    sleep(0.1)

                    self.assertEqual(send(sendr, {**(dm := {'main': [None, f'm{0}'.encode()]}), **(do := {'othr': [None, f'o{0}'.encode()]})}), 1)
                    self.assertEqual(recvl(recvr1, timeout=1000), (0, dm))
                    self.assertEqual(recvl(recvr2, timeout=1000), (0, do))

                    sleep(0.0002)

                    for i in range(1, 120):
                        if i & 1:
                            self.assertEqual(recvl(recvr1, timeout=0), None)
                            self.assertEqual(recvl(recvr2, timeout=0), None)
                            self.assertEqual(send(sendr, {**(dm := {'main': [None, f'm{i}'.encode()]}), **(do := {'othr': [None, f'o{i}'.encode()]})}), i + 1)
                            self.assertEqual(recvl(recvr1, timeout=1000), (i, dm))
                            self.assertEqual(recvl(recvr2, timeout=1000), ((i + 1) // 2, do))

                        else:
                            self.assertEqual(recvl(recvr1, timeout=0), None)
                            self.assertEqual(send(sendr, dm := {'main': [None, f'm{i}'.encode()]}), i + 1)
                            self.assertEqual(recvl(recvr1, timeout=1000), (i, dm))

                        sleep(0.0002)

                finally:
                    recvr2.destroy()

            finally:
                recvr1.destroy()

        finally:
            sendr.destroy()


    def test_tee_doubly_ephemeral_and_ephemeral(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr1 = ZMQReceiver(self.CLIENT1+'??', 'client1')

            try:
                sleep(0.1)

                self.assertEqual(recvl(recvr1, timeout=0), None)  # this will not prime because is doubly ephemeral, so no request packets

                sleep(0.1)

                self.assertEqual(send(sendr, d := {'main': [None, f'm{0}'.encode()]}, timeout=100), None)

                recvr2 = ZMQReceiver([(self.CLIENT1+'?', [('main', 'main')])], 'client2')

                try:
                    sleep(0.1)

                    self.assertEqual(recvl(recvr2, timeout=0), None)  # this will prime

                    sleep(0.1)

                    self.assertEqual(send(sendr, d := {'main': [None, f'm{1}'.encode()]}, timeout=100), 1)

                    sleep(0.01)

                    self.assertEqual(recvl(recvr2, timeout=1), (0, d))
                    self.assertEqual(recvl(recvr1, timeout=1), (0, d))

                    sleep(0.01)

                    self.assertEqual(send(sendr, d := {'main': [None, f'm{2}'.encode()]}, timeout=100), 2)

                    sleep(0.01)

                    self.assertEqual(recvl(recvr2, timeout=1), (1, d))
                    self.assertEqual(recvl(recvr1, timeout=1), (1, d))

                    sleep(0.01)

                    self.assertEqual(send(sendr, d := {'othr': [None, f'm{3}'.encode()]}, timeout=100), 3)

                    sleep(0.01)

                    self.assertEqual(recvl(recvr2, timeout=100), None)
                    self.assertEqual(recvl(recvr1, timeout=100), (2, d))

                    sleep(0.01)

                    self.assertEqual(send(sendr, d := {'main': [None, f'm{4}'.encode()]}, timeout=100), 4)

                    sleep(0.01)

                    self.assertEqual(recvl(recvr2, timeout=100), (2, d))
                    self.assertEqual(recvl(recvr1, timeout=100), (3, d))

                finally:
                    recvr2.destroy()

            finally:
                recvr1.destroy()

        finally:
            sendr.destroy()


    def test_outputs_balance(self):
        sendr = ZMQSender([self.SERVER1, self.SERVER2, self.SERVER3], 'server', balance=True)

        try:
            recvr1 = ZMQReceiver(self.CLIENT1, 'client1')

            try:
                recvr2 = ZMQReceiver(self.CLIENT2, 'client2')

                try:
                    recvr3 = ZMQReceiver(self.CLIENT3, 'client3')

                    try:
                        self.assertEqual(recvl(recvr1, timeout=0), None)
                        self.assertEqual(recvl(recvr2, timeout=0), None)
                        self.assertEqual(recvl(recvr3, timeout=0), None)

                        sleep(0.1)

                        for i in range(0, 120, 3):
                            self.assertEqual(send(sendr, d := {'main': [None, f'm{i}'.encode()]}, timeout=100), i + 1)

                            sleep(0.01)

                            self.assertEqual(recv(recvr1, timeout=1000), (d, (i, True)))
                            self.assertEqual(recv(recvr2, timeout=1), None)
                            self.assertEqual(recv(recvr3, timeout=1), None)

                            sleep(0.01)

                            self.assertEqual(send(sendr, d := {'main': [None, f'm{i + 1}'.encode()]}, timeout=100), i + 2)

                            sleep(0.01)

                            self.assertEqual(recv(recvr2, timeout=1000), (d, (i + 1, True)))
                            self.assertEqual(recv(recvr1, timeout=1), None)
                            self.assertEqual(recv(recvr3, timeout=1), None)

                            sleep(0.01)

                            self.assertEqual(send(sendr, d := {'main': [None, f'm{i + 2}'.encode()]}, timeout=100), i + 3)

                            sleep(0.01)

                            self.assertEqual(recv(recvr3, timeout=1000), (d, (i + 2, True)))
                            self.assertEqual(recv(recvr2, timeout=1), None)
                            self.assertEqual(recv(recvr1, timeout=1), None)

                            sleep(0.01)

                    finally:
                        recvr3.destroy()

                finally:
                    recvr2.destroy()

            finally:
                recvr1.destroy()

        finally:
            sendr.destroy()


    def test_sources_balance(self):
        sendr1 = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                sendr3 = ZMQSender(self.SERVER3, 'server3')

                try:
                    recvr = ZMQReceiver([self.CLIENT1, self.CLIENT2, self.CLIENT3], 'client', balance=True)

                    try:
                        self.assertEqual(recvl(recvr, timeout=0), None)

                        sleep(0.1)

                        for i in range(0, 120, 3):
                            self.assertEqual(send(sendr1, d := {'main': [None, f'm{i}'.encode()]}, sendstate(i), timeout=100), i + 1)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=100), (i, d))

                            sleep(0.01)

                            self.assertEqual(send(sendr2, d := {'main': [None, f'm{i + 1}'.encode()]}, sendstate(i + 1), timeout=100), i + 2)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=100), (i + 1, d))

                            sleep(0.01)

                            self.assertEqual(send(sendr3, d := {'main': [None, f'm{i + 2}'.encode()]}, sendstate(i + 2), timeout=100), i + 3)

                            sleep(0.01)

                            self.assertEqual(recvl(recvr, timeout=100), (i + 2, d))

                            sleep(0.01)

                    finally:
                        recvr.destroy()

                finally:
                    sendr3.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()


    def test_outputs_balance_doubly_ephemeral_watch(self):
        sendr = ZMQSender([self.SERVER1, self.SERVER2, self.SERVER3], 'server', balance=True)

        try:
            recvr1 = ZMQReceiver(self.CLIENT1, 'client1')

            try:
                recvr2 = ZMQReceiver(self.CLIENT2, 'client2')

                try:
                    recvr3 = ZMQReceiver(self.CLIENT3, 'client3')

                    try:
                        recvr4 = ZMQReceiver(self.CLIENT1+'??', 'client4')

                        try:
                            recvr5 = ZMQReceiver(self.CLIENT2+'??', 'client5')

                            try:
                                recvr6 = ZMQReceiver(self.CLIENT3+'??', 'client6')

                                recvr1.dd = recvr2.dd = recvr3.dd = recvr4.dd = recvr5.dd = recvr6.dd = False


                                try:
                                    self.assertEqual(recvl(recvr1, timeout=0), None)
                                    self.assertEqual(recvl(recvr2, timeout=0), None)
                                    self.assertEqual(recvl(recvr3, timeout=0), None)

                                    sleep(0.1)

                                    for i in range(0, 120, 3):
                                        self.assertEqual(send(sendr, d := {'main': [None, f'm{i}'.encode()]}, timeout=100), i + 1)

                                        sleep(0.01)

                                        self.assertEqual(recv(recvr1, timeout=1000), (d, (i, True)))
                                        self.assertEqual(recv(recvr2, timeout=1), None)
                                        self.assertEqual(recv(recvr3, timeout=1), None)
                                        self.assertEqual(recv(recvr4, timeout=1000), (d, (i // 3, False)))
                                        self.assertEqual(recv(recvr5, timeout=1), None)
                                        self.assertEqual(recv(recvr6, timeout=1), None)

                                        sleep(0.01)

                                        self.assertEqual(send(sendr, d := {'main': [None, f'm{i + 1}'.encode()]}, timeout=100), i + 2)

                                        sleep(0.01)

                                        self.assertEqual(recv(recvr2, timeout=1000), (d, (i + 1, True)))
                                        self.assertEqual(recv(recvr1, timeout=1), None)
                                        self.assertEqual(recv(recvr3, timeout=1), None)
                                        self.assertEqual(recv(recvr5, timeout=1000), (d, (i // 3, False)))
                                        self.assertEqual(recv(recvr4, timeout=1), None)
                                        self.assertEqual(recv(recvr6, timeout=1), None)

                                        sleep(0.01)

                                        self.assertEqual(send(sendr, d := {'main': [None, f'm{i + 2}'.encode()]}, timeout=100), i + 3)

                                        sleep(0.01)

                                        self.assertEqual(recv(recvr3, timeout=1000), (d, (i + 2, True)))
                                        self.assertEqual(recv(recvr2, timeout=1), None)
                                        self.assertEqual(recv(recvr1, timeout=1), None)
                                        self.assertEqual(recv(recvr6, timeout=1000), (d, (i // 3, False)))
                                        self.assertEqual(recv(recvr5, timeout=1), None)
                                        self.assertEqual(recv(recvr4, timeout=1), None)

                                        sleep(0.01)

                                finally:
                                    recvr6.destroy()

                            finally:
                                recvr5.destroy()

                        finally:
                            recvr4.destroy()

                    finally:
                        recvr3.destroy()

                finally:
                    recvr2.destroy()

            finally:
                recvr1.destroy()

        finally:
            sendr.destroy()


    def test_send_recv_missing_topic_of_1(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr = ZMQReceiver([(self.CLIENT1, [('other', 'other')])], 'client')

            try:
                self.assertEqual(recvl(recvr, timeout=0), None)  # prime the sender by sending a request for first message

                sleep(0.1)  # make sure recvr connected (both sockets must connect, PUB/SUB and PUSH/PULL for the requests)

                for i in range(120):
                    self.assertEqual(send(sendr, d := {'main': [None, str(i).encode()]}), i + 1)
                    self.assertEqual(recvl(recvr, timeout=1000), (i, {}))

                    sleep(0.01)  # because otherwise request packets can double up and once one is missed sender doesn't send

            finally:
                recvr.destroy()

        finally:
            sendr.destroy()


    def test_send_recv_missing_topic_of_2(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr = ZMQReceiver([(self.CLIENT1, [('main', 'main'), ('other', 'other')])], 'client')

            try:
                self.assertEqual(recvl(recvr, timeout=0), None)  # prime the sender by sending a request for first message

                sleep(0.1)  # make sure recvr connected (both sockets must connect, PUB/SUB and PUSH/PULL for the requests)

                for i in range(120):
                    self.assertEqual(send(sendr, d := {'main': [None, str(i).encode()]}), i + 1)
                    self.assertEqual(recvl(recvr, timeout=1000), (i, d))

                    sleep(0.01)  # because otherwise request packets can double up and once one is missed sender doesn't send

            finally:
                recvr.destroy()

        finally:
            sendr.destroy()


    def test_send_recv_ephemeral_missing_topic_of_1(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr = ZMQReceiver([(self.CLIENT1+'?', [('other', 'other')])], 'client')

            try:
                self.assertEqual(recvl(recvr, timeout=0), None)  # prime the sender by sending a request for first message

                sleep(0.1)  # make sure recvr connected (both sockets must connect, PUB/SUB and PUSH/PULL for the requests)

                for i in range(3):
                    self.assertEqual(send(sendr, d := {'main': [None, str(i).encode()]}), i + 1)
                    self.assertEqual(recvl(recvr, timeout=100), None)

                    sleep(0.01)  # because otherwise request packets can double up and once one is missed sender doesn't send

            finally:
                recvr.destroy()

        finally:
            sendr.destroy()


    def test_send_recv_ephemeral_missing_topic_of_2(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr = ZMQReceiver([(self.CLIENT1, [('main', 'main'), ('other', 'other')])], 'client')

            try:
                self.assertEqual(recvl(recvr, timeout=0), None)  # prime the sender by sending a request for first message

                sleep(0.1)  # make sure recvr connected (both sockets must connect, PUB/SUB and PUSH/PULL for the requests)

                for i in range(120):
                    self.assertEqual(send(sendr, d := {'main': [None, str(i).encode()]}), i + 1)
                    self.assertEqual(recvl(recvr, timeout=1000), (i, d))

                    sleep(0.01)  # because otherwise request packets can double up and once one is missed sender doesn't send

            finally:
                recvr.destroy()

        finally:
            sendr.destroy()


    def test_duplicate_topics(self):
        sendr1 = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                recvr = ZMQReceiver([self.CLIENT1, self.CLIENT2], 'client')

                try:
                    self.assertEqual(recvl(recvr, timeout=0), None)

                    sleep(0.1)

                    self.assertEqual(send(sendr1, {'main': [None, b's1']}, timeout=100), 1)
                    self.assertEqual(send(sendr2, {'main': [None, b's2']}, timeout=100), 1)

                    sleep(0.01)

                    self.assertRaises(RuntimeError, lambda: recvl(recvr, timeout=1000))

                finally:
                    recvr.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()


    def test_state_msgid_ignore_and_ffwd(self):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr = ZMQReceiver(self.CLIENT1, 'client')

            try:
                self.assertEqual(recvl(recvr, timeout=0), None)

                sleep(0.1)

                self.assertEqual(send(sendr, d := {'main': [None, b'10']}, sendstate(10)), 11)
                self.assertEqual(recvl(recvr, timeout=1000), (10, d))

                self.assertEqual(send(sendr, d := {'main': [None, b'5']}, sendstate(5)), 11)
                self.assertEqual(recvl(recvr, timeout=100), None)

                self.assertEqual(send(sendr, d := {'main': [None, b'20']}, sendstate(20)), 21)
                self.assertEqual(recvl(recvr, recvstate(30), timeout=100), None)

                self.assertEqual(send(sendr, d := {'main': [None, b'30']}, sendstate(30)), 31)
                self.assertEqual(recvl(recvr, timeout=100), (30, d))

                sleep(0.01)

            finally:
                recvr.destroy()

        finally:
            sendr.destroy()


    def test_outs_required(self):
        sendr = ZMQSender(self.SERVER1, 'server', outs_required=['client1', 'client2', 'client3'])

        try:
            recvr1 = ZMQReceiver([self.CLIENT1], 'client1')

            try:
                self.assertEqual(recvl(recvr1, timeout=0), None)

                sleep(0.1)

                self.assertEqual(send(sendr, d := {'main': [None, b'0']}, timeout=100), None)

                recvr2 = ZMQReceiver([self.CLIENT1], 'client2')

                try:
                    self.assertEqual(recvl(recvr2, timeout=0), None)

                    sleep(0.1)

                    self.assertEqual(send(sendr, d, timeout=100), None)

                    recvr3 = ZMQReceiver([self.CLIENT1], 'client3')

                    try:
                        self.assertEqual(recvl(recvr3, timeout=0), None)

                        sleep(0.1)

                        self.assertEqual(send(sendr, d, timeout=100), 1)

                        self.assertEqual(recvl(recvr1, timeout=1000), (0, d))
                        self.assertEqual(recvl(recvr2, timeout=1000), (0, d))
                        self.assertEqual(recvl(recvr3, timeout=1000), (0, d))

                    finally:
                        recvr3.destroy()

                finally:
                    recvr2.destroy()

            finally:
                recvr1.destroy()

        finally:
            sendr.destroy()


class TestZeroMQIPC(TestZeroMQTCP):
    SERVER1 = 'ipc://ipc_5550'
    SERVER2 = 'ipc://ipc_5552'
    SERVER3 = 'ipc://ipc_5554'
    CLIENT1 = 'ipc://ipc_5550'
    CLIENT2 = 'ipc://ipc_5552'
    CLIENT3 = 'ipc://ipc_5554'

    # @classmethod
    # def tearDownClass(cls):
    #     for fnm in ('ipc_5550', 'ipc_5550.req', 'ipc_5552', 'ipc_5552.req', 'ipc_5554', 'ipc_5554.req'):
    #         try:
    #             os.unlink(fnm)
    #         except FileNotFoundError:
    #             pass



    # WARNING! This works but currently sends everything on a single channel because they all have the same client_id. Revisit if/when can assign unique client ID to each source.
    # def test_balance(self):
    #     sendr = ZMQSender([self.SERVER1, self.SERVER2, self.SERVER3], 'server', balance=True)

    #     try:
    #         recvr = ZMQReceiver([self.CLIENT1+'?', self.CLIENT2+'?', self.CLIENT3+'?'], 'client', balance=True)

    #         try:
    #             self.assertEqual(recvl(recvr, timeout=0), None)

    #             sleep(0.1)

    #             for i in range(50):
    #                 self.assertEqual(send(sendr, d := {'main': [None, f'm{i}'.encode()]}, timeout=100), i + 1)
    #                 self.assertEqual(recvl(recvr, timeout=100), (i, d))

    #                 sleep(0.0002)

    #         finally:
    #             recvr.destroy()

    #     finally:
    #         sendr.destroy()


class TestSubRecvQueueCap(unittest.TestCase):
    """A receiver joining two sources holds one barrier for all of them, and the only discard path is sender-side
    and can only fire on the source that is BEHIND that barrier. The source that is AHEAD is never drained, so the
    only thing bounding how stale its delivered frames get is the subscriber's receive queue. With libzmq's default
    RCVHWM of 1000 that bound is hundreds of frames; ZMQ_SUB_HWM is what makes it a couple.

    `test_join` above drives both senders in lockstep, so it never produces the skew this needs. Here the two
    senders run at 40 ms and 46 ms, a 15% difference, which is enough for the leading source to saturate its
    receive queue inside the measurement window.

    IPC rather than TCP on purpose: a loopback TCP connection autotunes its kernel socket buffers into the
    megabytes, and those buffers are a store that no zmq high water mark accounts for, which turns the measurement
    into one about the host's network stack. How much they hide depends on frame size, since they are bounded in
    bytes and the queue under test is bounded in messages: the same run over TCP with these 64 KB frames shows
    nothing (1666 ms vs 1633 ms p95, about 40 frames of kernel buffer), and with 256 KB frames shows 2123 ms vs
    920 ms. Real pipelines carry frames far larger than either.
    """

    SERVER1 = 'ipc://ipc_5560'
    SERVER2 = 'ipc://ipc_5562'
    CLIENT1 = 'ipc://ipc_5560'
    CLIENT2 = 'ipc://ipc_5562'

    DURATION  = 15.0     # seconds of measurement, long enough for the leading source to saturate its queue
    INTERVAL1 = 0.040    # leading source
    INTERVAL2 = 0.046    # lagging source, 15% slower
    MAX_P95   = 1000.0   # milliseconds

    def tearDown(self):
        gc.collect()

    def test_leading_source_frames_do_not_go_stale(self):
        payload = b'x' * 65536  # frames are not small in a real pipeline, but big enough here would make this a memcpy benchmark
        stop    = Event()
        ages    = {'main': [], 'othr': []}

        def pump(sendr, topic, interval):
            # The timestamp is taken inside the callable, which the sender calls when the request arrives, so what
            # is measured is time spent in the queue and not time spent waiting to be asked.
            while not stop.is_set():
                sendr.send(lambda: {topic: [{'t': time_ns()}, payload]}, timeout=1000)
                sleep(interval)

        sendr1 = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                recvr = ZMQReceiver([self.CLIENT1, self.CLIENT2], 'client')

                try:
                    recvr.recv(timeout=0)  # prime the senders with a first request

                    sleep(0.2)

                    threads = [
                        Thread(target=pump, args=(sendr1, 'main', self.INTERVAL1), daemon=True),
                        Thread(target=pump, args=(sendr2, 'othr', self.INTERVAL2), daemon=True),
                    ]

                    for thread in threads:
                        thread.start()

                    try:
                        t_end = time_ns() + int(self.DURATION * 1e9)

                        while time_ns() < t_end:
                            if (res := recvr.recv(timeout=1000)) is None:
                                continue

                            now = time_ns()

                            for topic, parts in res[0].items():
                                ages[topic].append((now - parts[0]['t']) / 1e6)

                    finally:
                        stop.set()

                        for thread in threads:
                            thread.join(2)

                finally:
                    recvr.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()

        for topic, topic_ages in ages.items():
            with self.subTest(topic=topic):
                self.assertGreater(len(topic_ages), 100, f'{topic}: too few frames delivered to say anything')

                topic_ages.sort()

                p95 = topic_ages[int(0.95 * (len(topic_ages) - 1))]

                self.assertLess(p95, self.MAX_P95,
                    f'{topic}: p95 frame age {p95:.0f} ms over {len(topic_ages)} frames, limit {self.MAX_P95:.0f} ms')


class TestExitMsgLateSubscriber(unittest.TestCase):
    """A sender that never sent data still has to reach a subscriber that is still connecting.

    `MQ.send_exit_msg` is how a filter tells its downstream the stream ended, and it goes out on a PUB socket, which
    discards silently while the SUB side is still connecting. A filter that forwards zero frames (an ultra-short clip,
    a dedup that drops every frame) never runs the send() handshake that would prove the link, so a single publish can
    reach nobody and the downstream waits forever.
    """

    PORT    = 5597
    ADDR    = f'tcp://127.0.0.1:{PORT}'
    EXIT    = ['clean']
    LATE_MS = 400  # how long after the publish the subscriber shows up

    def tearDown(self):
        gc.collect()

    def _run(self, linger):
        """Publish an OOB before any subscriber exists, bring one up `LATE_MS` later, return what it received."""

        queue_oob = Queue()
        ready     = Queue()

        def sender_thread():
            sendr = ZMQSender([f'tcp://*:{self.PORT}'], 'server')

            try:
                ready.put(None)
                sendr.send_oob(self.EXIT, linger=linger)  # no send() first: nothing is connected and nothing is confirmed
            finally:
                sendr.destroy()

        recvr = ZMQReceiver(self.ADDR, 'ctx')  # starts the zmq.Context in this thread, as the other tests here do
        recvr.destroy()

        sendt = Thread(target=sender_thread)

        sendt.start()

        try:
            ready.get()

            sleep(self.LATE_MS / 1000)

            recvr = ZMQReceiver([(self.ADDR, [('main', 'main')])], 'late',
                lambda m: queue_oob.put(_materialize_parts(m)))

            try:
                deadline = 2.5

                while deadline > 0 and queue_oob.empty():
                    recvr.recv(timeout=100)

                    deadline -= 0.1

                return None if queue_oob.empty() else queue_oob.get()

            finally:
                recvr.destroy()

        finally:
            sendt.join()

    def test_exit_msg_reaches_a_late_subscriber(self):
        self.assertEqual(self.EXIT, self._run(linger=2000))

    def test_without_linger_it_is_lost(self):
        """The bug, pinned: one publish into a socket nobody has subscribed to yet goes nowhere."""

        self.assertIsNone(self._run(linger=0))

    def test_returns_when_the_subscriber_closes(self):
        """The wait is not a fixed cost: once the client has the message and goes away, the sender stops waiting."""

        linger   = 6000
        elapsed  = []
        queue    = Queue()

        def sender_thread():
            sendr = ZMQSender([f'tcp://*:{self.PORT}'], 'server')

            try:
                queue.put(None)

                t0 = time_ns()

                sendr.send_oob(self.EXIT, linger=linger)

                elapsed.append((time_ns() - t0) // 1_000_000)

            finally:
                sendr.destroy()

        recvr = ZMQReceiver(self.ADDR, 'ctx')
        recvr.destroy()

        sendt = Thread(target=sender_thread)

        sendt.start()

        try:
            queue.get()

            sleep(self.LATE_MS / 1000)

            got   = Queue()
            recvr = ZMQReceiver([(self.ADDR, [('main', 'main')])], 'late', lambda m: got.put(_materialize_parts(m)))

            for _ in range(25):
                if not got.empty():
                    break

                recvr.recv(timeout=100)

            recvr.destroy()  # what a filter does once it has honored the exit, and what releases the sender

            self.assertFalse(got.empty())

        finally:
            sendt.join()

        self.assertLess(elapsed[0], linger // 2, f'sender waited {elapsed[0]} ms of a {linger} ms budget')

    def test_reaches_a_subscriber_that_is_seconds_late(self):
        """The gap to cover is a downstream still importing, not the subscribe handshake.

        A filter carrying a model reaches its own `init()`, and so creates its receiver, tens of seconds after the
        container starts. 2.5 s here keeps the suite quick while being orders of magnitude past any handshake.
        """

        self.LATE_MS, saved = 2500, self.LATE_MS

        try:
            self.assertEqual(self.EXIT, self._run(linger=10000))
        finally:
            self.LATE_MS = saved

    def test_a_fast_output_closing_does_not_strand_a_required_slow_one(self):
        """On a fan-out, the first client to take the exit and go away must not end the wait for its siblings.

        A `??`-free tee declares its outputs with `outs_required`. One of them can connect, receive the exit and
        close while the other is still coming up, and returning at that point would strand the slow one on exactly
        the hang this function exists to prevent.
        """

        fast_got = Queue()
        slow_got = Queue()
        started  = Queue()

        def sender_thread():
            sendr = ZMQSender([f'tcp://*:{self.PORT}'], 'server', outs_required=['fast', 'slow'])

            try:
                started.put(None)
                sendr.send_oob(self.EXIT, linger=6000)
            finally:
                sendr.destroy()

        def pump(recvr, got, rounds):
            for _ in range(rounds):
                if not got.empty():
                    return True

                recvr.recv(timeout=100)

            return not got.empty()

        recvr = ZMQReceiver(self.ADDR, 'ctx')
        recvr.destroy()

        sendt = Thread(target=sender_thread)

        sendt.start()

        try:
            started.get()

            fast = ZMQReceiver([(self.ADDR, [('main', 'main')])], 'fast', lambda m: fast_got.put(_materialize_parts(m)))

            self.assertTrue(pump(fast, fast_got, 25), 'the early output never got the exit')

            fast.destroy()  # CLOSE, which on its own used to end the wait

            sleep(0.5)  # the slow sibling is still coming up all this time

            slow = ZMQReceiver([(self.ADDR, [('main', 'main')])], 'slow', lambda m: slow_got.put(_materialize_parts(m)))

            try:
                self.assertTrue(pump(slow, slow_got, 25), 'the slow required output was stranded')
                self.assertEqual(self.EXIT, slow_got.get())

            finally:
                slow.destroy()

        finally:
            sendt.join()

    # The gate: the other half of the claim is that nothing is paid on the normal path. These pin it, because the
    # cost of getting the gate wrong is silent - a correct exit message, delivered, after a full linger window.

    GATE_PORT = 5598

    def _confirmed_sender(self):
        """A sender and a receiver that have exchanged real frames, so the PUB/SUB link is confirmed."""

        sendr = ZMQSender([f'tcp://*:{self.GATE_PORT}'], 'server')
        recvr = ZMQReceiver([(f'tcp://127.0.0.1:{self.GATE_PORT}', [('main', 'main')])], 'client')
        sent  = 0

        for _ in range(60):
            if send(sendr, {'main': [None, b'x']}, timeout=50) is not None:
                sent += 1

            recvr.recv(timeout=50)

            if sent >= 3:
                break

        self.assertGreaterEqual(sent, 3, 'setup never delivered a frame, so nothing was confirmed')
        self.assertTrue(sendr.clients, 'setup never confirmed a client')

        return sendr, recvr

    def _elapsed_send_oob(self, sendr, linger):
        t0 = time_ns()

        sendr.send_oob(self.EXIT, linger=linger)

        return (time_ns() - t0) // 1_000_000

    def test_a_live_confirmed_client_is_not_lingered_for(self):
        """The handshake already proved the link, so the single publish reaches it and the sender leaves at once."""

        sendr, recvr = self._confirmed_sender()

        try:
            elapsed = self._elapsed_send_oob(sendr, linger=60_000)
        finally:
            recvr.destroy()
            sendr.destroy()

        self.assertLess(elapsed, 500, f'sender with a live confirmed client waited {elapsed} ms')

    def test_a_confirmed_client_that_has_closed_is_not_lingered_for(self):
        """`clients` is pruned on CLOSE, so it cannot answer "was one ever confirmed?" - `clients_ever` can.

        A downstream that closed first has already left and does not need the exit message, but gating on the live
        `clients` dict read that as "nobody was ever there" and waited out the whole window. That is every teardown
        where the downstream goes first, which includes a downstream erroring out under STOP_EXIT='error'.
        """

        sendr, recvr = self._confirmed_sender()

        try:
            recvr.destroy()  # CLOSE

            for _ in range(3):  # pump so the CLOSE is processed and the client is pruned
                send(sendr, {'main': [None, b'x']}, timeout=50)

            self.assertFalse(sendr.clients, 'the CLOSE was not processed, so this is not testing the pruned case')
            self.assertTrue(sendr.clients_ever, 'the confirmation was not remembered')

            elapsed = self._elapsed_send_oob(sendr, linger=60_000)

        finally:
            sendr.destroy()

        self.assertLess(elapsed, 500, f'sender whose confirmed client had closed waited {elapsed} ms')

    def test_the_wait_yields_before_the_runtime_hard_kills_the_process(self):
        """ZMQ_EXIT_LINGER (60 s) is 6x the graceful-stop budget SignalStopper allows (10 s).

        `send_exit_msg` runs before `fini()`, and a stop in progress has a `DaemonicTimer` behind it that SIGKILLs
        this process and all of its children when that budget runs out. Waiting the full linger there would not buy
        the extra seconds, it would only turn a clean exit into a death by signal with `fini()`, `emit_stop()` and
        `stop_logging()` skipped. So the wait is clamped to the deadline, less EXIT_LINGER_RESERVE_MS for them.
        """

        sendr = ZMQSender([f'tcp://*:{self.GATE_PORT}'], 'server')  # nothing connected: the linger is entered

        self.assertFalse(sendr.clients_ever)

        try:
            utils._hard_exit_deadline = time_ns() + 2_500 * 1_000_000  # as SignalStopper.stop() would set it

            elapsed = self._elapsed_send_oob(sendr, linger=60_000)

        finally:
            utils._hard_exit_deadline = None

            sendr.destroy()

        self.assertLess(elapsed, 2_500, f'the wait ran past the hard-kill deadline: {elapsed} ms')
        self.assertGreater(elapsed, 500, f'the wait did not honor the linger up to the deadline: {elapsed} ms')

    def test_a_stop_that_begins_during_the_wait_is_honored(self):
        """The deadline is armed after the wait is already running, which is the likelier ordering of the two.

        The whole window is only available on a self-initiated exit, so entering the linger with no deadline armed
        is the normal case: a `kubectl delete` / scale-down SIGTERM, or a Ctrl-C, lands a moment later and arms it
        from under us. Reading `hard_exit_deadline()` once at entry missed exactly that, and the process was
        SIGKILLed inside `send_oob` with `fini()`, `emit_stop()` and `stop_logging()` skipped.
        """

        sendr = ZMQSender([f'tcp://*:{self.GATE_PORT}'], 'server')  # nothing connected: the linger is entered

        self.assertFalse(sendr.clients_ever)
        self.assertIsNone(utils.hard_exit_deadline())

        def arm_deadline():  # as SignalStopper.stop() would, 200 ms into the wait
            sleep(0.2)

            utils._hard_exit_deadline = time_ns() + 2_500 * 1_000_000

        armer = Thread(target=arm_deadline, daemon=True)

        try:
            armer.start()

            elapsed = self._elapsed_send_oob(sendr, linger=60_000)

        finally:
            armer.join(5)

            utils._hard_exit_deadline = None

            sendr.destroy()

        # armed at ~200 ms for 2_500 ms, less EXIT_LINGER_RESERVE_MS, so the wait should end at ~1_700 ms
        self.assertLess(elapsed, 2_500, f'the mid-wait deadline was never consulted: {elapsed} ms')
        self.assertGreater(elapsed, 500, f'the wait ended before the deadline it was clamped to: {elapsed} ms')

    def test_no_stop_in_progress_leaves_the_linger_alone(self):
        """A self-initiated exit has no hard-kill timer behind it, so the full window stays available."""

        self.assertIsNone(utils.hard_exit_deadline())

        sendr = ZMQSender([f'tcp://*:{self.GATE_PORT}'], 'server')

        try:
            elapsed = self._elapsed_send_oob(sendr, linger=1_500)
        finally:
            sendr.destroy()

        self.assertGreaterEqual(elapsed, 1_400, f'the full linger was not paid: {elapsed} ms')




class TestPairByTs(unittest.TestCase):
    """A receiver joining two sources that sample at different rates.

    `TestSubRecvQueueCap` above measures the same shape for a different number: how stale each source's frame is
    when it is delivered. The number here is the one the join itself is about, how far apart in wall clock the two
    frames of a SINGLE delivered batch were taken. The default join has no reason to keep that small, because the
    only key it has for deciding that two frames belong together is a per-source counter, and two sources sampling
    at different rates do not keep matching counters.

    Note what the counter drift is and is not. It is not a time difference: a source with a lower id has taken
    fewer samples, which on its own says nothing about when its latest frame was taken. What it is, is the loss of
    the only key the default join pairs on, plus a second-order effect that does cost real time: the shared barrier
    is dragged forward by whichever source leads, so the leading source publishes into a subscriber queue nobody
    drains while the lagging one catches up, and the frames it eventually delivers are as old as that queue is
    deep.

    The senders here emulate what `video_in` does on a live camera: a blocking read at the camera's rate, then a
    send of the frame that read returned. The capture timestamp is taken before the send, so a frame the sender
    is holding while it waits to be asked ages exactly as a real one does.

    IPC rather than TCP for the same reason `TestSubRecvQueueCap` gives: a loopback TCP connection autotunes its
    kernel socket buffers into the megabytes and those buffers are a store no zmq high water mark accounts for.
    """

    SERVER1 = 'ipc://ipc_5570'
    SERVER2 = 'ipc://ipc_5572'
    CLIENT1 = 'ipc://ipc_5570'
    CLIENT2 = 'ipc://ipc_5572'

    DURATION  = 12.0    # seconds of measurement
    INTERVAL1 = 0.040   # leading source, 25 samples/s
    INTERVAL2 = 0.046   # lagging source, 21.7 samples/s, so the counters drift apart by about 3.3 per second

    # Measured on this shape over two 12 s runs: p95 pairing skew 527 and 519 ms with the default join, 45.4 and
    # 45.3 ms with pair_by_ts, over 221 and 238 batches. The 45 ms floor under the flag is INTERVAL2, which is the
    # right floor: a batch holds the newest frame each source has, and the slower source's newest is on average
    # half its own sampling period old. The bound below sits just above that floor and a factor of five under the
    # default, so neither assertion is really a measurement of the host it runs on.
    MAX_SKEW_MS = 100.0

    def tearDown(self):
        gc.collect()

    def _run(self, pair_by_ts, stamp_ts=True, duration=None):
        """Drive both sources for `duration` and return (skews_ms, ids) of every batch delivered."""

        payload = b'x' * 65536
        stop    = Event()
        skews   = []
        ids     = []

        def pump(sendr, topic, interval):
            while not stop.is_set():
                t_cap = time_ns()  # when this source "read" the frame, before it is offered to the sender
                xtra  = {'ts': t_cap / 1e9} if stamp_ts else None

                sendr.send(lambda: {topic: [xtra, payload]}, timeout=1000)
                sleep(interval)

        sendr1 = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                recvr = ZMQReceiver([self.CLIENT1, self.CLIENT2], 'client', pair_by_ts=pair_by_ts)

                try:
                    recvr.recv(timeout=0)  # prime the senders with a first request

                    sleep(0.2)

                    threads = [
                        Thread(target=pump, args=(sendr1, 'main', self.INTERVAL1), daemon=True),
                        Thread(target=pump, args=(sendr2, 'othr', self.INTERVAL2), daemon=True),
                    ]

                    for thread in threads:
                        thread.start()

                    try:
                        t_end = time_ns() + int((self.DURATION if duration is None else duration) * 1e9)

                        while time_ns() < t_end:
                            if (res := recvr.recv(timeout=1000)) is None:
                                continue

                            topicmsgs, state = res

                            if len(topicmsgs) < 2:  # a partial batch is a failure of its own, counted by the caller
                                skews.append(None)

                                continue

                            tss = [parts[0]['ts'] for parts in topicmsgs.values()] if stamp_ts else []

                            skews.append((max(tss) - min(tss)) * 1000 if tss else 0.0)
                            ids.append(state.msg_id)

                    finally:
                        stop.set()

                        for thread in threads:
                            thread.join(2)

                finally:
                    recvr.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()

        return skews, ids

    @staticmethod
    def _p95(values):
        values = sorted(values)

        return values[int(0.95 * (len(values) - 1))]

    def test_pairing_skew_stays_small_with_pair_by_ts(self):
        skews, _ = self._run(pair_by_ts=True)

        self.assertGreater(len(skews), 100, 'too few batches delivered to say anything')
        self.assertNotIn(None, skews, 'a batch was delivered without both sources in it')

        p95 = self._p95(skews)

        self.assertLess(p95, self.MAX_SKEW_MS,
            f'p95 pairing skew {p95:.1f} ms over {len(skews)} batches, limit {self.MAX_SKEW_MS:.1f} ms')

    def test_pairing_skew_is_large_without_it(self):
        """The same assertion on the default join, inverted, so the fixture is on record as reproducing the defect.

        If this ever starts failing it does not mean the default join got worse, it means it got BETTER, and the
        test above is no longer measuring anything. Read it as a tripwire on the baseline, not as a requirement.
        """

        skews, _ = self._run(pair_by_ts=False)

        self.assertGreater(len(skews), 100, 'too few batches delivered to say anything')

        p95 = self._p95([s for s in skews if s is not None])

        self.assertGreater(p95, self.MAX_SKEW_MS,
            f'p95 pairing skew {p95:.1f} ms over {len(skews)} batches with the default join, which is below the '
            f'{self.MAX_SKEW_MS:.1f} ms the pair_by_ts test asserts, so that test no longer proves anything')

    def test_frames_with_no_timestamp_still_deliver(self):
        """No meta['ts'] anywhere: pair on arrival time rather than stall, and keep both sources in every batch."""

        skews, _ = self._run(pair_by_ts=True, stamp_ts=False, duration=4.0)

        self.assertGreater(len(skews), 20, 'too few batches delivered to say anything')
        self.assertNotIn(None, skews, 'a batch was delivered without both sources in it')

    def test_the_state_msg_id_stays_monotonic(self):
        """Per-source counters are no longer meant to agree, so the id handed to the sender half is max of them.

        That is all `mq_msgid_sync` needs from it. It is NOT a moment any more, only an order, and this pins that.
        """

        _, ids = self._run(pair_by_ts=True, duration=4.0)

        self.assertGreater(len(ids), 20, 'too few batches delivered to say anything')
        self.assertEqual(ids, sorted(ids))

    def test_balanced_sources_are_rejected(self):
        with self.assertRaises(ValueError):
            ZMQReceiver([self.CLIENT1, self.CLIENT2], 'client', balance=True, pair_by_ts=True)

    def test_a_negative_tolerance_is_rejected(self):
        """A negative tolerance is truthy, so it would pass the "no gate" check and then ask for a batch whose
        frames are LESS than a negative number apart, which no batch is. The join would deliver nothing, forever,
        with nothing in the logs to say why. Rejected at construction instead, and rejected whatever `pair_by_ts`
        resolves to, so a typo is found at startup and not on the day someone turns the pairing on.
        """

        with self.assertRaises(ValueError):
            ZMQReceiver([self.CLIENT1, self.CLIENT2], 'client', pair_by_ts=True, pair_ts_tolerance=-0.001)

        with self.assertRaises(ValueError):
            ZMQReceiver(self.CLIENT1, 'client', pair_by_ts=False, pair_ts_tolerance=-1.0)

        recvr = ZMQReceiver([self.CLIENT1, self.CLIENT2], 'client', pair_by_ts=True, pair_ts_tolerance=0)  # 0 is the no-gate default and stays legal

        recvr.destroy()

    # For the restart test below. Source B starts here in id space, far above anything source A reaches in a run
    # this short, so B's counter is the one the delivered batch id follows and restarting B is what used to make
    # that id fall off a cliff.
    RESTART_SERVER1 = 'ipc://ipc_5576'
    RESTART_SERVER2 = 'ipc://ipc_5578'
    RESTART_FROM_ID = 5000
    RESTART_AFTER   = 40     # frames source B publishes before it goes away and comes back
    RESTART_RUN     = 6.0    # seconds

    def test_the_state_msg_id_stays_monotonic_across_a_source_restart(self):
        """A source that restarts gracefully must not drag the delivered batch id backwards.

        `MSG_ID_CLOSE` resets the closing sender's `min_recv_id`. Without the flag that field is only ever an
        ephemeral channel's older-message filter, so the reset is harmless and a synchronized source that comes
        back is fast-forwarded by the next request against the shared barrier. Under `pair_by_ts` the same field
        IS a synchronized source's barrier, so resetting it both stops the fast forward and drops the batch id
        back to whatever the other sources are counting.

        A falling batch id is not cosmetic. With `mq_msgid_sync` on it reaches `ZMQSender.send`, which returns
        without publishing anything whose state id is below what it has already sent, so the filter keeps being
        asked to `process()` and its output goes nowhere until the id climbs past the old value. Per-source
        counters drift freely under this flag, so that can be a long time.
        """

        payload   = b'x' * 4096
        interval  = 0.010
        stop      = Event()
        restarted = Event()
        ids       = []
        errors    = []

        def pump_a(sendr):
            try:
                while not stop.is_set():
                    t_cap = time_ns()

                    sendr.send(lambda: {'main': [{'ts': t_cap / 1e9}, payload]}, timeout=200)
                    sleep(interval)

            except Exception as exc:  # noqa: BLE001  - reported by the assertions below rather than swallowed
                errors.append(exc)

        def pump_b():
            """Source B, including its restart. Every socket operation on B happens in this one thread: a zmq
            socket is not thread safe, and destroying one under an in-flight send from another thread is the
            same problem wearing a hat.
            """

            sendr = ZMQSender(self.RESTART_SERVER2, 'server2')
            sendr.min_send_id = self.RESTART_FROM_ID  # start high, so B is the source the batch id follows

            try:
                n = 0

                while not stop.is_set():
                    if n == self.RESTART_AFTER:
                        sendr.destroy()  # sends MSG_ID_CLOSE, which is the whole point of this test

                        sendr = ZMQSender(self.RESTART_SERVER2, 'server2')  # same address, counter back to 0

                        restarted.set()

                    t_cap = time_ns()

                    sendr.send(lambda: {'othr': [{'ts': t_cap / 1e9}, payload]}, timeout=200)

                    n += 1

                    sleep(interval)

            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

            finally:
                sendr.destroy()

        sendr1 = ZMQSender(self.RESTART_SERVER1, 'server1')

        try:
            recvr = ZMQReceiver([self.RESTART_SERVER1, self.RESTART_SERVER2], 'client', pair_by_ts=True)

            try:
                recvr.recv(timeout=0)  # prime the senders with a first request

                sleep(0.2)

                threads = [Thread(target=pump_a, args=(sendr1,), daemon=True), Thread(target=pump_b, daemon=True)]

                for thread in threads:
                    thread.start()

                try:
                    before = after = 0
                    t_end  = time_ns() + int(self.RESTART_RUN * 1e9)

                    while time_ns() < t_end:
                        if (res := recvr.recv(timeout=100)) is None:
                            continue

                        ids.append(res[1].msg_id)

                        if restarted.is_set():
                            after += 1
                        else:
                            before += 1

                finally:
                    stop.set()

                    for thread in threads:
                        thread.join(3)

            finally:
                recvr.destroy()

        finally:
            sendr1.destroy()

        self.assertEqual(errors, [], f'a source thread raised: {errors}')
        self.assertTrue(restarted.is_set(), 'source B never restarted, so this run measures nothing')

        self.assertGreater(before, 10, f'only {before} batches before the restart, so this run measures nothing')
        self.assertGreater(after, 10, f'only {after} batches after the restart, so this run measures nothing')

        self.assertGreaterEqual(max(ids), self.RESTART_FROM_ID,
            f'source B never set the batch id (max delivered {max(ids)}), so resetting B could not have shown '
            f'up here anyway and this run measures nothing')

        drops = [(ids[i - 1], ids[i]) for i in range(1, len(ids)) if ids[i] < ids[i - 1]]

        self.assertEqual(drops, [],
            f'the batch id went backwards across the restart, {len(drops)} time(s): {drops[:5]}, over '
            f'{len(ids)} batches running {min(ids)} to {max(ids)}')


class TestPairByTsSingleSource(unittest.TestCase):
    """The flag is a join setting, and a filter that sets it globally must not change on its single-source hops.

    `test_send_recv` above, run twice: once as it is and once with pair_by_ts on. Same assertions, because the flag
    resolves to off on a receiver with fewer than two synchronized sources and the original code path runs.
    """

    SERVER1 = 'ipc://ipc_5574'
    CLIENT1 = 'ipc://ipc_5574'

    # Same reason `TestZeroMQTCP` does it, and the same hack. ZMQ_CONN_HANDSHAKE makes a sender ignore a client
    # until that client has acknowledged a HELLO, and a HELLO only goes out from inside send(). A strictly
    # lockstep send-then-recv loop never has both running at once, so the first send waits out its whole timeout
    # for an acknowledgement the receiver has no opportunity to give. Restored afterwards, which the original
    # does not do, so this does not quietly change the behavior of whatever runs next in the same process.
    @classmethod
    def setUpClass(cls):
        from openfilter.filter_runtime import zeromq

        cls._handshake = zeromq.ZMQ_CONN_HANDSHAKE
        zeromq.ZMQ_CONN_HANDSHAKE = False

    @classmethod
    def tearDownClass(cls):
        from openfilter.filter_runtime import zeromq

        zeromq.ZMQ_CONN_HANDSHAKE = cls._handshake

    def tearDown(self):
        gc.collect()

    def _send_recv_120(self, pair_by_ts):
        sendr = ZMQSender(self.SERVER1, 'server')

        try:
            recvr = ZMQReceiver(self.CLIENT1, 'client', pair_by_ts=pair_by_ts)

            try:
                self.assertFalse(recvr.pair_ts, 'pair_by_ts must resolve to off on a single synchronized source')

                self.assertEqual(recvl(recvr, timeout=0), None)  # prime the sender with a request for the first message

                sleep(0.1)  # both sockets have to connect, PUB/SUB and PUSH/PULL for the requests

                for i in range(120):
                    # `test_send_recv` sends with no timeout, which hangs for good rather than failing when a
                    # request packet is lost, a thing its own comment below says happens. Bound it here so a lost
                    # packet is a failed assertion and not a stuck job.
                    self.assertEqual(send(sendr, d := {'main': [{'ts': time_ns() / 1e9}, str(i).encode()]}, timeout=5000), i + 1)
                    self.assertEqual(recvl(recvr, timeout=1000), (i, d))

                    sleep(0.01)  # because otherwise request packets can double up and once one is missed sender doesn't send

            finally:
                recvr.destroy()

        finally:
            sendr.destroy()

    def test_without_the_flag(self):
        self._send_recv_120(pair_by_ts=False)

    def test_with_the_flag_on(self):
        self._send_recv_120(pair_by_ts=True)


class TestPairByTsMappedTopicsWithoutTimestamps(unittest.TestCase):
    """A topic-mapped join where one receiver subscribes to a topic its source does not publish.

    Two things have to be true at once for this to bite. The receiver has to prune a subscribed topic that turned
    out not to exist on the source, which is what the mapped-topic prune loop does, and the frames have to carry
    no 'ts', which sends the pairing down its arrival-time fallback. Every non-image frame is in that second set.

    The prune loop used to bind the missing topic name to `t`, which is the same name the arrival time of the
    message is held under in that scope, so the fallback divided a topic name by 1000 and `recv()` raised
    `TypeError: unsupported operand type(s) for /: 'str' and 'int'`. The flag off, the same setup delivers.
    """

    SERVER1 = 'ipc://ipc_5584'
    SERVER2 = 'ipc://ipc_5586'
    CLIENT1 = 'ipc://ipc_5584'
    CLIENT2 = 'ipc://ipc_5586'

    FRAMES = 20

    # Same reason and the same hack as TestPairByTsSingleSource: a strictly lockstep send-then-recv loop never
    # has a send and a recv running at once, so the connection handshake has no opportunity to complete.
    @classmethod
    def setUpClass(cls):
        from openfilter.filter_runtime import zeromq

        cls._handshake = zeromq.ZMQ_CONN_HANDSHAKE
        zeromq.ZMQ_CONN_HANDSHAKE = False

    @classmethod
    def tearDownClass(cls):
        from openfilter.filter_runtime import zeromq

        zeromq.ZMQ_CONN_HANDSHAKE = cls._handshake

    def tearDown(self):
        gc.collect()

    def _run(self, pair_by_ts):
        """Return the batches delivered. Source 1 is subscribed to a topic it never publishes."""

        batches = []
        sendr1  = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                recvr = ZMQReceiver([
                    (self.CLIENT1, [('main', 'camA'), ('extra', 'x')]),  # 'extra' is never published by server1
                    (self.CLIENT2, [('main', 'camB')]),
                ], 'client', pair_by_ts=pair_by_ts)

                try:
                    recvr.recv(timeout=0)  # prime both senders with a request

                    sleep(0.2)

                    for i in range(self.FRAMES):
                        send(sendr1, {'main': [None, f'a-{i}'.encode()]}, timeout=1000)  # no 'ts' anywhere, which is every non-image frame
                        send(sendr2, {'main': [None, f'b-{i}'.encode()]}, timeout=1000)

                        if (res := recv(recvr, timeout=1000)) is not None:
                            batches.append(res[0])

                        sleep(0.01)

                finally:
                    recvr.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()

        return batches

    def test_a_subscribed_topic_the_source_does_not_publish_does_not_break_recv(self):
        batches = self._run(pair_by_ts=True)

        self.assertGreater(len(batches), 5, 'too few batches delivered to say anything')

        for batch in batches:
            self.assertEqual(sorted(batch), ['camA', 'camB'], 'a batch went out without both sources in it')

    def test_the_same_setup_without_the_flag(self):
        """The baseline the test above has to match. If this one ever fails the fixture itself is broken."""

        batches = self._run(pair_by_ts=False)

        self.assertGreater(len(batches), 5, 'too few batches delivered to say anything')

        for batch in batches:
            self.assertEqual(sorted(batch), ['camA', 'camB'], 'a batch went out without both sources in it')


class TestPairByTsTolerance(unittest.TestCase):
    """What `pair_ts_tolerance` does when the sources' clocks are further apart than it allows.

    It refuses every batch, and goes on refusing for as long as the clocks stay apart. That is the gate doing
    what it was asked to do: a tolerance is the operator stating that a wider pair is wrong for this pipeline,
    so the refusal is not overridden. What it must not be is silent, because a join that refuses every batch is
    indistinguishable from the livelock this flag exists to avoid, right down to the healthy pod and the sources
    still publishing. These two tests pin both halves: the refusal, and the warning that explains it.
    """

    SERVER1 = 'ipc://ipc_5588'
    SERVER2 = 'ipc://ipc_5590'
    CLIENT1 = 'ipc://ipc_5588'
    CLIENT2 = 'ipc://ipc_5590'

    INTERVAL = 0.040  # both sources at 25 samples/s
    SKEW     = 0.2    # seconds source 2's clock sits ahead of source 1's
    DURATION = 3.0

    def tearDown(self):
        gc.collect()

    def _run(self, tolerance):
        """Drive both sources for DURATION with their clocks SKEW apart, and return the batches delivered."""

        payload = b'x' * 1024
        stop    = Event()
        batches = []

        def pump(sendr, topic, skew):
            while not stop.is_set():
                sendr.send(lambda: {topic: [{'ts': time_ns() / 1e9 + skew}, payload]}, timeout=1000)
                sleep(self.INTERVAL)

        sendr1 = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                recvr = ZMQReceiver([self.CLIENT1, self.CLIENT2], 'client', pair_by_ts=True,
                    pair_ts_tolerance=tolerance)

                try:
                    recvr.recv(timeout=0)  # prime the senders with a first request

                    sleep(0.2)

                    threads = [
                        Thread(target=pump, args=(sendr1, 'main', 0.0), daemon=True),
                        Thread(target=pump, args=(sendr2, 'othr', self.SKEW), daemon=True),
                    ]

                    for thread in threads:
                        thread.start()

                    try:
                        t_end = time_ns() + int(self.DURATION * 1e9)

                        while time_ns() < t_end:
                            if (res := recvr.recv(timeout=500)) is not None:
                                batches.append(res[0])

                    finally:
                        stop.set()

                        for thread in threads:
                            thread.join(2)

                finally:
                    recvr.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()

        return batches

    def test_sources_further_apart_than_the_tolerance_deliver_nothing_and_say_so(self):
        with self.assertLogs(zeromq_logger, level='WARNING') as logs:
            batches = self._run(tolerance=self.SKEW / 4)

        self.assertEqual(batches, [], 'a batch went out whose frames are further apart than the tolerance')

        refusals = [line for line in logs.output if 'pair_ts_tolerance' in line]

        self.assertTrue(refusals, f'nothing logged to tell this apart from a stall, got {logs.output}')

        # Rate limited, so a 3 s run at 25 fps is a handful of lines and not a few hundred.
        self.assertLess(len(refusals), 10, f'the over-tolerance warning is not rate limited, {len(refusals)} lines')

        self.assertIn(f'{self.SKEW / 4:.3f} s', refusals[0], 'the warning does not name the tolerance')

    def test_a_tolerance_wider_than_the_skew_still_delivers(self):
        """The other half, so the test above is about the tolerance and not about the fixture failing to run."""

        batches = self._run(tolerance=self.SKEW * 4)

        self.assertGreater(len(batches), 20, 'too few batches delivered to say anything')

        for batch in batches:
            self.assertEqual(sorted(batch), ['main', 'othr'], 'a batch went out without both sources in it')


class TestJoinBarrierLivelock(unittest.TestCase):
    """A join that stops delivering for good after ONE of its sources skips a single message id.

    This is the shape of the production freeze: a receiver joining two cameras delivered its last batch at id
    28459 and then spent 17 minutes logging `received newer message id N than expected 28460` at 5 Hz, with both
    cameras still publishing, `process()` never called and the pod still reporting healthy.

    Three things have to be true at once, and all three are true of the production pipeline:

      1. The sources are topic MAPPED (`addr;main>camA`), which is what two cameras that both publish 'main' have
      to do to join. A mapped source gets `recvd_new` as a dict, so `Sender.new_recv()` hands back a dict of Nones
      rather than None, so `process_msg` never takes its `recvd is None` first-message branch. Every message whose
      id is not exactly the barrier therefore lands in the `else` branch, which invalidates the OTHER source's
      held frame. Unmapped sources get `recvd = None` and the first message of each round initializes instead of
      invalidating, which is why an unmapped fixture of the same shape does not reproduce this at all.

      2. The two sources' published ids differ by one. One skipped id is enough, and the sender skips ids on its
      own: the `downstream requested newer message id` path sets `min_send_id = prev_id + 1` without publishing
      that id. A frame dropped at ZMQ_PUB_HWM does the same thing to the id sequence the receiver reads.

      3. The receiver calls `recv()` with a timeout no longer than ZMQ_POLL_TIMEOUT, which is what `Filter`
      does (`POLL_TIMEOUT_MS`, 100 ms). One such call issues exactly one request, and it is issued before any
      message of that round is read, so it carries `min_recv_id - 1` computed from the STALE `self.prev_id`. That
      is what keeps the sender-side fast forward from ever firing again and closing the gap: with a longer
      timeout the receiver loops, re-requests with the climbed barrier, and the fast forward rescues the join.

    From there it is self-sustaining. `min_recv_id` is a local, reset to `self.prev_id + 1` at the top of every
    `recv()`, and `self.prev_id` only moves on a delivery, so every round re-runs from the same stale barrier:
    source A's frame arrives and takes the barrier, source B's frame arrives one id higher and destroys A's, the
    round ends with nothing to deliver, and the next round does it again forever.
    """

    SERVER1 = 'ipc://ipc_5580'
    SERVER2 = 'ipc://ipc_5582'

    INTERVAL   = 0.200   # both sources at 5 fps, the rate the cameras ran at
    RECV_MS    = 100     # == ZMQ_POLL_TIMEOUT, == Filter's POLL_TIMEOUT_MS
    SKIP_AFTER = 5       # source B skips one id on its 6th frame
    DURATION   = 6.0
    MAX_GAP    = 1.0     # five frame intervals without a batch is a stall, not jitter

    def tearDown(self):
        gc.collect()

    def _run(self, **recvr_kwargs):
        """Drive both sources, skip one id on B, and return (max seconds with no batch, batches, sends)."""

        payload = b'x' * 4096
        stop    = Event()
        sends   = {'A': 0, 'B': 0}

        def pump(sendr, name):
            n = 0

            while not stop.is_set():
                t_cap = time_ns()

                if name == 'B' and n == self.SKIP_AFTER:
                    sendr.min_send_id += 1  # the id this source never publishes, exactly what a fast forward leaves behind

                n += 1

                if sendr.send(lambda: {'main': [{'ts': t_cap / 1e9}, payload]}, timeout=int(self.INTERVAL * 1000)) is not None:
                    sends[name] += 1

                if (left := self.INTERVAL - (time_ns() - t_cap) / 1e9) > 0:
                    sleep(left)

        sendr1 = ZMQSender(self.SERVER1, 'server1')

        try:
            sendr2 = ZMQSender(self.SERVER2, 'server2')

            try:
                recvr = ZMQReceiver([(self.SERVER1, [('main', 'camA')]), (self.SERVER2, [('main', 'camB')])],
                    'client', **recvr_kwargs)

                try:
                    recvr.recv(timeout=0)  # prime the senders with a first request

                    sleep(0.2)

                    threads = [Thread(target=pump, args=(sendr1, 'A'), daemon=True),
                               Thread(target=pump, args=(sendr2, 'B'), daemon=True)]

                    for thread in threads:
                        thread.start()

                    try:
                        batches  = 0
                        t_end    = time_ns() + int(self.DURATION * 1e9)
                        t_last   = time_ns()
                        max_gap  = 0.0

                        while time_ns() < t_end:
                            if recvr.recv(timeout=self.RECV_MS) is not None:
                                batches += 1
                                max_gap  = max(max_gap, (time_ns() - t_last) / 1e9)
                                t_last   = time_ns()

                        max_gap = max(max_gap, (time_ns() - t_last) / 1e9)

                    finally:
                        stop.set()

                        for thread in threads:
                            thread.join(2)

                finally:
                    recvr.destroy()

            finally:
                sendr2.destroy()

        finally:
            sendr1.destroy()

        return max_gap, batches, sends

    def test_one_skipped_id_stops_the_default_join(self):
        """The defect itself, asserted directly: the default join stops delivering at the skip and stays stopped.

        This used to be the same assertion as the test below under `@unittest.expectedFailure`, which was not
        worth much: `expectedFailure` counts ANY failure, so the test went on reporting "the livelock still
        reproduces" if the precondition below broke, if a socket raised, or if the fixture stopped driving the
        sources at all. Asserting the stall is what makes it a tripwire, the same way
        `TestPairByTs.test_pairing_skew_is_large_without_it` is one.

        Read it as a statement about the baseline, not as a requirement. If it ever fails it means the default
        join got BETTER, which is the signal to delete this test and keep only the flag-on one below.
        """

        max_gap, batches, sends = self._run()

        self.assertGreater(min(sends.values()), 20,
            f'the sources stopped publishing ({sends}), so this run measures nothing')

        self.assertGreater(max_gap, self.MAX_GAP,
            f'the default join went at most {max_gap:.2f} s without a batch after one source skipped a single '
            f'message id, under the {self.MAX_GAP:.2f} s that counts as a stall, over a run of '
            f'{self.DURATION:.0f} s in which the sources published {sends} frames and the join delivered '
            f'{batches}. The livelock no longer reproduces, so the test below no longer proves anything')

    def test_pair_by_ts_survives_one_skipped_id(self):
        """The same run with the flag on. Each source keeps its own barrier, so a skipped id costs one frame."""

        max_gap, batches, sends = self._run(pair_by_ts=True)

        self.assertGreater(min(sends.values()), 20,
            f'the sources stopped publishing ({sends}), so this run measures nothing')

        self.assertLess(max_gap, self.MAX_GAP,
            f'{max_gap:.2f} s with no batch delivered after one source skipped a single message id, over a run '
            f'of {self.DURATION:.0f} s in which the sources published {sends} frames and the join delivered '
            f'{batches}')


if __name__ == '__main__':
    unittest.main()
