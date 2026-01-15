#!/usr/bin/env python

import gc
import logging
import os
import unittest
from queue import Queue
from random import randint
from threading import Thread
from time import sleep

from openfilter.filter_runtime.zeromq import ZMQStateRecv, ZMQStateSend, ZMQReceiver, ZMQSender, logger as zeromq_logger

zeromq_logger.setLevel(int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper())))


def recvstate(msg_id):
    return ZMQStateRecv(msg_id)

def sendstate(msg_id):
    return ZMQStateSend(msg_id)

def send(sendr, *args, **kwargs):
    return None if (res := sendr.send(*args, **kwargs)) is None else res[0]

def recvl(recvr, *args, **kwargs):
    return None if (res := recvr.recv(*args, **kwargs)) is None else (res[1][0], res[0])

def recv(recvr, *args, **kwargs):
    return None if (res := recvr.recv(*args, **kwargs)) is None else res


class TestZeroMQOld(unittest.TestCase):
    def tearDown(self):
        # Force garbage collection to clean up file descriptors
        gc.collect()

    def test_old_general(self):
        def thread(queue: Queue, queue_oob: Queue):
            sendr = ZMQSender(['tcp://*:5550', 'ipc://./tmp_pipe'], 'server', lambda m: queue_oob.put(m))

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
                recvr2     = ZMQReceiver([('ipc://./tmp_pipe', [('main', 'main')])], 'client2', lambda m: queue2_oob.put(m))

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


if __name__ == '__main__':
    unittest.main()
