import importlib.util, importlib.metadata
import logging
import os
import re
import signal
from base64 import b64encode
from collections import deque
from collections.abc import Mapping, Sequence, Set
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from json import loads as json_loads
from random import choice
from threading import Condition, Event, Thread
from time import sleep, time
from typing import Any, Callable

from numpy import generic as np_generic, ndarray as np_ndarray

__all__ = [
    'JSONLiteral', 'JSONType', 'json_getval', 'json_sanitize',
    'sanitize_filename', 'sanitize_pathname', 'simpledeepcopy', 'dict_without',
    'split_commas_maybe', 'rndstr', 'sizestr', 'secstr', 'timestr',
    'parse_time_interval', 'parse_date_and_or_time',
    'pascal_to_snake_case', 'hide_uri_pwds', 'hide_uri_users_and_pwds', 'levenshteinish_distance', 'once',
    'get_real_module_name', 'get_packages', 'get_package_version',
    'set_env_vars', 'running_in_container', 'setLogLevelGlobal',
    'adict', 'FnmLock', 'Deque', 'DaemonicTimer', 'SignalStopper'
]


JSONLiteral = None | bool | int | float | str
JSONType    = JSONLiteral | list | dict

def json_getval(val: str) -> JSONType:
    """Try to dejsonify, otherwise return string as is."""

    try:
        return json_loads(val)
    except Exception:
        return val

def json_sanitize(val: Any, loose=False) -> JSONType:
    """Sanitize for json.dumps() compatible, two levels, `loose` will convert datetime to iso text and dataclasses for
    example. Non-loose will convert stuff like Fraction and nunpy.generic."""

    if isinstance(val, JSONLiteral):
        return val
    if isinstance(val, (list, tuple)):
        return [json_sanitize(v, loose) for v in val]
    if isinstance(val, dict):
        return {str(k): json_sanitize(v, loose) for k, v in val.items()} if loose else {k: json_sanitize(v, loose) for k, v in val.items()}
    if isinstance(val, (bytes, bytearray)):
        return b64encode(val)
    if isinstance(val, np_generic):
        return val.item()
    if isinstance(val, np_ndarray):
        return [json_sanitize(v, loose) for v in val] if val.shape else json_sanitize(val.item(), loose)

    mod  = (cls := val.__class__).__module__
    name = cls.__qualname__

    # if mod == 'numpy':
    #     if name in ('float16', 'float32', 'float64', 'longdouble'):
    #         return float(val)
    #     if name in ('int8', 'uint8', 'int16', 'uint16', 'int32', 'uint32', 'int64', 'uint64'):
    #         return int(val)
    #     if name == 'bool_':
    #         return bool(val)
    #     if name == 'str_':
    #         return str(val)
    #     if name == 'ndarray':
    #         return [json_sanitize(v, loose) for v in val] if val.shape else json_sanitize(val.item(), loose)

    if loose:
        if isinstance(val, Mapping):
            return {str(k): json_sanitize(v, loose) for k, v in val.items()}
        if isinstance(val, Sequence):
            return [json_sanitize(v, loose) for v in val]

        if mod == 'datetime':
            if name == 'datetime':
                return val.isoformat()

        elif is_dataclass(val):
            return json_sanitize(asdict(val), loose)

    if mod == 'fractions':
        if name == 'Fraction':
            return int(v) if (v := float(val)).is_integer() else v

    elif mod == 'decimal':
        if name == 'Decimal':
            return float(val) if val % 1 else int(val)

    raise ValueError(f'unjsonable{" (loose)" if loose else ""} type: {(r if len(r := repr(val)) <= 64 else f"{r[:64]}...")}')


sanitize_filename_tbl = str.maketrans('<>:"\\|?*\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f/', '_' * 41)

def sanitize_filename(fnm: str) -> str:
    return fnm.translate(sanitize_filename_tbl)


sanitize_pathname_tbl = str.maketrans('<>:"\\|?*\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f', '_' * 40)

def sanitize_pathname(path: str) -> str:
    return path.translate(sanitize_pathname_tbl)


def simpledeepcopy(obj: Any) -> Any:
    """Only deep copy tuples, lists and dicts (and their subclasses), doesn't deepcopy dict keys (they are immutable)."""

    if isinstance(obj, (list, tuple)):
        return obj.__class__([simpledeepcopy(v) for v in obj])
    if isinstance(obj, dict):
        return obj.__class__({k: simpledeepcopy(v) for k, v in obj.items()})

    return obj


def dict_without(d: dict, without: str | Sequence | Mapping) -> dict:
    """Return a dictionary (or subclass, same as passed in) without the keys in `without`. Do not make the mistake of
    passing `without` as a string if you don't want each of its letters to be excluded rather than the whole string."""

    if isinstance(without, str):
        without = {without}
    elif not isinstance(without, (Mapping, Set)):
        without = set(without)

    return d.__class__((k, v) for k, v in d.items() if k not in without)


def split_commas_maybe(v: Any) -> Any:
    return ([s.strip() for s in v.split(',')] if v.strip() else []) if isinstance(v, str) else v


def rndstr(count: int, pool: int = 62, xtra: str = '') -> str:
    s = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_-'[:min(64, pool)]

    if xtra:
        s += xtra

    return ''.join(choice(s) for _ in range(count))


def sizestr(b: int) -> str:
    """3 significant digit size (bytes)."""

    return f'{b}b' if b < 1000 else \
        f'{b/1000:0.2f}k'          if b < 10000 else          f'{b/1000:0.1f}k'          if b < 100000 else          f'{b//1000}k'          if b < 1000000 else \
        f'{b/1000000:0.2f}M'       if b < 10000000 else       f'{b/1000000:0.1f}M'       if b < 100000000 else       f'{b//1000000}M'       if b < 1000000000 else \
        f'{b/1000000000:0.2f}G'    if b < 10000000000 else    f'{b/1000000000:0.1f}G'    if b < 100000000000 else    f'{b//1000000000}G'    if b < 1000000000000 else \
        f'{b/1000000000000:0.2f}T' if b < 10000000000000 else f'{b/1000000000000:0.1f}T' if b < 100000000000000 else f'{b//1000000000000}T'


def secstr(ns: int) -> str:
    """3 significant digit (nanoseconds)."""

    return f'{ns}ns' if ns < 1000 else \
        f'{ns/1000:0.2f}us'      if ns < 10000 else       f'{ns/1000:0.1f}us'      if ns < 100000 else       f'{ns//1000}us'      if ns < 1000000 else \
        f'{ns/1000000:0.2f}ms'   if ns < 10000000 else    f'{ns/1000000:0.1f}ms'   if ns < 100000000 else    f'{ns//1000000}ms'   if ns < 1000000000 else \
        f'{ns/1000000000:0.2f}s' if ns < 10000000000 else f'{ns/1000000000:0.1f}s' if ns < 100000000000 else f'{ns//1000000000}s'


def timestr(s: float) -> str:
    """Common time string [[[days:]hrs:]mins:]secs[.subsecs] from seconds."""

    ss = f'{ss:0.3f}'[1:] if (ss := s - (s := int(s))) else ''

    return f'{s}{ss}' if s < 60 else \
        f'{s // 60}:{s % 60:02}{ss}' if s < 3600 else \
        f'{s // 3600}:{(s % 3600) // 60:02}:{s % 60:02}{ss}' if s < 86400 else \
        f'{s // 86400}d:{(s % 86400) // 3600:02}:{(s % 3600) // 60:02}:{s % 60:02}{ss}'


def parse_time_interval(text: str) -> float:
    """Parse time of format [[[days[d]:]hrs:]mins:]secs[.subsecs] to a float count of seconds."""

    parts = ('0:0:0:' + text).split(':')[-4:]

    if parts[0].endswith('d'):
        parts[0] = parts[0][:-1]

    return sum(a * b for a, b in zip([24*60*60, 60*60, 60, 1], [float(v) for v in parts]))


def parse_date_and_or_time(s: str, utc: bool = False) -> datetime:
    """Parse simple (or isoformat) datetime or date or time representation in UTC or local.

    Returns:
        A datetime with timezone set appropriately. If date is not provided then today is used. If time is not provided
        then midnight is used.

    Notes:
        * Accepted date format are 'yyyy/mm/dd', 'yy/mm/dd', 'mm/dd' or 'dd', separator is '/' or '-'.
        * Accepted times are 24 hour clock 'hh:mm:ss.ms', 'hh:mm:ss', 'hh:mm', 'mm:ss.ms' or 'ss.ms'.
        * Date with time is accepted separated by a space or a 'T', e.g. 'yy-mm-dd hh:mm:ss' or 'mm/ddTss.ms'.
        * Datetime can also be ISO format.
    """

    tz = timezone.utc if utc else datetime.now().astimezone().tzinfo

    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        dt = None

    if dt is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)

    else:
        dt = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)

        def parse_date(s):
            nonlocal dt

            try:
                if (l := len(t := s.replace('-', '/').split('/'))) > 3:
                    raise ValueError(f'invalid date {s!r}')
                elif l == 2:
                    t = [dt.year, *t]
                elif l == 1:
                    t = [dt.year, dt.month, *t]

                dt = dt.replace(year=(y := int(t[0])) + (2000 if y < 100 else 0), month=int(t[1]), day=int(t[2]))

            except Exception:
                raise ValueError(f'invalid date {s!r}')

        def parse_time(s):
            nonlocal dt

            try:
                if (c := s.count(':')) > 2:
                    raise ValueError

                t  = (f'0:0:{s}{"" if "." in s or c != 1 else ":0"}'.split(':'))[-3:]
                dt = dt.replace(hour=int(t[0]), minute=int(t[1]), second=int(float(t[2])), microsecond=int(float(t[2]) % 1 * 1_000_000))

            except Exception:
                raise ValueError(f'invalid time {s!r}')

        if (l := len(t := s.replace('T', ' ').split(' '))) > 2:
            raise ValueError(f'invalid date and/or time {s!r}')

        elif l == 2:
            parse_date(t[0])
            parse_time(t[1])

        elif ':' not in s and '.' not in s:
            parse_date(t[0])

        else:
            parse_time(t[0])

    return dt


def pascal_to_snake_case(s: str) -> str:
    cs = []
    ss = s + 'U'
    ll = False

    for i, c in enumerate(s):
        cs.append(c if (lc := c.islower()) else f'_{c.lower()}' if ll or ss[i + 1].islower() else c.lower())
        ll = lc

    return ''.join(cs).lstrip('_')


re_sub_uri_pwd = re.compile(r'\b ( [a-zA-Z][a-zA-Z0-9+\-.]* :// [^:@]+: ) [^@]* ( @ [^\s/?#]+ )', re.VERBOSE)

def hide_uri_pwds(text: str) -> str:
    """Censor anything that looks like a URI password in a string."""

    return re_sub_uri_pwd.sub(r'\g<1>****\g<2>', text)


re_sub_uri_user_and_pwd = re.compile(r'\b ( [a-zA-Z][a-zA-Z0-9+\-.]* :// ) [^:@]+: [^@]* ( @ [^\s/?#]+ )', re.VERBOSE)

def hide_uri_users_and_pwds(text: str) -> str:
    """Censor anything that looks like a URI user:password in a string."""

    return re_sub_uri_user_and_pwd.sub(r'\g<1>****\g<2>', text)


def levenshteinish_distance(a: str, b: str, max_cost: int | None = None) -> int:
    from os.path import commonprefix

    MOVE_COST = 2
    CASE_COST = 1

    substitution_cost = lambda a, b: 0 if a == b else CASE_COST if a.casefold() == b.casefold() else MOVE_COST

    if a == b:
        return 0

    if l := len(commonprefix((a, b))):  # trim away common prefix
        a = a[l:]
        b = b[l:]

    if l := len(commonprefix((a[::-1], b[::-1]))):  # trim away common suffix
        a = a[:-l]
        b = b[:-l]

    if not a:
        return len(b) * MOVE_COST

    if not b:
        return len(a) * MOVE_COST

    if (b_size := len(b)) < (a_size := len(a)):  # prefer shorter str
        a     , b      = b,      a
        a_size, b_size = b_size, a_size

    if max_cost is not None and (b_size - a_size) * MOVE_COST > max_cost:  # quick fail when a match is impossible
        return max_cost + 1

    buffer = [i * MOVE_COST for i in range(1, a_size + 1)]
    result = 0

    for b_index in range(b_size):
        code     = b[b_index]
        distance = result = b_index * MOVE_COST
        minimum  = float("inf")

        for index in range(a_size):
            substitute    = distance + substitution_cost(code, a[index])
            distance      = buffer[index]
            insert_delete = min(result, distance) + MOVE_COST
            result        = min(insert_delete, substitute)
            buffer[index] = result

            if result < minimum:
                minimum = result

        if max_cost is not None and minimum > max_cost:
            return max_cost + 1

    return result


def once(func: Callable, *args, t: float | None = None) -> Any:
    """Call an *args function just once, other calls will return cached ret value. `t` is cache lifetime in seconds."""

    if (cache := getattr(once, 'cache', None)) is None:
        cache = once.cache = {}
    elif len(cache) > 10000:  # lets not use up all memory
        cache = once.cache = dict(list(cache.items())[1000:])

    if t is None:
        if (ret_exp := cache.get(key := (args, func), key)) is key:
            cache[key] = ((ret := func(*args)), float('inf'))

        else:
            del cache[key]  # for LRU behavior

            cache[key] = ret_exp

            ret = ret_exp[0]

    elif (ret_exp := cache.get(key := (args, func), key)) is key:
        cache[key] = ((ret := func(*args)), time() + t)

    else:
        del cache[key]

        ret, exp = ret_exp

        cache[key] = ((ret := func(*args)), now + t) if (now := time()) >= exp else ret_exp

    return ret


def get_real_module_name(mod: str) -> str:
    """Try to convert a possible '__main__' to a real module name."""

    try:
        return mod if mod != '__main__' or not (spec := importlib.util.find_spec('__main__')) else spec.name
    except Exception:  # because of File "/usr/lib/python3.10/importlib/util.py", line 114, in find_spec, raise ValueError('{}.__spec__ is None'.format(name)), ValueError: __main__.__spec__ is None
        return mod


def get_packages() -> list[importlib.metadata.Distribution]:
    return list(importlib.metadata.distributions())


def get_package_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def running_in_container() -> bool:
    return os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv')


def set_env_vars(vars: dict[str, str | None] | None) -> dict[str, str | None] | None:
    """Set or delete environment variables returning the previous values of those variables or None if did not exist.
    Call again with returned dict to set env vars back to what they were before the first call."""

    if vars is None:
        return None

    old_vars = {var: os.getenv(var) for var in vars}

    for var, val in vars.items():
        if val is not None:
            os.environ[var] = val
        elif var in os.environ:
            del os.environ[var]

    return old_vars


def setLogLevelGlobal(level):
    """Set log level for ALL loggers."""

    for logger_name in logging.root.manager.loggerDict:
        logging.getLogger(logger_name).setLevel(level)


class adict(dict):
    """Fast Javascript-like attribute dict with access by attribute and None return on no item."""

    copy, fromkeys = lambda s: adict(s), staticmethod(lambda i, v=None: adict(dict.fromkeys(i, v)))
    __setattr__, __delattr__, __getnewargs__ = dict.__setitem__, dict.__delitem__, lambda s: (dict(s),)
    def __getattribute__(self, name):
        try: return self[name]
        except KeyError:
            try: return dict.__getattribute__(self, name)
            except AttributeError:
                if name.startswith('__'): raise  # because some system things depend on an AttributeError
                else: return None  # default value for missing items
    def set(self, name, value=None):
        """Set name=value except if value==None in which case delete the key from the dictionary entirely."""
        if value is not None: self[name] = value
        elif name in self: del self[name]
        return self


class FnmLock:
    def __init__(self, fnm: str, timeout: float | None = None, orphan_timeout: float = 10, retry_time: float = 0.05) -> Callable[[], None]:
        """Lock on a 'FILENAME' by creating 'FILENAME.lock'. Returns a callable which should be called to unlock.
        `timeout` in seconds specifies how long without an mtime change a lock file can go before raising a
        TimeoutError. When created, spawns a daemon Thread which updates the mtime of the 'FILENAME.lock' file
        periodically to indicate that the lock is still in use by a running process.

        Args:
            timeout: How long to wait in seconds before raising a TimeoutError, None means block forever until acquire
                or until `orphan_timeout` passes without an mtime update to the lock file.

            orphan_timeout: How long ago mtime in seconds to consider a lock file orphaned and raising a RuntimeError.

            retry_time: How long to wait between attempts to create the lock file.
        """

        self.lock_fnm = lock_fnm = fnm + '.lock'
        self.locked   = False
        t_timeout     = float('inf') if timeout is None else time() + timeout
        weird_count   = 0

        while True:
            try:
                fd = os.open(lock_fnm, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except FileExistsError:
                pass

            else:
                try:
                    os.close(fd)
                except Exception:
                    pass

                self.locked      = True
                self.release_evt = Event()
                self.thread      = Thread(target=self.thread_func, args=(lock_fnm, self.release_evt,), daemon=True)

                self.thread.start()

                return

            if (t := time()) >= t_timeout:
                raise TimeoutError

            try:
                mtime = os.stat(lock_fnm).st_mtime

            except FileNotFoundError:
                if timeout is None and (weird_count := weird_count + 1) > 200:
                    raise RuntimeError('Something weird is happening, os.open(fnm) is consistently getting FileExistsError but os.stat(fnm) is getting FileNotFoundError.')

            else:
                if t >= mtime + orphan_timeout:
                    raise RuntimeError(f'The lock file {os.path.abspath(lock_fnm)!r} is older than the orphan timeout, possibly orphaned. Consider deleting the file manually if you are sure that another process is not holding this lock and try whatever this is again.')

            sleep(retry_time)

    @staticmethod
    def thread_func(lock_fnm: str, release_evt: Event):
        while not release_evt.wait(1):
            os.utime(lock_fnm, (t := time(), t))

    def release(self):
        if self.locked:
            self.release_evt.set()
            self.thread.join()

            self.locked = False

            os.unlink(self.lock_fnm)


class Deque:
    """Thread-safe blocking deque. Add methods as needed."""

    def __init__(self, maxlen=None):
        self.deque = deque(maxlen=maxlen)
        self.cond  = Condition()

    def __bool__(self):
        return bool(self.deque)

    def append(self, item):
        with self.cond:
            self.deque.append(item)
            self.cond.notify()

    def popleft(self):
        with self.cond:
            while not self.deque:
                self.cond.wait()

            return self.deque.popleft()


class DaemonicTimer(Thread):
    """It's very annoying that threading.Timer doesn't have a settable daemon flag."""

    def __init__(self, interval, function, daemon=True):
        Thread.__init__(self, daemon=daemon)

        self.interval = interval
        self.function = function
        self.finished = Event()

    def run(self):
        self.finished.wait(self.interval)
        self.function()


class SignalStopper:
    """Graceful stop on SIGINT or SIGTERM with optional hard kill if that doesn't exit."""

    def __init__(self, logger=None, stop_evt=None, wait_for_allow_hard_kill=1, graceful_exit_timeout=10):
        import psutil

        self.psutil    = psutil
        self.logger    = logger
        self.stop_evt  = Event() if stop_evt is None else stop_evt
        self.wait      = wait_for_allow_hard_kill
        self.timeout   = graceful_exit_timeout
        self.kill_time = 0
        self.killer    = None

        signal.signal(signal.SIGINT, self.handler)
        signal.signal(signal.SIGTERM, self.handler)

    def handler(self, signum, frame):
        if not self.stop(reason := signal.Signals(signum).name):
            if (td := self.kill_time - time()) <= 0:
                self.kill(reason)

            else:
                self.killer = DaemonicTimer(td, lambda: self.kill(reason))
                self.killer.start()

    def stop(self, reason=None):
        if self.stop_evt.is_set():
            return False

        self.kill_time = time() + self.wait

        self.stop_evt.set()
        DaemonicTimer(self.timeout, lambda: self.kill('TIMEOUT')).start()

        if self.logger:
            self.logger.info(f'{reason + ", " if reason else ""}shutting down gracefully...')

        return True

    def kill(self, reason=None):
        if self.logger:
            self.logger.critical(f'{reason + ", " if reason else ""}terminating all subprocesses, as well as this one!')

        selfpid = os.getpid()
        pids    = [p.pid for p in self.psutil.Process(selfpid).children(recursive=True)] + [selfpid]

        if self.logger:
            self.logger.debug(f'pids to kill: {", ".join(str(p) for p in pids)}')

        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except:  # in case process disappears before we murderize it, yes, without explicit Exception
                pass

        # we do not exist here any longer...


# inside of openfilter/filter_runtime/utils.py
def strtobool(val: str) -> bool:
    """Convert a string representation of truth to True/False.

    Accepts 'y', 'yes', 't', 'true', 'on', '1' as true values and
    'n', 'no', 'f', 'false', 'off', '0' as false values.
    Raises ValueError on anything else (matches distutils.behaviour).
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return True
    if val in ('n', 'no', 'f', 'false', 'off', '0'):
        return False
    raise ValueError(f"invalid truth value {val!r}")
