#!/usr/bin/env python

import logging
import os
import unittest
from itertools import repeat, takewhile
from queue import Queue
from random import choice, randint
from threading import Event, Thread
from time import sleep

from openfilter.filter_runtime.rolllog import RollLog
from openfilter.filter_runtime.utils import rndstr, setLogLevelGlobal

logger = logging.getLogger(__name__)

log_level = int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper()))

setLogLevelGlobal(log_level)

TEST_DIR = 'logs/test'


def deldir(path):
    try:
        fnms = os.listdir(path)
    except Exception:
        return

    for fnm in fnms:
        try:
            os.unlink(os.path.join(path, fnm))
        except Exception:
            pass

    try:
        os.rmdir(path)
    except Exception:
        pass


def rndstrs(count=100, min_len=30, max_len=130):
    return [rndstr(randint(min_len, max_len)) for _ in range(count)]


def rndstrs_with_nl(count=100, min_len=30, max_len=130):
    return [rndstr(randint(min_len, max_len), xtra='\n') for _ in range(count)]


def rndobjs(count=100, min_len=30, max_len=130):
    return [rndstr(randint(min_len, max_len), xtra='\n') if randint(0, 1) else
        choice([randint(0, 0xffffffff), None, False, True, [rndstr(4, xtra='\n')], {rndstr(4, xtra='\n'): rndstr(4, xtra='\n')}])
        for _ in range(count)]


class TestRollLog(unittest.TestCase):
    def test_rollover_bin(self):
        rl = RollLog(TEST_DIR, 'bin', file_size=10, total_size=20)

        try:
            rl.write(b'0123456789')

            self.assertEqual(len(rl.logfiles), 1)

            p0 = rl.logfiles[0].path

            rl.write(b'01234567')

            self.assertEqual(len(rl.logfiles), 2)
            self.assertEqual(rl.logfiles[0].path, p0)

            p1 = rl.logfiles[1].path

            rl.write(b'8')

            self.assertEqual(len(rl.logfiles), 2)
            self.assertEqual(rl.logfiles[0].path, p0)
            self.assertEqual(rl.logfiles[1].path, p1)

            rl.write(b'9')

            self.assertEqual(len(rl.logfiles), 2)
            self.assertEqual(rl.logfiles[0].path, p0)
            self.assertEqual(rl.logfiles[1].path, p1)

            rl.write(b'0')

            self.assertEqual(len(rl.logfiles), 2)
            self.assertEqual(rl.logfiles[0].path, p1)

            p2 = rl.logfiles[1].path

            rl.write(b'12345678')

            self.assertEqual(len(rl.logfiles), 2)
            self.assertEqual(rl.logfiles[0].path, p1)
            self.assertEqual(rl.logfiles[1].path, p2)

            rl.write(b'901234567890')

            self.assertEqual(len(rl.logfiles), 1)
            self.assertEqual(rl.logfiles[0].path, p2)

            rl.write(b'123456789')

            self.assertEqual(len(rl.logfiles), 1)

            p3 = rl.logfiles[0].path

            rl.write(b'123456789')

            self.assertEqual(len(rl.logfiles), 1)
            self.assertEqual(rl.logfiles[0].path, p3)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_external_deletions_read_bin(self):
        rl = RollLog(TEST_DIR, 'bin', file_size=2)

        try:
            rl.write(b'00')
            rl.write(b'11')
            rl.write(b'22')
            rl.write(b'33')
            rl.write(b'44')
            rl.write(b'55')
            rl.write(b'66')
            rl.write(b'77')
            rl.write(b'88')
            rl.write(b'9')

            os.unlink(rl.logfiles[0].path)
            os.unlink(rl.logfiles[2].path)
            os.unlink(rl.logfiles[3].path)
            os.unlink(rl.logfiles[6].path)
            os.unlink(rl.logfiles[9].path)

            read = b''.join(takewhile(lambda x: x is not None, (rl.read_block() for _ in repeat(None))))

            self.assertEqual(read, b'1144557788')

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_external_deletions_write_bin(self):
        rl = RollLog(TEST_DIR, 'bin', file_size=2)

        try:
            self.assertEqual(rl.write(b'0'), 1)
            self.assertEqual(rl.write(b'1'), 1)
            self.assertEqual(rl.write(b'2'), 1)

            deldir(TEST_DIR)

            self.assertEqual(rl.write(b'3'), 1)
            self.assertEqual(rl.write(b'4'), 0)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_write_read_binl(self):
        rl = RollLog(TEST_DIR, 'binl', file_size=100)

        try:
            rl.write(b'123')
            rl.write(b'456')
            rl.write(b'789')

            self.assertEqual(rl.read(), b'123')
            self.assertEqual(rl.read(), b'456')
            self.assertEqual(rl.read(), b'789')

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_write_txt_read_binl(self):
        rl = RollLog(TEST_DIR, 'txt', file_size=100)

        try:
            rss = rndstrs()

            for rs in rss:
                rl.write(rs)

            rss_read = [s.decode() for s in takewhile(lambda x: x is not None, (rl.read('binl') for _ in repeat(None)))]

            self.assertEqual(rss_read, rss)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_read_block_bin(self):
        rl = RollLog(TEST_DIR, 'bin', file_size=100)

        try:
            rss = rndstrs_with_nl()

            for rs in rss:
                rl.write(rs.encode())

            rss      = ''.join(rss).encode()
            rss_read = b''.join(takewhile(lambda x: x is not None, (rl.read_block() for _ in repeat(None))))

            self.assertEqual(rss_read, rss)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_read_block_binl(self):
        rl = RollLog(TEST_DIR, 'binl', file_size=100)

        try:
            rss = [s.encode() for s in rndstrs()]

            for rs in rss:
                rl.write(rs)

            rss_read = sum(takewhile(lambda x: x is not None, (rl.read_block() for _ in repeat(None))), start=[])

            self.assertEqual(rss_read, rss)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_read_block_txt(self):
        rl = RollLog(TEST_DIR, 'txt', file_size=100)

        try:
            rss = rndstrs()

            for rs in rss:
                rl.write(rs)

            rss_read = sum(takewhile(lambda x: x is not None, (rl.read_block() for _ in repeat(None))), start=[])

            self.assertEqual(rss_read, rss)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_read_block_json(self):
        rl = RollLog(TEST_DIR, 'json', file_size=100)

        try:
            rss = rndobjs()

            for rs in rss:
                rl.write(rs)

            rss_read = sum(takewhile(lambda x: x is not None, (rl.read_block() for _ in repeat(None))), start=[])

            self.assertEqual(rss_read, rss)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_seek_block_bin(self):
        rl = RollLog(TEST_DIR, 'bin', file_size=100)

        try:
            rss = rndstrs_with_nl()

            for rs in rss:
                rl.write(rs.encode())

            while rl.read_block() is not None:
                pass

            rl.seek_block()

            rss_read = b''.join(takewhile(lambda x: x is not None, (rl.read_block() for _ in repeat(None))))
            rss      = ''.join(rss).encode()

            self.assertEqual(rss_read, rss)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_seek_block_txt(self):
        rl = RollLog(TEST_DIR, 'txt', file_size=100)

        try:
            rss = rndstrs()

            for rs in rss:
                rl.write(rs)

            while rl.read_block() is not None:
                pass

            rl.seek_block()

            rss_read = sum(takewhile(lambda x: x is not None, (rl.read_block() for _ in repeat(None))), start=[])

            self.assertEqual(rss_read, rss)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_seek_block_json(self):
        rl = RollLog(TEST_DIR, 'json', file_size=100)

        try:
            rss = rndobjs()

            for rs in rss:
                rl.write(rs)

            while rl.read_block() is not None:
                pass

            rl.seek_block()

            rss_read = sum(takewhile(lambda x: x is not None, (rl.read_block() for _ in repeat(None))), start=[])

            self.assertEqual(rss_read, rss)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_tell_bin(self):
        rl = RollLog(TEST_DIR, 'bin', file_size=2)

        try:
            self.assertEqual(rl.tell(), ('start', 0))

            rl.write(b'0')

            self.assertNotIn((t := rl.tell())[0], ('start', 'end'))
            self.assertEqual(t[1], 0)
            self.assertEqual(rl.read(), b'0')
            self.assertEqual((t2 := rl.tell())[0], t[0])
            self.assertEqual(t2[1], 1)

            rl.write(b'1')

            self.assertEqual((t2 := rl.tell())[0], t[0])
            self.assertEqual(t2[1], 1)
            self.assertEqual(rl.read(), b'1')
            self.assertEqual((t2 := rl.tell())[0], t[0])
            self.assertEqual(t2[1], 2)
            self.assertEqual(rl.read(), None)
            self.assertEqual((t2 := rl.tell())[0], t[0])
            self.assertEqual(t2[1], 2)

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_tell_seek_bin(self):
        rl = RollLog(TEST_DIR, 'bin', file_size=2)

        try:
            rl.write(b'0')

            self.assertEqual(rl.read(), b'0')

            pos = rl.tell()

            rl.write(b'12')
            rl.write(b'34')

            self.assertEqual(rl.read(), b'12')

            pos2 = rl.tell()

            self.assertEqual(rl.read(), b'34')

            rl.seek(pos)

            self.assertEqual(rl.read(), b'12')
            self.assertEqual(rl.read(), b'34')

            rl.seek(pos2)

            self.assertEqual(rl.read(), b'34')

            rl.seek(pos)

            self.assertEqual(rl.read(), b'12')
            self.assertEqual(rl.read(), b'34')

            os.unlink(rl.logfiles[-2].path)

            rl.seek(pos)

            self.assertEqual(rl.read(), b'34')

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_head_txt(self):
        rl = RollLog(TEST_DIR, 'txt', file_size=100)

        try:
            try:
                rss = rndstrs()

                for rs in rss:
                    rl.write(rs)

            finally:
                rl.close()

            for rs in rss:
                ro = RollLog(TEST_DIR, 'txt', rdonly=True, head=TEST_DIR + '/head.json')

                try:
                    self.assertEqual(ro.read(), rs)
                finally:
                    ro.close()

        finally:
            deldir(TEST_DIR)


    def test_refresh_txt_1(self):
        rl = RollLog(TEST_DIR, 'txt', file_size=4)

        try:
            ro = RollLog(TEST_DIR, 'txt', rdonly=True, autorefresh=False)

            try:
                rl.write('000')
                rl.write('111')

                self.assertNotEqual(ro.logfiles, rl.logfiles)
                self.assertIs(ro.read(), None)

                ro.refresh()

                self.assertEqual(ro.logfiles, rl.logfiles)
                self.assertEqual(ro.read(), '000')
                self.assertEqual(ro.read(), '111')

                rl.write('222')

                self.assertNotEqual(ro.logfiles, rl.logfiles)
                self.assertIs(ro.read(), None)

                ro.refresh()

                self.assertEqual(ro.logfiles, rl.logfiles)
                self.assertEqual(ro.read(), '222')

                rl.write('3')
                rl.write('4')

                self.assertNotEqual(ro.logfiles, rl.logfiles)
                self.assertIs(ro.read(), None)

                ro.refresh()

                self.assertEqual(ro.logfiles, rl.logfiles)
                self.assertIs(ro.read(), '3')

                self.assertEqual(rl.logfiles[-1].size, 4)  # the '3\n4\n'
                self.assertIs(rl.write_file, None)  # the '3\n4\n'

                os.unlink(rl.logfiles[-1].path)

                rl.write('5')
                ro.refresh()

                self.assertIs(ro.read(), '5')

            finally:
                ro.close()

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_refresh_txt_2(self):
        rl = RollLog(TEST_DIR, 'txt', file_size=4)

        try:
            ro = RollLog(TEST_DIR, 'txt', rdonly=True, autorefresh=False)

            try:
                rl.write('000')
                rl.write('1')
                rl.write('2')
                rl.write('333')

                self.assertNotEqual(ro.logfiles, rl.logfiles)
                self.assertIs(ro.read(), None)

                ro.refresh()

                self.assertEqual(ro.logfiles, rl.logfiles)
                self.assertEqual(ro.read(), '000')
                self.assertEqual(ro.read(), '1')

                os.unlink(rl.logfiles[0].path)
                os.unlink(rl.logfiles[2].path)

                ro.refresh()

                self.assertEqual(len(ro.logfiles), 1)
                self.assertEqual(ro.read(), '2')
                self.assertEqual(ro.read(), None)

                rl.write('4')
                rl.write('')
                rl.write('')

                ro.refresh()

                self.assertEqual(ro.read(), '4')

                os.unlink(rl.logfiles[-1].path)

                ro.refresh()

                self.assertEqual(ro.read(), None)

            finally:
                ro.close()

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_autorefresh_new_files_bin(self):
        rl = RollLog(TEST_DIR, 'bin', file_size=4)

        try:
            ronr = RollLog(TEST_DIR, 'bin', rdonly=True, autorefresh=False)

            try:
                roar = RollLog(TEST_DIR, 'bin', rdonly=True)

                try:
                    rl.write(b'0000')

                    self.assertEqual(ronr.read(), None)
                    self.assertEqual(roar.read(), b'0000')  # first autorefresh location in code

                    ronr.refresh()

                    self.assertEqual(ronr.read(), b'0000')

                    ronr.read_file.close()
                    roar.read_file.close()

                    ronr.read_file = None
                    roar.read_file = None

                    rl.write(b'1111')

                    os.unlink(rl.logfiles[0].path)

                    self.assertEqual(ronr.read(), None)
                    self.assertEqual(roar.read(), b'1111')  # second autorefresh location in code

                    ronr.refresh()

                    self.assertEqual(ronr.read(), b'1111')

                    rl.write(b'2222')

                    self.assertEqual(ronr.read(), None)
                    self.assertEqual(roar.read(), b'2222')  # third autorefresh location in code

                    ronr.refresh()

                    self.assertEqual(ronr.read(), b'2222')

                finally:
                    roar.close()

            finally:
                ronr.close()

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_autorefresh_no_new_files_bin(self):
        rl = RollLog(TEST_DIR, 'bin', file_size=4)

        try:
            ronr = RollLog(TEST_DIR, 'bin', rdonly=True, autorefresh=False)

            try:
                roar = RollLog(TEST_DIR, 'bin', rdonly=True)

                try:
                    self.assertEqual(ronr.read(), None)
                    self.assertEqual(roar.read(), None)  # first autorefresh location in code

                    rl.write(b'0000')
                    ronr.refresh()

                    self.assertEqual(ronr.read(), b'0000')
                    self.assertEqual(roar.read(), b'0000')  # this time will succeed

                    ronr.read_file.close()
                    roar.read_file.close()

                    ronr.read_file = None
                    roar.read_file = None

                    os.unlink(rl.logfiles[0].path)

                    self.assertEqual(ronr.read(), None)
                    self.assertEqual(roar.read(), None)  # second autorefresh location in code

                    rl.write(b'1111')
                    ronr.refresh()

                    self.assertEqual(ronr.read(), b'1111')
                    self.assertEqual(roar.read(), b'1111')  # this time will succeed

                    self.assertEqual(ronr.read(), None)
                    self.assertEqual(roar.read(), None)  # third autorefresh location in code

                    rl.write(b'2222')

                    ronr.refresh()

                    self.assertEqual(ronr.read(), b'2222')
                    self.assertEqual(roar.read(), b'2222')  # this time will succeed

                finally:
                    roar.close()

            finally:
                ronr.close()

        finally:
            rl.close()
            deldir(TEST_DIR)


    def test_threadsafe_read_write_txt(self):
        rl = RollLog(TEST_DIR, 'txt', file_size=150, total_size=100_000_000)

        try:
            NSTRS = 10_000
            NLOOP = 10
            EXPECTED_COUNT = NLOOP * NSTRS

            def thread_func(queue, stop_evt, expected_count):
                count = 0
                while count < expected_count:
                    if stop_evt.is_set():
                        break
                    if data := rl.read():
                        queue.put(data)
                        count += 1

                queue.put(None)

            strs     = rndstrs(count=NSTRS, min_len=50, max_len=150)
            queue    = Queue()
            stop_evt = Event()
            thread   = Thread(target=thread_func, args=(queue, stop_evt, EXPECTED_COUNT), daemon=True)

            try:
                thread.start()

                for i in range(EXPECTED_COUNT):
                    rl.write(strs[i % NSTRS])

                # Wait for reader to finish (with timeout to avoid hanging)
                thread.join(timeout=60)

                i = 0

                while (data := queue.get(timeout=1)) is not None:
                    self.assertEqual(data, strs[i % NSTRS])

                    i += 1

                self.assertEqual(i, EXPECTED_COUNT)

            finally:
                stop_evt.set()
                thread.join(timeout=5)

        finally:
            rl.close()
            deldir(TEST_DIR)


if __name__ == '__main__':
    unittest.main()
