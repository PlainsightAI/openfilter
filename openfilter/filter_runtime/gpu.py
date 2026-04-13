"""Framework-agnostic GPU detection and metrics via ctypes.

Uses the CUDA Driver API (libcuda.so.1) for GPU detection and NVML
(libnvidia-ml.so.1) for runtime metrics. No torch dependency.

Library Loading
---------------
On Kubernetes (GKE), the NVIDIA device plugin mounts driver libraries at
/usr/local/nvidia/lib64/ but does NOT add this path to LD_LIBRARY_PATH.
The dynamic linker caches LD_LIBRARY_PATH at process startup, so setting
os.environ['LD_LIBRARY_PATH'] from Python has no effect on dlopen().
We use absolute paths to bypass this (dlopen with absolute path skips
the search entirely).
"""

import ctypes
import ctypes.util
import logging
import os
from dataclasses import dataclass

__all__ = [
    "preload_gpu_libs",
    "detect_gpu",
    "GPUInfo",
    "GPUMetrics",
    "get_gpu_metrics",
    "nvml_shutdown",
]

logger = logging.getLogger(__name__)

# Libraries to preload with RTLD_GLOBAL so downstream frameworks (torch, etc.)
# can find them already loaded in the process.
_GPU_LIB_NAMES = ["libcuda.so.1", "libnvidia-ml.so.1"]
_preloaded_gpu_libs: set = set()

# Cached library handles
_libcuda = None
_libnvml = None
_nvml_initialized = False


@dataclass
class GPUInfo:
    """Result of ctypes-based GPU detection."""

    available: bool
    device_count: int = 0
    device_name: str = "unknown"
    driver_version: str = "unknown"


@dataclass
class GPUMetrics:
    """GPU utilization snapshot from NVML."""

    index: int
    gpu_util: int  # percent 0-100
    mem_used_mb: int  # MiB


def _find_gpu_lib(name: str) -> str | None:
    """Find a GPU library by searching OPENFILTER_APPEND_LD_LIBRARY_PATH, then system paths."""
    ld_path = os.environ.get("OPENFILTER_APPEND_LD_LIBRARY_PATH", "")
    for search_dir in ld_path.split(":"):
        if not search_dir:
            continue
        lib_path = os.path.join(search_dir, name)
        if os.path.exists(lib_path):
            return lib_path

    # Fall back to system library search
    found = ctypes.util.find_library(name.split(".so")[0].lstrip("lib"))
    if found:
        return found

    # Last resort: try the bare name and let dlopen search
    return name


def _load_libcuda():
    """Load and return libcuda handle, or None."""
    global _libcuda
    if _libcuda is not None:
        return _libcuda

    path = _find_gpu_lib("libcuda.so.1")
    if path is None:
        return None
    try:
        _libcuda = ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
        return _libcuda
    except OSError as exc:
        logger.debug("Failed to load libcuda: %s", exc)
        return None


def _load_libnvml():
    """Load and return libnvidia-ml handle, or None."""
    global _libnvml
    if _libnvml is not None:
        return _libnvml

    path = _find_gpu_lib("libnvidia-ml.so.1")
    if path is None:
        return None
    try:
        _libnvml = ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
        return _libnvml
    except OSError as exc:
        logger.debug("Failed to load libnvidia-ml: %s", exc)
        return None


def preload_gpu_libs():
    """Preload NVIDIA GPU driver libraries using ctypes with absolute paths.

    Must be called before any CUDA consumer is imported (PyTorch, TensorRT,
    ONNX Runtime, CuPy, etc.) so that the already-loaded libraries are visible
    to downstream dlopen() calls.
    """
    ld_path = os.environ.get("OPENFILTER_APPEND_LD_LIBRARY_PATH")
    if not ld_path:
        return

    for search_dir in ld_path.split(":"):
        for lib_name in _GPU_LIB_NAMES:
            lib_path = os.path.join(search_dir, lib_name)
            if lib_path in _preloaded_gpu_libs:
                continue
            if os.path.exists(lib_path):
                try:
                    ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)
                    _preloaded_gpu_libs.add(lib_path)
                except OSError as exc:
                    logger.debug("Failed to preload GPU library %s: %s", lib_path, exc)


def detect_gpu() -> GPUInfo:
    """Detect GPU availability using the CUDA Driver API (no torch required).

    Uses cuInit, cuDeviceGetCount, cuDeviceGetName, cuDriverGetVersion
    from libcuda.so.1 via ctypes.
    """
    lib = _load_libcuda()
    if lib is None:
        return GPUInfo(available=False)

    try:
        # cuInit(0)
        ret = lib.cuInit(ctypes.c_uint(0))
        if ret != 0:
            logger.debug("cuInit failed with error code %d", ret)
            return GPUInfo(available=False)

        # cuDeviceGetCount
        count = ctypes.c_int(0)
        ret = lib.cuDeviceGetCount(ctypes.byref(count))
        if ret != 0:
            logger.debug("cuDeviceGetCount failed with error code %d", ret)
            return GPUInfo(available=False)

        device_count = count.value
        if device_count == 0:
            return GPUInfo(available=False, device_count=0)

        # cuDeviceGetName for device 0
        name_buf = ctypes.create_string_buffer(256)
        ret = lib.cuDeviceGetName(name_buf, 256, ctypes.c_int(0))
        device_name = (
            name_buf.value.decode("utf-8", errors="replace") if ret == 0 else "unknown"
        )

        # cuDriverGetVersion
        version = ctypes.c_int(0)
        ret = lib.cuDriverGetVersion(ctypes.byref(version))
        if ret == 0:
            v = version.value
            driver_version = f"{v // 1000}.{(v % 1000) // 10}"
        else:
            driver_version = "unknown"

        return GPUInfo(
            available=True,
            device_count=device_count,
            device_name=device_name,
            driver_version=driver_version,
        )

    except Exception as exc:
        logger.debug("GPU detection via CUDA Driver API failed: %s", exc)
        return GPUInfo(available=False)


def nvml_shutdown():
    """Shut down NVML if it was initialized. Safe to call even if not initialized."""
    global _nvml_initialized
    if not _nvml_initialized:
        return
    lib = _load_libnvml()
    if lib is not None:
        try:
            lib.nvmlShutdown()
        except Exception:
            pass
    _nvml_initialized = False


def get_gpu_metrics() -> list[GPUMetrics] | None:
    """Get GPU utilization metrics via NVML (no nvidia-smi subprocess).

    Returns a list of GPUMetrics for each GPU, or None on failure.
    NVML is initialized once on first call and reused across subsequent calls.
    Call nvml_shutdown() when done (e.g. at process exit).
    """
    global _nvml_initialized
    lib = _load_libnvml()
    if lib is None:
        return None

    try:
        # nvmlInit_v2 — idempotent, but skip redundant calls
        if not _nvml_initialized:
            ret = lib.nvmlInit_v2()
            if ret != 0:
                logger.debug("nvmlInit_v2 failed with error code %d", ret)
                return None
            _nvml_initialized = True

        # nvmlDeviceGetCount_v2
        count = ctypes.c_uint(0)
        ret = lib.nvmlDeviceGetCount_v2(ctypes.byref(count))
        if ret != 0:
            logger.debug("nvmlDeviceGetCount_v2 failed with error code %d", ret)
            return None

        results = []

        class NvmlUtilization(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        class NvmlMemory(ctypes.Structure):
            _fields_ = [
                ("total", ctypes.c_ulonglong),
                ("free", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong),
            ]

        for i in range(count.value):
            handle = ctypes.c_void_p()
            ret = lib.nvmlDeviceGetHandleByIndex_v2(
                ctypes.c_uint(i), ctypes.byref(handle)
            )
            if ret != 0:
                continue

            util = NvmlUtilization()
            ret = lib.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(util))
            gpu_util = util.gpu if ret == 0 else 0

            mem = NvmlMemory()
            ret = lib.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem))
            mem_used_mb = mem.used // (1024 * 1024) if ret == 0 else 0

            results.append(
                GPUMetrics(index=i, gpu_util=gpu_util, mem_used_mb=mem_used_mb)
            )

        return results if results else None

    except Exception as exc:
        logger.debug("NVML metrics collection failed: %s", exc)
        return None
