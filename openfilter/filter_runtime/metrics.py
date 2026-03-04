"""Metrics.

Environment variables:
    GPU_METRICS: Set to 'false'ish to turn off GPU metrics.

    GPU_METRICS_INTERVAL: Default number of seconds between poll of GPU metrics (using nvidia-smi tool).

    CPU_METRICS_INTERVAL: Default number of seconds between poll of CPU and memory metrics.
"""

import logging
import os
import shutil
import subprocess
from pprint import pformat
from threading import Event, Thread
from time import time

from psutil import Process, cpu_count, virtual_memory

from .frame import Frame
from .utils import JSONType, json_getval, sizestr, secstr, timestr

__all__ = ['Metrics']

logger = logging.getLogger(__name__)

GPU_METRICS          = bool(json_getval((os.getenv('GPU_METRICS') or 'true').lower()))
GPU_METRICS_INTERVAL = max(0, float(json_getval(os.getenv('GPU_METRICS_INTERVAL') or 1)))
CPU_METRICS_INTERVAL = max(0, float(json_getval(os.getenv('CPU_METRICS_INTERVAL') or 1)))

GPU_METRIC_NAMES     = [(f'gpu{i}', f'gpu{i}_mem') for i in range(8)]


class Metrics:
    def __init__(self):
        self.fps                = 15
        self.fps_t              = self.uptime_t = time()
        self.fps_td             = 1 / 15
        self.cpu                = 0
        self.mem                = 0
        self.lat_in             = 0
        self.lat_out            = 0
        self.gpu                = {}
        self.frame_count        = 0
        self.megapx_count       = 0
        self.disk_usage_percent = 0.0
        self.ram_usage_percent  = 0.0
        self.gpu_accessible     = 0
        self.gpu_usage_percent  = 0.0
        self.proc               = Process()
        self.stop_evt           = Event()

        self.cpu_thread = Thread(target=self.cpu_thread_func, args=(self.stop_evt,), daemon=True)

        self.cpu_thread.start()

        if GPU_METRICS:
            self.gpu_thread = Thread(target=self.gpu_thread_func, args=(self.stop_evt,), daemon=True)

            self.gpu_thread.start()

    def destroy(self):
        self.stop_evt.set()

        if GPU_METRICS:
            self.gpu_thread.join()

        self.cpu_thread.join()

    def cpu_thread_func(self, stop_evt: Event):  # we do this in a separate thread because it can take a non-insignificant amount of time
        last_t   = time()
        proc     = self.proc
        cores    = cpu_count(logical=True) or 1
        old_kids = {}  # {pid: Process, ...} for cpu_percent() tracking of state

        try:
            while not stop_evt.wait(max(0, CPU_METRICS_INTERVAL - (time() - last_t))):
                last_t   = time()  # time() again because Event.wait() can be inaccurate
                cpu      = proc.cpu_percent()
                mem      = proc.memory_info().rss
                new_kids = {}
                kids     = proc.children(recursive=True)

                for child in kids:
                    try:
                        new_kids[pid]  = child = old_kids.get(pid := child.pid, child)
                        cpu           += child.cpu_percent()
                        mem           += child.memory_info().rss

                    except Exception as exc:
                        pass

                old_kids = new_kids
                self.cpu = min(100, cpu / cores)
                self.mem = mem / 0x40000000  # GB

                try:
                    usage = shutil.disk_usage('/')
                    self.disk_usage_percent = (usage.used / usage.total) * 100
                except Exception:
                    pass

                try:
                    vm = virtual_memory()
                    self.ram_usage_percent = vm.percent
                except Exception:
                    pass

        except Exception as exc:
            logger.error(exc)

    def gpu_thread_func(self, stop_evt: Event):
        last_t = time()

        try:
            while not stop_evt.wait(max(0, GPU_METRICS_INTERVAL - (time() - last_t))):  # GPU metrics max once per GPU_METRICS_INTERVAL
                last_t = time()  # time() again because Event.wait() can be inaccurate
                gpu    = {}

                try:
                    result = subprocess.run(['nvidia-smi', '--query-gpu=index,utilization.gpu,memory.used',  # TODO: better way to do 'gpu'?
                        '--format=csv,nounits,noheader'], stdout=subprocess.PIPE, text=True)

                except Exception:
                    logger.debug('failed to run nvidia-smi for GPU metrics')
                    self.gpu_accessible = 0

                    break

                if result.returncode or not (data := result.stdout.strip()):
                    self.gpu_accessible = 0
                    break

                for line in data.split('\n'):
                    if len(vals := [int(s.strip()) for s in line.split(',')]) != 3:
                        raise ValueError(f'expected three comma-separated numbers, not {line!r}')

                    gpu_idx, gpu_util, gpu_mem = vals

                    if not 0 <= gpu_idx <= 7:
                        raise ValueError(f'unexpected GPU index {vals[0]!r}')

                    gpu[gpu_name := f'gpu{gpu_idx}'] = gpu_util
                    gpu[f'{gpu_name}_mem']           = gpu_mem / 1000

                self.gpu = gpu
                self.gpu_accessible = 1
                self.gpu_usage_percent = gpu.get('gpu0', 0.0)

        except Exception as exc:
            logger.error(exc)
            self.gpu_accessible = 0

        self.gpu = {}

    def incoming(self, frames: dict[str, Frame] | None = None):
        if not frames:  # don't count anything if totally empty or missing (Nnne) frames
            return

        megapx_count = self.megapx_count
        tss          = []

        for frame in frames.values():
            if isinstance(m := frame.data.get('meta'), dict) and isinstance(ts := m.get('ts'), float):
                tss.append(ts)

            if frame.has_image:
                megapx_count += (frame.width * frame.height) / 1_000_000

        if tss:
            self.lat_in = 0.95 * self.lat_in + 0.05 * (time() - min(tss))

        self.frame_count  += 1  # because even if there are no images in frames the data may refer to images, or in another way count as a "frame"
        self.megapx_count  = megapx_count

    def outgoing(self, frames: dict[str, Frame] | None = None) -> dict[str, JSONType]:
        td          = (t := time()) - self.fps_t
        self.fps_t  = t
        self.fps_td = fps_td = 0.95 * self.fps_td + 0.05 * td
        self.fps    = fps = 1 / fps_td

        if frames is None or not (tss := [ts for f in frames.values()
                if isinstance(m := f.data.get('meta'), dict) and isinstance(ts := m.get('ts'), float)]):
            lat_out = self.lat_out
        else:
            self.lat_out = lat_out = 0.95 * self.lat_out + 0.05 * (t - min(tss))

        metrics = {
            'ts':  t,
            'fps': fps,       # (F)rames (P)er (S)idereal year
            'cpu': self.cpu,  # percent of whole CPU this process and all its children recursively
            'mem': self.mem,  # GB sum this process and all its children recursively
        }  # add more?

        if lat_in := self.lat_in:
            metrics['lat_in'] = lat_in * 1000  # milliseconds

        if lat_out:
            metrics['lat_out'] = lat_out * 1000  # milliseconds

        if gpu := self.gpu:
            metrics.update(gpu)

        metrics['uptime_count']      = int(t - self.uptime_t)
        metrics['disk_usage_percent'] = self.disk_usage_percent
        metrics['ram_usage_percent']  = self.ram_usage_percent
        metrics['gpu_accessible']     = self.gpu_accessible
        metrics['gpu_usage_percent']  = self.gpu_usage_percent

        if frame_count := self.frame_count:
            metrics['frame_count'] = frame_count

        if megapx_count := self.megapx_count:
            metrics['megapx_count'] = megapx_count

        return metrics

    @staticmethod
    def log_text(log: str, frames: dict[str, Frame], metrics: dict[str, JSONType] | None = None) -> str | None:
        if not log:
            return None

        if metrics is None:
            prefix = ''

        else:
            parts = []

            if (fps := metrics.get('fps')) is not None:
                parts.append(f"""fps: {
                    f'{fps:0.2f}' if (fps := metrics['fps']) < 10 else f'{fps:0.1f}' if fps < 100 else str(round(fps))
                }""")

            if (cpu := metrics.get('cpu')) is not None:
                parts.append(f"""cpu: {
                    f'{cpu:0.2f}' if (cpu := metrics["cpu"]) < 10 else f'{cpu:0.1f}' if cpu < 100 else str(round(cpu))
                }% / {sizestr(int(metrics["mem"] * 1_000_000_000))}""")

            if (lat_in := metrics.get('lat_in')) is not None:
                parts.append(f"in: {secstr(int(lat_in * 1_000_000))}")

            if (lat_out := metrics.get('lat_out')) is not None:
                parts.append(f"out: {secstr(int(lat_out * 1_000_000))}")

            for gpu_n, ngpu_mem_n in GPU_METRIC_NAMES:
                if (gpu := metrics.get(gpu_n)) is not None:
                    parts.append(f"{gpu_n}: {f'{gpu}% / {sizestr(int(metrics[ngpu_mem_n] * 1_000_000_000))}'}")

            if (up := metrics.get('uptime_count')) is not None:
                parts.append(f"up: {timestr(up)}s" if (up) < 60 else f"up: {timestr(up)}")

            prefix = ', '.join(parts)

        if log == 'metrics':
            text = prefix

        elif log == 'pretty':
            text = prefix + (f'{" - " if prefix else ""}NO FRAMES' if frames is None else
                ('\n' if '\n' in (text := pformat({t: (f, f.data) for t, f in frames.items()})) else '') + text)

        else:
            if prefix:
                prefix += ' - '

            if log == 'image':
                text = prefix + ('NO FRAMES' if frames is None else
                    f"{{{', '.join(f'{t!r}: {f}' for t, f in frames.items())}}}")

            elif log == 'data':
                text = prefix + ('NO FRAMES' if frames is None else
                    f"{{{', '.join(f'{t!r}: {f.data}' for t, f in frames.items())}}}")

            elif log == 'all':
                text = prefix + ('NO FRAMES' if frames is None else
                    f"{{{', '.join(f'{t!r}: {f.fullstr}' for t, f in frames.items())}}}")

            else:
                raise ValueError(f'invalid log {log!r}')

        return text
