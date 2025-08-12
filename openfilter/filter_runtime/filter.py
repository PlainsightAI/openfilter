import json
import logging
import multiprocessing as mp
import os
import re
import sys
import threading
import time
from datetime import datetime
from multiprocessing import synchronize
from typing import Any, Callable, Literal, List

import numpy as np

from .dlcache import is_cached_file, dlcache
from .frame import Frame
from .mq import POLL_TIMEOUT_MS, is_mq_addr, MQ
from .logging import Logger
from .utils import JSONType, json_getval, simpledeepcopy, dict_without, split_commas_maybe, rndstr, \
    timestr, parse_time_interval, parse_date_and_or_time, hide_uri_users_and_pwds, \
    get_real_module_name, get_packages, get_package_version, set_env_vars, running_in_container, \
    adict, DaemonicTimer, SignalStopper
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib # python <3.11 uses tomli instead of tomllib

from uuid import uuid4
from openfilter.observability import OpenFilterLineage, TelemetryRegistry, MetricSpec
from openfilter.observability.client import OpenTelemetryClient
from openfilter.filter_runtime.utils import strtobool
__all__ = ['is_cached_file', 'is_mq_addr', 'FilterConfig', 'Filter']

logger = logging.getLogger(__name__)

LOG_LEVEL  = (os.getenv('LOG_LEVEL') or 'INFO').upper()
LOG_FORMAT = os.getenv('LOG_FORMAT') or None
LOG_PID    = bool(json_getval((os.getenv('LOG_PID') or ('false' if running_in_container() else 'true')).lower()))
LOG_THID   = bool(json_getval((os.getenv('LOG_THID') or 'false').lower()))
LOG_UTC    = bool(json_getval((os.getenv('LOG_UTC') or 'false').lower()))

if LOG_UTC:
    from time import gmtime

    logging.Formatter.converter = gmtime

if LOG_FORMAT is None:  # '%(asctime)s.%(msecs)03d %(process)7d.%(threadName)s %(levelname)-8s %(filename)s:%(lineno)d - %(funcName)s - %(message)s'  - everything
    if LOG_PID:
        if LOG_THID:
            LOG_FORMAT = '%(asctime)s.%(msecs)03d %(process)7d.%(thread)012x %(levelname)-8s %(message)s'
        else:
            LOG_FORMAT = '%(asctime)s.%(msecs)03d %(process)7d %(levelname)-8s %(message)s'

    else:
        if LOG_THID:
            LOG_FORMAT = '%(asctime)s.%(msecs)03d %(thread)012x %(levelname)-8s %(message)s'
        else:
            LOG_FORMAT = '%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s'

logging.basicConfig(
    level   = int(getattr(logging, LOG_LEVEL)),
    format  = LOG_FORMAT,
    datefmt = '%Y-%m-%d %H:%M:%S',
)

LOOP_EXC         = bool(json_getval((os.getenv('LOOP_EXC') or 'true').lower()))
PROP_EXIT        = (os.getenv('PROP_EXIT') or 'clean').lower()
OBEY_EXIT        = (os.getenv('OBEY_EXIT') or 'all').lower()
STOP_EXIT        = (os.getenv('STOP_EXIT') or 'error').lower()
AUTO_DOWNLOAD    = bool(json_getval((os.getenv('AUTO_DOWNLOAD') or 'true').lower()))
ENVIRONMENT      = os.getenv('ENVIRONMENT')

# Telemetry environment variables
TELEMETRY_EXPORTER_ENABLED = os.getenv('TELEMETRY_EXPORTER_ENABLED')

# Try to read OpenLineage config from YAML file first, then environment
try:
    from openfilter.observability.config import read_openlineage_config
    _ol_config = read_openlineage_config()
    if _ol_config:
        OPENLINEAGE_URL = _ol_config.get("url") or os.getenv('OPENLINEAGE_URL')
        OPENLINEAGE_API_KEY = _ol_config.get("api_key") or os.getenv('OPENLINEAGE_API_KEY')
        OPENLINEAGE_HEARTBEAT_INTERVAL = str(_ol_config.get("heartbeat_interval", 10))
    else:
        OPENLINEAGE_URL = os.getenv('OPENLINEAGE_URL')
        OPENLINEAGE_API_KEY = os.getenv('OPENLINEAGE_API_KEY')
        OPENLINEAGE_HEARTBEAT_INTERVAL = os.getenv('OPENLINEAGE__HEART__BEAT__INTERVAL', '10')
except ImportError:
    OPENLINEAGE_URL = os.getenv('OPENLINEAGE_URL')
    OPENLINEAGE_API_KEY = os.getenv('OPENLINEAGE_API_KEY')
    OPENLINEAGE_HEARTBEAT_INTERVAL = os.getenv('OPENLINEAGE__HEART__BEAT__INTERVAL', '10')

OPENLINEAGE_EXPORT_RAW_DATA = os.getenv('OPENLINEAGE_EXPORT_RAW_DATA', 'false').lower() in ('true', '1', 'yes')

PROP_EXIT_FLAGS  = {'all': 3, 'clean': 1, 'error': 2, 'none': 0}
POLL_TIMEOUT_SEC = POLL_TIMEOUT_MS / 1000

if PROP_EXIT not in PROP_EXIT_FLAGS:
    raise ValueError(f'invalid PROP_EXIT {PROP_EXIT!r}, can only be one of: {", ".join(PROP_EXIT_FLAGS)}')
if OBEY_EXIT not in PROP_EXIT_FLAGS:
    raise ValueError(f'invalid OBEY_EXIT {OBEY_EXIT!r}, can only be one of: {", ".join(PROP_EXIT_FLAGS)}')
if STOP_EXIT not in PROP_EXIT_FLAGS:
    raise ValueError(f'invalid STOP_EXIT {STOP_EXIT!r}, can only be one of: {", ".join(PROP_EXIT_FLAGS)}')


class FilterConfig(adict):  # types are informative to you as in the end they're all just adicts, maybe in future do something with them (defaults, coercion and/or validation)
    id:                  str

    sources:             str | list[str] | None
    sources_balance:     bool | None
    sources_timeout:     int | None
    sources_low_latency: bool | None

    outputs:             str | list[str] | None
    outputs_balance:     bool | None
    outputs_timeout:     int | None
    outputs_required:    str | None
    outputs_metrics:     str | bool | None
    outputs_jpg:         bool | None

    exit_after:          float | str | None  # '[[[days:]hrs:]mins:]secs[.subsecs]' or '@date/time/datetime'

    environment:         str | None
    log_path:            str | Literal[False] | None
    metrics_interval:    float | None
    extra_metrics:       dict[str, JSONType] | list[tuple[str, JSONType]] | None
    mq_log:              str | bool | None
    mq_msgid_sync:       bool | None

    def clean(self):  # -> Self:
        """Return a clean instance of this config without any hidden items starting with '_'."""

        return self.__class__({k: v for k, v in self.items() if not k.startswith('_')})

class FilterContext:
    """
    FilterContext: Static context for Docker image and model metadata.

    The FilterContext class provides static access to build and model metadata for the filter runtime. It is initialized once per process and stores the following information:

    - filter_version: The version of the filter runtime, read from the file 'VERSION'.
    - resource_bundle_version: The version of the resource bundle, read from the file 'RESOURCE_BUNDLE_VERSION'.
    - version_sha: The Git commit SHA, read from the file 'VERSION_SHA'. This should be set at build time by CI/CD or manually.
    - models: A dictionary of models loaded from 'models.toml'. Each entry contains:
        - model name (key)
        - version: The version string for the model
        - path: The path to the model file (if present), or 'No path' if not specified

    This context is intended to provide runtime and build information for logging, debugging, and traceability. It is accessed via classmethods such as FilterContext.get(key), FilterContext.as_dict(), FilterContext.log(), and specific getter methods.

    Example usage:
        FilterContext.init()  # Initializes context if not already done
        version = FilterContext.get('filter_version')
        FilterContext.log()   # Logs all context info
        filter_version = FilterContext.get_filter_version()
        openfilter_version = FilterContext.get_openfilter_version()
    """

    _data = {}

    @classmethod
    def init(cls):
        if cls._data:
            return  # already initialized

        cls._data = {
            "filter_version": cls._read_file("VERSION"),
            "resource_bundle_version": cls._read_file("RESOURCE_BUNDLE_VERSION"),
            "version_sha": cls._read_file("VERSION_SHA"),
            "models": cls._read_models_toml(),
            "openfilter_version": cls.get_openfilter_version()
        }

    @classmethod
    def get(cls, key):
        return cls._data.get(key)

    @classmethod
    def as_dict(cls):
        return dict(cls._data)

    @classmethod
    def log(cls):
        """Log all available static context information."""
        for key, value in cls._data.items():
            if key == "models":
                logger.info("Models config:")
                for name, model in value.items():
                    logger.info(f"  Model: {name} ({model['version']}) - {model.get('path', 'No path')}")
                logger.info(f"  Total models: {len(value)}")
            else:
                logger.info(f"{key.replace('_', ' ').title()}: {value}")

    @classmethod
    def get_filter_version(cls) -> str | None:
        """Get the filter version."""
        return cls._data.get('filter_version')

    @classmethod
    def get_resource_bundle_version(cls) -> str | None:
        """Get the resource bundle version from RESOURCE_BUNDLE_VERSION file."""
        return cls._data.get('resource_bundle_version')

    @classmethod
    def get_version_sha(cls) -> str | None:
        """Get the version SHA."""
        return cls._data.get('version_sha')

    @classmethod
    def get_model_info(cls) -> dict | None:
        """Get the models data."""
        return cls._data.get('models')

    @classmethod
    def get_openfilter_version(cls) -> str | None:
        """Get the OpenFilter framework version."""
        try:
            import importlib.metadata
            version = importlib.metadata.version('openfilter')
            return f"v{version}"
        except Exception:
            return None

    @staticmethod
    def _read_file(filename):
        try:
            path = Path(filename)
            if path.exists():
                return path.read_text().strip()
            logger.warning(f"{filename} not found")
        except Exception as e:
            logger.warning(f"Error reading {filename}: {e}")
        return None

    @staticmethod
    def _read_models_toml():
        path = Path("models.toml")
        if not path.exists():
            logger.warning("models.toml not found")
            return {}

        try:
            with path.open("rb") as f:
                raw = tomllib.load(f)

            models = {}
            for name, data in raw.items():
                if isinstance(data, dict) and 'version' in data:
                    models[name] = {
                        "version": data["version"],
                        "path": data.get("path", "No path")
                    }
                else:
                    logger.warning(f"Model {name} missing version field")

            return models

        except Exception as e:
            logger.error(f"Error reading models.toml: {e}")
            return {}
        
class Filter:
    """Filter base class. All filters derive from this and can override any of these config options but in practice
    mostly override `sources` and `outputs` to specify other sources or outputs than the filter pipeline.
    
    config:
        id:
            Unique string identifier for this filter. If this is not provided then it will be randomly generated.

        sources:
            Sources for this filter, they can be either other filters ('tcp://', 'ipc://') or filter specific URIs like
            'file://', 'rtsp://', 'http://', etc... When thet are other filters they are handled here and take the
            following form (there can be multiple delimited by commas, whitespace is ignored):

                "tcp://127.0.0.1" - All topics are received (not including "_metrics" if present).
                "tcp://127.0.0.1;" - Only the 'main' topic is received.
                "tcp://127.0.0.1;>" - Same.
                "tcp://127.0.0.1;>other" - The 'main' topic is received as 'other'.
                "tcp://127.0.0.1;that>" - The 'that' topic is received as 'main'.
                "tcp://127.0.0.1;that>other" - The 'that' topic is received as 'other'.
                "tcp://127.0.0.1;*" - ALL topics are received, including '_metrics'.

        sources_balance:
            Source(s) are load balanced (previously split across multiple identical pipelines) so join them again here
            into one stream. This filter will act as if the multiple upstream `sources` are one single filter running
            faster than it could if it were only one element. Must be paired with `outputs_balance` upstreamn.

        sources_timeout:
            If specified then this is the maximum number of milliseconds to wait for any input from `sources`, on
            timeout otherwise call process() regardless with an empty `frames` object. EXPERIMENTAL!

        sources_low_latency:
            Set low latency mode for sources, also lowers throughput a bit. Normally a filter will preemptively request
            the next frame as soon as it has received the current one. This allows that the next frame may be ready in
            the pipeline when this filter comes back to request it, but in the case of sources which provikde data at
            the moment of the request (like video), this will increase the amount of time that has passed between frame
            generation and when you get it (higher latency). Global env var default ZMQ_LOW_LATENCY.

        outputs:
            Where other filters will connect to get their data, e.g. "tcp://127.0.0.1", "tcp://*:5552", "ipc://name".
            NOT the destination filters themselves! Repeat, this is a bind point where this filter will listen for
            connections, not where it should connect to send data. This field is also commonly overloaded by specific
            output filters like video or messaging queue outputs.

        outputs_balance:
            Balance sending frames across all outputs. Not normal operation, meant for a load balancing topology. Must
            be paired with `sources_balance` downstream.

        outputs_timeout:
            If specified then this is the maximum number of milliseconds to wait for to output `frames`, on timeout
            otherwise call process drop those `frames` and proceed as if they had been sent. EXPERIMENTAL!

        outputs_required:
            Comma separated string of filter ids required to be connected before sending anything. This is a list of the
            `id` fields from the configs of the required filters, NOT their addresses.

        outputs_jpg:
            Whether to output images as jpg True, False makes sure NOT to output them as jpg even if returned from
            process() as such, None uses env var default which is normally to pass them on as they are returned from
            process(). Global env var default ZMQ_LOW_LATENCY. Gloval env var default OUTPUTS_JPG.

        exit_after:
            Exit after this amount of time in seconds or as a formatted string '[[[days[d]:]hrs:]mins:]secs[.subsecs]'.
            If the `exit_after` string starts with '@' then this sets an actual clock date/time to exit at (in local
            time or UTC depending on LOG_UTC). Can pass either time (date will be today), date (time will be midnight)
            or both. Date order is year/month/day and the separator character is '/' or '-'. If both date and time are
            passed then they are separated by either space ' ' or 'T'. Default is no exit datetime scheduled.

        environment:
            Optional and informational only, 'Production', 'Staging', 'Dev', whatever...

        log_path:
            Set to False to disable logs and metrics, None for default location and otherwise will be path for logs and
            metrics. Gloval env var default LOG_PATH.

        metrics_interval:
            Number of seconds between averaged metrics samples written to log files. Gloval env var default
            METRICS_INTERVAL.

        mq_log:
            Log outgoing messages, can be 'all', 'image', 'data', 'none', 'pretty', 'metrics', True (same as 'all') or
            False (same as 'none'). A value None actually means use global env var default, not 'none' which means no
            log at all. Global env var default MQ_LOG.

        mq_msgid_sync:
            Default True means synchronize message IDs between sources and outputs (normal mode of operation). This
            is provided in case of advanced use with circular filter topologies. If you don't know what this means then
            don't touch this. Global env var default MQ_MSGID_SYNC. EXPERIMENTAL!

    Environment variables:
        LOG_LEVEL:
            'critical', 'error', 'warning', 'info' or 'debug'.

        LOG_FORMAT:
            Log show format override, direct parameter to basicConfig(format=?), overrides LOG_PID and LOG_THID.

        LOG_PID:
            Force show or hide process ID.

        LOG_THID:
            Force show or hide thread ID.

        LOG_UTC:
            If 'true'ish all logging will be in UTC instead of local time. This only affects showing time in the logs as
            timezone information is stored so real time is never lost regardless of mode.

        LOOP_EXC:
            If 'false'ish ignore exceptions in the main loop and keep going, otherwise exit with an error (default).

        PROP_EXIT:
            Exit propagate policy to other filters, can be 'all', 'error', 'clean', or 'none'. Default 'clean'.

        OBEY_EXIT:
            Which propagated exits to obey, can be 'all', 'error', 'clean', or 'none'. Default 'all'.

        STOP_EXIT:
            Multi-filter Runner exit policy, can be 'all', 'error', 'clean', or 'none'. Default 'error'.

        AUTO_DOWNLOAD:
            Automatically download "jfrog://..." resources in configs and replace names with cached "file://..." URIs.
            Default True.

    From logging.py:
        LOG_PATH:
            Path for logs, set to 'false' to disable. Default 'false'.

        LOGS_FILE_SIZE:
            Maximum individual logs file size in bytes. Default 5_000_000.

        LOGS_TOTAL_SIZE:
            Maximum total size of all logs files in bytes. Default 100_000_000.

        METRICS_FILE_SIZE:
            Maximum individual log file size in bytes. Default 5_000_000.

        METRICS_TOTAL_SIZE:
            Maximum total size of all metrics files in bytes. Default 100_000_000.

        METRICS_INTERVAL:
            Number of seconds between metrics samples written to metrics file (base metrics averaged in this time).

    From mq.py:
        OUTPUTS_JPG:
            If 'true'ish then encode output images to network as jpg, 'false'ish only send decoded, 'null' send as is as
            was passed from process().

        OUTPUTS_METRICS:
            If true then send metrics as '_metrics' on all zeromq outputs. If false then don't send. If string then is
            address of dedicated sender for metrics (will not be sent on normal senders).

        OUTPUTS_METRICS_PUSH:
            If 'true'ish then will always send metrics on dedicated metrics output regardless of if something is
            officially connected or not. Default true to support doubly ephemeral '??' listeners which are most likely
            the only things connected. Does not affect metrics on normal output channels.

        MQ_LOG:
            Default outputs logging if not explicitly specified. Default 'none'.

        MQ_MSGID_SYNC:
            Whether to sync expected message IDs between outgoing and incoming zeromq message queues. Advanced thing,
            don't touch unless u know what u doing.

    From metrics.py:
        GPU_METRICS:
            Set to 'false'ish to turn off GPU metrics.

        GPU_METRICS_INTERVAL:
            Default number of seconds between poll of GPU metrics (using nvidia-smi tool).

        CPU_METRICS_INTERVAL:
            Default number of seconds between poll of CPU and memory metrics.

    From dlcache.py:
        JFROG_API_KEY:
            The JFrog API key, will be deprecated by evil JFrog people at end of September 2024, use JFROG_TOKEN
            instead.

        JFROG_TOKEN:
            The JFrog access token to the World Bank master server.

        DLCACHE_PATH:
            Path to root of cache where to download 'jfrog://' items to. Default 'cache'.

    From zeromq.py (don't mess with these except DEBUG_ZEROMQ, ZMQ_CONN_TIMEOUT, ZMQ_LOW_LATENCY and ZMQ_WARN_*):
        DEBUG_ZEROMQ:
            If 'true'ish and logging is set to 'debug' then will log each message sent and received (not the full
            contents, just basic info).

        ZMQ_RECONNECT_IVL:
            Reconnect wait in milliseconds.

        ZMQ_RECONNECT_IVL_MAX:
            Reconnect exponential backoff max value in milliseconds, 0 for no backoff (default).

        ZMQ_EXPLICIT_LINGER:
            Because sometimes zmq.LINGER just doesn't do it. Milliseconds to wait after last send before allowing socket
            close to make sure important messages (exit) get out. Because really, sometimes it just drops the last
            messages even with LINGER set high.

        ZMQ_POLL_TIMEOUT:
            Length to wait in milliseconds each poll for a message to come in in milliseconds. Requests for more frames
            are sent at this interval as well.

        ZMQ_CONN_TIMEOUT:
            Length of time in milliseconds without receiving anything from a downstream connection in order to consider
            that client timed out and no longer require a request from it to allow publish of frames.

        ZMQ_CONN_HANDSHAKE:
            Since we are using two separate sockets for communication it is possible that the requestor socket connects
            before the subscriber socket and causes messages to be sent which are missed. This is not usually a problem
            during normal operation but may be during testing or in special circumstances. For this reason handshake
            exists so that a sender does not recognize a receiver until that receiver has indicated in its request
            packets that it has received at least one message from the sender. Set this to False to turn this behavior
            off if for some reason it is causing a problem or if you want the absolute fastest connections without
            regard for possibly lost initial packets. Set on upstream side, default True.

        ZMQ_PUSH_HWM:
            For emergencies.

        ZMQ_PUB_HWM:
            For emergencies.

        ZMQ_LOW_LATENCY:
            If 'true'ish then favor lower latency over higher throughput. Will only help in some cases with the right
            properties. Really on things immediately downstream of VideoIn.

        ZMQ_WARN_NEWER:
            Warn on newer messages than expected.

        ZMQ_WARN_OLDER:
            Warn on older messages than expected.
    
    Subclasses can declare metrics by setting the metric_specs class attribute:
    
        class MyFilter(Filter):
            metric_specs = [
                MetricSpec(
                    name="frames_processed",
                    instrument="counter", 
                    value_fn=lambda d: 1
                ),
                MetricSpec(
                    name="detections_per_frame",
                    instrument="histogram",
                    value_fn=lambda d: len(d.get("detections", [])),
                    boundaries=[0, 1, 2, 5, 10]
                )
            ]
    """

    config:  FilterConfig
    logger:  Logger
    mq:      MQ
    metrics: dict[str, JSONType]  # the last metrics that were sent out, including user metrics

    FILTER_TYPE = 'User'
    metric_specs: List[MetricSpec] = []  # subclasses override this to declare metrics

    @property
    def metrics(self) -> dict[str, JSONType]:
        return self.mq.metrics

    class Exit(SystemExit): pass
    class PropagateError(Exception): pass
    class YesLoopException(Exception): pass  # not to raise, just to exist as an Exception to allow other Exceptions to propagate


    def __init__(self,
        config:    FilterConfig,
        stop_evt:  threading.Event | synchronize.Event | None = None,
        obey_exit: str | None = None,
    ):
        if not (config := simpledeepcopy(config)).get('id'):
            config['id'] = f'{self.__class__.__name__}-{rndstr(6)}'  # everything must have an ID for sanity
        
        pipeline_id = config.get("pipeline_id") or os.environ.get("PIPELINE_ID")
        self.device_id_name = config.get("device_name") or os.environ.get("DEVICE_NAME")
        self.pipeline_id = pipeline_id  # to store as an attribute
        
        # Add pipeline identification to config for OpenLineage start event
        if pipeline_id:
            config["pipeline_id"] = pipeline_id
        if self.device_id_name:
            config["device_name"] = self.device_id_name
       
        FilterContext.init()

        self.start_logging(config)  # the very firstest thing we do to catch as much as possible
        self._metrics_updater_thread = None
        try:
             self.telemetry_enabled: bool = bool(strtobool(TELEMETRY_EXPORTER_ENABLED)) if TELEMETRY_EXPORTER_ENABLED is not None else False
        except ValueError:
             logger.warning(f"Invalid TELEMETRY_EXPORTER_ENABLED value: {TELEMETRY_EXPORTER_ENABLED}. Defaulting to False.")
             self.telemetry_enabled = False
        
        # Check if raw subject data export is enabled
        self._export_raw_data = OPENLINEAGE_EXPORT_RAW_DATA
        if self._export_raw_data:
            logger.info("[Filter] Raw subject data export is ENABLED")
        else:
            logger.info("[Filter] Raw subject data export is DISABLED (set OPENLINEAGE_EXPORT_RAW_DATA=true to enable)")
    

        try:
            try:
                self.config = config = self.normalize_config(config)

            finally:
                logger.info(f'{self.__class__.__name__}(config=' +
                    str((_ := lambda cfg: (
                        hide_uri_users_and_pwds(cfg)       if isinstance(cfg, str) else
                        cfg.__class__([_(v) for v in cfg]) if isinstance(cfg, (list, tuple)) else
                        cfg                                if not isinstance(cfg, FilterConfig) else
                        cfg.__class__({_(k): _(v) for k, v in cfg.items() if not k.startswith("_")})))(config)) +
                ')')

            self.stop_evt  = threading.Event() if stop_evt is None else stop_evt
            self.obey_exit = PROP_EXIT_FLAGS[OBEY_EXIT if obey_exit is None else obey_exit]

            if AUTO_DOWNLOAD:
                self.download_cached_files(config)

        except:  # yes, bare naked except
            self.stop_logging()

            raise

    def start_logging(self, config: dict[str, Any]):
        self.logger = Logger(config.get('id'), utc=LOG_UTC, log_path=config.get('log_path'),
            metrics_interval=config.get('metrics_interval'))

    def stop_logging(self):
        self.logger.close()

    def exit(self, reason: str | None = None, exc: BaseException | None = None):
        """Allow clean exit from the filter from any point in the filter code, including process(), init(), setup(),
        shutdown() and fini(). But only works correctly from within these functions which are called from the run()
        loop, otherwise will cause a sys exit or other exception specified with `exc`."""

        if not self.stop_evt.is_set():  # because we don't want to potentially log multiple exits
            self.stop_evt.set()
            if hasattr(self, 'emitter') and self.emitter is not None:
                self.emitter.stop_lineage_heart_beat()
            self.stop_metrics_updater_thread()
            if hasattr(self, 'emitter') and self.emitter is not None:
                self.emitter.emit_stop()
            logger.info(f'{reason}, exiting...' if reason else 'exiting...')

        raise exc or Filter.Exit
    
    
    def start_metrics_updater_thread(self):
        interval = self.otel.export_interval_millis / 1000  

        def loop():
            while not self.stop_evt.is_set():
                try:
                    # Send system metrics to OpenTelemetry (raw, not aggregated)
                    self.otel.update_metrics(self.metrics, filter_name=self.filter_name)
                    
                    # System metrics are automatically aggregated by OTel SDK and sent to OpenLineage
                    # via the OTelLineageExporter bridge - no need to send them directly
                            
                except Exception as e:
                    logger.error(f"[metrics_updater] Error updating metrics: {e}")
                self.stop_evt.wait(interval)  

        # Store the thread handle
        self._metrics_updater_thread = threading.Thread(target=loop, daemon=True)
        self._metrics_updater_thread.start()

    def stop_metrics_updater_thread(self):
        if not getattr(self, "telemetry_enabled", False):
            # Telemetry not enabled, nothing to stop
            return
        if self._metrics_updater_thread is not None:
            self.stop_evt.set()
            self._metrics_updater_thread.join(timeout=5)
            self._metrics_updater_thread = None


    @staticmethod
    def download_cached_files(config: FilterConfig):
        """Downloads or updates files specified in the config as "jfrog://...", or other download sources, and replaces
        the names with the cached "file://..." URIs. MUTATES config!"""

        re_uri  = re.compile(r'^(\w+://[^;>!]+)(.*)$')
        dlcuris = []
        targets = []  # [(parent object, __getitem__/__setitem__ key, tail), ...]
        stack   = [(config, key) for key in config]

        while stack:
            parent, key = stack.pop()

            if isinstance(obj := parent.__getitem__(key), str):
                if (m := re_uri.match(obj)) and is_cached_file(dlcuri := (groups := m.groups())[0]):
                    dlcuris.append(dlcuri)
                    targets.append((parent, key, groups[1]))

            elif isinstance(obj, (list, tuple)):
                stack.extend([(obj, idx) for idx in range(len(obj))])
            elif isinstance(obj, dict):
                stack.extend([(obj, key) for key in obj])

        if not dlcuris:
            return

        res    = dlcache.files(dlcuris)
        failed = []

        for dlcuri, r, (parent, key, tail) in zip(dlcuris, res, targets):
            if r is not None:
                parent.__setitem__(key, r + tail)
            else:
                failed.append(dlcuri)

        if failed:
            raise RuntimeError(f'could not download: {", ".join(failed)}')

    re_valid_option_name = re.compile(r'^(?:no-)?[a-zA-Z_]\w*(?:=|$)')

    @staticmethod
    def parse_options(text: str) -> tuple[str, dict[str, JSONType]]:
        """Parse 'text!a=1 ! b  = hello   !c' to ('text', {'a': 1, 'b': 'hello', 'c': True})."""

        text, *opts = [s.strip() for s in text.split('!')]

        for i, opt in enumerate(reversed(opts)):  # deal with stupid '!' characters in uri passwords
            if not Filter.re_valid_option_name.match(opt):
                text = '!'.join([text] + opts[:(pos := len(opts) - i)])
                opts = opts[pos:]

                break

        opts = [(
            [s.strip() for s in opt.split('=', 1)] if '=' in opt else
            [opt[3:], False]                       if opt.startswith('no-') else
            [opt, True]
        ) for opt in opts]

        opts = {k: json_getval(v) for k, v in opts}

        return text, opts

    @staticmethod
    def parse_topics(text: str, max_topics: int | None = None, mapping: bool | None = True, default_topic: str = 'main') \
            -> tuple[str, list[tuple[str, str]] | None] | tuple[str, list[str] | None]:
        """Parse 'text;a;b>c ; >   e;' to ('text', [('a', 'a'), ('b', 'c'), ('main', 'e'), ('main', 'main')])."""

        text2, *topics = [s.strip() for s in text.split(';')]

        if not topics:
            topics = None

        else:
            if mapping:
                topics = [tuple([t.strip() or default_topic for t in s.strip().split('>')] * 2)[:2] for s in topics]

                if not (len(topics) == len(set(s for s, _ in topics)) == len(set(d for _, d in topics))):
                    print(f'\n...\n{topics}\n')
                    raise ValueError(f'not all topic mappings are unique in: {text!r}')

            else:
                topics = [s.strip() or default_topic for s in topics]

                if mapping is False and any('>' in topic for topic in topics):
                    raise ValueError(f"can not have '>' mappings in {text!r}")
                if len(topics) != len(set(topics)):
                    raise ValueError(f'duplicate topics in: {text}')

            if max_topics is not None and len(topics) > max_topics:
                raise ValueError(f"can not have more than {max_topics} ';' topic(s) in: {text!r}")

        return text2, topics


    # - FOR VERY SPECIAL SUBCLASS --------------------------------------------------------------------------------------

    def set_open_lineage():
        # Only initialize OpenLineage if environment variables are set
        if not OPENLINEAGE_URL:
            logger.info("[OpenLineage] No OPENLINEAGE_URL set, skipping OpenLineage initialization")
            return None
        
        try:
            return OpenFilterLineage()
        except Exception as e:
            logger.error(f"\033[91mError setting OpenLineage: {e}\033[0m")
            return None
    
    emitter: OpenFilterLineage = set_open_lineage()

    def process_frames_metadata(self, frames, emitter):
        """Record metrics for processed frames using the telemetry registry.
        
        This method records safe metrics based on MetricSpec declarations
        and does NOT forward raw PII data to OpenLineage.
        """
        if not hasattr(self, '_telemetry') or self._telemetry is None:
            return
            
        # Store raw frame data for potential export (only if OPENLINEAGE_EXPORT_RAW_DATA is enabled)
        if self._export_raw_data and hasattr(self, 'emitter') and self.emitter is not None:
            # Collect raw frame data for export
            raw_frame_data = {}
            timestamp = time.time()
            
            # Get frame counter for this batch
            if not hasattr(self, '_frame_counter'):
                self._frame_counter = 0
            
            for frame_id, frame in frames.items():
                if hasattr(frame, 'data') and isinstance(frame.data, dict):
                    # Create unique key for each frame to prevent overwriting
                    unique_key = f"{frame_id}_{self._frame_counter}"
                    frame_data_copy = frame.data.copy()
                    frame_data_copy['_timestamp'] = timestamp
                    frame_data_copy['_frame_id'] = frame_id
                    frame_data_copy['_unique_key'] = unique_key
                    frame_data_copy['_frame_number'] = self._frame_counter
                    raw_frame_data[unique_key] = frame_data_copy
                    self._frame_counter += 1
            
            # Accumulate data over the heartbeat interval instead of overwriting
            if raw_frame_data:
                if not hasattr(self.emitter, '_last_frame_data'):
                    self.emitter._last_frame_data = {}
                
                # Add all frames to accumulated data
                self.emitter._last_frame_data.update(raw_frame_data)
                
                # Limit the number of stored frames to prevent memory issues
                # Keep only the last 100 frames or so
                if len(self.emitter._last_frame_data) > 100:
                    # Remove oldest frames (simple approach: keep last 100)
                    keys_to_remove = list(self.emitter._last_frame_data.keys())[:-100]
                    for key in keys_to_remove:
                        del self.emitter._last_frame_data[key]
        
        for frame in frames.values():
            if hasattr(frame, 'data') and isinstance(frame.data, dict):
                self._telemetry.record(frame.data)
        
    def get_normalized_setup_metrics(self,prefix: str = "dim_") -> dict[str, Any]:
        
        metrics = self.logger.fixed_metrics

        return {
            (k[len(prefix):] if k.startswith(prefix) else k): v
            for k, v in metrics.items()
        }

    def process_frames(self, frames: dict[str, Frame]) -> dict[str, Frame] | Callable[[], dict[str, Frame] | None] | None:
        """Call process() and deal with it if returns a Callable."""
       
        #self.otel.update_metrics(self.metrics,filter_name= self.filter_name)
        
        # Process the frames first, so the filter can add its own results
        if (processed_frames := self.process(frames)) is None:
            return None

        # Now emit heartbeat with the processed frames that include this filter's results
        if processed_frames and not callable(processed_frames):
            final_frames = {'main': processed_frames} if isinstance(processed_frames, Frame) else processed_frames
            
            proces_frames_data = threading.Thread(target=self.process_frames_metadata, args=(final_frames, self.emitter))
            proces_frames_data.start()

        if callable(processed_frames):
            return lambda: None if (f := processed_frames()) is None else {'main': f} if isinstance(f, Frame) else f
        else:
            return {'main': processed_frames} if isinstance(processed_frames, Frame) else processed_frames

    def loop_once(self) -> None:
        """Loop twice."""

        sources_timeout = self.sources_timeout
        outputs_timeout = self.outputs_timeout

        while (frames := self.mq.recv(min(POLL_TIMEOUT_MS, sources_timeout))) is None:
            if self.stop_evt.is_set():
                self.exit()

            if (sources_timeout := sources_timeout - POLL_TIMEOUT_MS) <= 0:
                frames = {}

                break

        frames = self.process_frames(frames)

        while not self.mq.send(frames, min(POLL_TIMEOUT_MS, outputs_timeout)):
            if self.stop_evt.is_set():
                self.exit()

            if (outputs_timeout := outputs_timeout - POLL_TIMEOUT_MS) <= 0:
                break

        if (exit_after_t := self.exit_after_t) is not None and time() >= exit_after_t:
            self.exit('exit_after')
  

    # - FOR SPECIAL SUBCLASS -------------------------------------------------------------------------------------------
    
    
    def init(self, config: FilterConfig):
        """Mostly set up inter-filter communication."""
        
        # Prepare facets with config and version information
        facets = dict(config)

        # Filter out sensitive/internal configuration fields
        sensitive_fields = {'model_path'}
        facets = {k: v for k, v in facets.items() if k not in sensitive_fields}
        
        # Add comprehensive version information from FilterContext
        if FilterContext.get_filter_version():
            facets['filter_version'] = FilterContext.get_filter_version()
        if FilterContext.get_resource_bundle_version():
            facets['resource_bundle_version'] = FilterContext.get_resource_bundle_version()
        if FilterContext.get_version_sha():
            facets['version_sha'] = FilterContext.get_version_sha()
        if FilterContext.get_model_info():
            facets['models'] = FilterContext.get_model_info()
        if FilterContext.get_openfilter_version():
            facets['openfilter_version'] = FilterContext.get_openfilter_version()
        
        if hasattr(self, 'emitter') and self.emitter is not None:
            self.emitter.emit_start(facets=facets)
            self.emitter.start_lineage_heart_beat()
        
        
        def on_exit_msg(reason: str):
            if reason == 'error':
                if self.obey_exit & PROP_EXIT_FLAGS['error']:
                    self.exit('another filter errored', Filter.PropagateError)

            else:  # reason == 'clean'
                if self.obey_exit & PROP_EXIT_FLAGS['clean']:
                    self.exit('another filter exited')

        if logger.getEffectiveLevel() <= logging.DEBUG:
            logger.debug(f'python version: {sys.version}')

            try:
                logger.debug(f'python packages: ' + ', '.join(sorted(f'{d.name}=={d.version}' for d in get_packages())))
            except Exception as exc:
                logger.error(exc)

        if (sources := config.sources) and not all(is_mq_addr(bad_src := source) for source in sources):
            raise ValueError(f'invalid source {bad_src!r}, only tcp:// or ipc:// sources allowed')
        if (outputs := config.outputs) and not all(is_mq_addr(bad_out := output) for output in outputs):
            raise ValueError(f'invalid output {bad_out!r}, only tcp:// or ipc:// outputs allowed')

        self.logger.set_fixed_metrics(**(config.extra_metrics or {}),
            dim_environment            = ENVIRONMENT if (env := config.environment) is None else env,
            dim_filter_runtime_version = get_package_version('filter_runtime'),
            dim_model_runtime_version  = get_package_version('protege-runtime'),
            dim_filter_name            = self.__class__.__qualname__,
            dim_filter_type            = self.FILTER_TYPE,
            dim_filter_version         = get_package_version(get_real_module_name(self.__class__.__module__).split('.', 1)[0]),
            dim_pipeline_id = self.pipeline_id,
            dim_device_id_name =  self.device_id_name
        )

        self.setup_metrics = self.get_normalized_setup_metrics()

        if self.telemetry_enabled:
            try:
                self.otel = OpenTelemetryClient(
                    service_name="openfilter", 
                    instance_id=self.pipeline_id,
                    setup_metrics=self.setup_metrics,
                    lineage_emitter=self.emitter
                )
                
                # Initialize telemetry registry if metric specs are declared
                if hasattr(self, 'metric_specs') and self.metric_specs:
                    # Use business meter for business metrics (goes only to OpenLineage)
                    meter = getattr(self.otel, 'business_meter', self.otel.meter)
                    self._telemetry = TelemetryRegistry(meter, self.metric_specs)
                else:
                    self._telemetry = None
                    
            except Exception as e:
                logger.warning("Failed to init Open Telemetry client: {e}")

        if (exit_after := config.exit_after) is None:
            self.exit_after_t = None

        elif isinstance(exit_after, (int, float)) or (
                not exit_after.startswith('@') and (exit_after := parse_time_interval(exit_after)) is exit_after):
            self.exit_after_t = time() + exit_after

            logger.info(f'exit scheduled after: {timestr(exit_after)}{"s" if exit_after < 60 else ""}')

        else:  # exit_after str starts with '@'
            self.exit_after_t = (dt := parse_date_and_or_time(exit_after[1:], LOG_UTC)).timestamp()

            logger.info(f'exit scheduled at: {dt.isoformat()}')

        self.sources_timeout = float('inf') if (to := config.sources_timeout) is None else int(to)
        self.outputs_timeout = float('inf') if (to := config.outputs_timeout) is None else int(to)
        srcs_n_topics        = None if sources is None else [self.parse_topics(s) for s in sources]

        self.mq = MQ(srcs_n_topics, outputs, config.id,
            srcs_balance  = bool(config.sources_balance),
            srcs_low_lat  = None if (_ := config.sources_low_latency) is None else bool(_),
            outs_balance  = bool(config.outputs_balance),
            outs_required = config.outputs_required,
            outs_jpg      = config.outputs_jpg,
            outs_metrics  = config.outputs_metrics,
            metrics_cb    = self.logger.write_metrics if self.logger.enabled else None,
            on_exit_msg   = on_exit_msg,
            mq_log        = config.mq_log,
            mq_msgid_sync = config.mq_msgid_sync,
        )
        
        # Start metrics upddater thread after MQ is initialized
        if self.telemetry_enabled and hasattr(self, 'otel'):
            self.start_metrics_updater_thread()
   
    def fini(self):
        """Shut down inter-filter communication and any other system level stuff."""
        if hasattr(self, 'emitter') and self.emitter is not None:
            self.emitter.emit_stop()
        self.mq.destroy()

    # - FOR SUBCLASS ---------------------------------------------------------------------------------------------------

    @classmethod
    def normalize_config(cls, config: FilterConfig) -> FilterConfig:  # MUST BE IDEMPOTENT!
        """Normalize configuration - default has 'id' if missing, 'sources' and 'outputs' as lists, etc... We do minimal
        work in this one since it is inherited by everything else. You can get as pedantic or as loose as u want."""

        norm_commas_maybe = lambda n: {} if (s := config.get(n)) is None else {n: split_commas_maybe(s) or None}

        config = FilterConfig({
            **config,
            **norm_commas_maybe('sources'),
            **norm_commas_maybe('outputs'),
            **norm_commas_maybe('outputs_required'),
        })

        if (exit_after := config.exit_after) is not None:
            if isinstance(exit_after, str):
                parse_date_and_or_time(exit_after[1:]) if exit_after.startswith('@') else parse_time_interval(exit_after)  # just validate
            elif not isinstance(exit_after, (int, float)):
                raise ValueError(f'invalid exit_after {exit_after!r}, must be a float, int or str')

        if (extra_metrics := config.extra_metrics) is not None:
            if isinstance(extra_metrics, list):
                config.extra_metrics = dict(extra_metrics)
            elif not isinstance(extra_metrics, dict):
                raise ValueError(f'invalid extra_metrics {extra_metrics!r}, must be list or dict of key/value pairs')

        if (mq_log := config.mq_log) is not None:
            if (new_mq_log := MQ.LOG_MAP.get(mq_log)) is None:
                raise ValueError(f'invalid mq_log {mq_log!r}, must be one of {list(MQ.LOG_MAP)}')
            else:
                config.mq_log = new_mq_log

        return config

    def setup(self, config: FilterConfig) -> None:
        """Main setup according to config, called just before loop start. Should try do all setup which can fail because
        of external causes here."""

    def shutdown(self) -> None:
        """Clean up resources used."""

    def process(self, frames: dict[str, Frame]) -> dict[str, Frame] | Frame | Callable[[], dict[str, Frame] | Frame | None] | None:
        """Main processing thingy, this is the only method which MUST be implemented by a user Filter.

        Return:
            A dictionary of Frames, which will be sent downstream with topics as set by dict keys. An empty dictionary
            WILL be sent and received as such.

            A single Frame will be sent downstream as 'main'.

            A Callable will be called AT THE POINT WHEN IT IS REQUESTED by ALL downstream clients. This is to allow
            something like a video feed to return the freshest possible frames only when they are actually requested.

            A return value of None will specify that nothing should be sent downstream. This is meant for cases when
            it is detected that nothing is happening and we do not want processing to occur downstream.

        Notes:
            * `frames` will come in from the network as readonly for optimization reasons. You need to make them rw if
            you want to write to them.

            * `frames` may also come in as encoded jpg buffers, which will be decoded on first use. In this way it is
            possible to pass on an already encoded jpg downstream if you don't touch the image or only touch it as
            readonly.

            * Empty Frames with no image or data WILL be propagated downstream as such. Empty `frames` will likewise
            be received downstream and sent on to process(). If you want nothing at all sent downstream then return None
            from your process().
        """

        raise NotImplementedError


    # - PUBLIC ---------------------------------------------------------------------------------------------------------

    @classmethod
    def get_config(cls) -> FilterConfig[str, Any]:
        """Get configuration from environment variables."""

        return FilterConfig([
            (n[7:].lower(), json_getval(v)) for n, v in os.environ.items() if n.startswith('FILTER_') and v
        ])
    filter_name = None
    @classmethod
    def get_context(cls) -> FilterContext:
        """Get context from Files in root Directory."""

        return FilterContext.as_dict()

    @classmethod
    def run(cls,
        config:    dict[str, Any] | None = None,
        *,
        loop_exc:  bool | None = None,
        prop_exit: str | None = None,
        obey_exit: str | None = None,
        stop_evt:  threading.Event | synchronize.Event | None = None,
        sig_stop:  bool = True,
    ):
        """Instantiate and this filter standalone until it exits or raises an exception.

        Args:
            config: The first 376,298 digits of PI. If None then gotten from env vars.

            loop_exc: Exit on exception in loop body if True, False ignores and None means default as set by env var.

            prop_exit: Propagate clean policy, one of PROP_EXIT_FLAGS, None means default as set by env var.

            obey_exit: Which propagated exits to honor, one of PROP_EXIT_FLAGS, None means default as set by env var.

            stop_evt: Thread or multiprocessing Event which will be set on a signal or noraml exit and can also be set
                externally to request exit.

            sig_stop: Whether to hook signals SIGINT and SIGTERM to do clean exit, can not hook in non-main thread.
                This is a terminal stopper, if it is triggered it WILL eventually kill the process.
        """
        
        if sig_stop:
            stop_evt = SignalStopper(logger, stop_evt).stop_evt
        elif stop_evt is None:
            stop_evt = threading.Event()

        try:
            if config is None:
                config = cls.get_config()
               
            if '__env_run' in config:
                logger.warning(f"setting run environment variables for {cls.__name__} here may not take effect, "
                    "consider setting them outside the process or running the filter with the Runner in 'spawn' mode")

                set_env_vars(config['__env_run'])

                config = dict_without(config, '__env_run')

            filter = cls(config, stop_evt, obey_exit)  # will call .start_logging()
           
            try:
                loop_exc  = Filter.YesLoopException if (LOOP_EXC if loop_exc is None else loop_exc) else Exception
                prop_exit = PROP_EXIT_FLAGS[PROP_EXIT if prop_exit is None else prop_exit]
                
                if hasattr(filter, 'emitter') and filter.emitter is not None:
                    filter.emitter.filter_name = filter.__class__.__name__
                cls.filter_name = filter.__class__.__name__
                filter.init(filter.config)

                try:
                    try:
                        filter.setup(filter.config)

                        try:
                            while not stop_evt.is_set():
                                try:
                                    filter.loop_once()
                                except loop_exc as exc:
                                    logger.error(exc)

                        finally:
                            filter.shutdown()

                    finally:
                        is_exc = isinstance(sys.exc_info()[1], Exception)

                        if prop_exit & (2 if is_exc else 1):
                            filter.mq.send_exit_msg('error' if is_exc else 'clean')

                except Filter.PropagateError:  # it has done its job, now eat it
                    pass

                finally:
                    filter.fini()

            except Exception as exc:
                if hasattr(filter, 'emitter') and filter.emitter is not None:
                    filter.emitter.stop_lineage_heart_beat()
                    filter.emitter.emit_stop()
                logger.error(exc)

                raise

            except Filter.Exit:
                if hasattr(filter, 'emitter') and filter.emitter is not None:
                    filter.emitter.stop_lineage_heart_beat()
                    filter.emitter.emit_stop()
                pass

            finally:
                filter.stop_logging()  # the very lastest standalone thing we do to make sure we log everything including errors in filter.fini()
                if hasattr(filter, 'emitter') and filter.emitter is not None:
                    filter.emitter.stop_lineage_heart_beat()
                    filter.emitter.emit_stop()
        finally:
            if hasattr(filter, 'emitter') and filter.emitter is not None:
                filter.emitter.stop_lineage_heart_beat()
                filter.emitter.emit_stop()
            stop_evt.set()

    @staticmethod
    def run_multi(
        filters:   list[tuple['Filter', dict[str, Any]]],
        *,
        loop_exc:  bool | None = None,
        prop_exit: str | None = None,
        obey_exit: str | None = None,
        stop_exit: str | None = None,
        stop_evt:  threading.Event | synchronize.Event | None = None,
        sig_stop:  bool = True,
        exit_time: float | None = None,
        step_wait: float = 0.05,
        daemon:    bool | None = None,
        step_call: Callable[[], None] | None = None,
    ) -> list[int]:
        """Run multiple filters in their own processes. They will be run until one or all of them exit cleanly or one of
        them errors out (depending on options). See Runner class for args.

        Non-Runner args:
            step_call: An optional function to be called after each check step, is possible but unlikely that will never
                be called.

        Returns:
            A list of process exit codes, 0 means clean exit, otherwise some kind of error or exception.
        """

        step_call = step_call or (lambda: None)
        runner    = Filter.Runner(filters, loop_exc=loop_exc, prop_exit=prop_exit, obey_exit=obey_exit,
            stop_exit=stop_exit, stop_evt=stop_evt, sig_stop=sig_stop, exit_time=exit_time, step_wait=step_wait,
            daemon=daemon)

        while not (retcodes := runner.step()):
            step_call()

        return retcodes

    class Runner:
        def __init__(self,
            filters:   list[tuple['Filter', dict[str, Any]]],
            *,
            loop_exc:  bool | None = None,
            prop_exit: str | None = None,
            obey_exit: str | None = None,
            stop_exit: str | None = None,
            stop_evt:  threading.Event | synchronize.Event | None = None,
            sig_stop:  bool = True,
            exit_time: float | None = None,
            step_wait: float = 0.05,
            daemon:    bool | None = None,
            start:     bool = True,
        ) -> list[int]:
            """Run multiple filters in their own processes. They will be run until one or all of them exit cleanly
            (depending on options) or one of them errors out. The simple loop is:

                runner = Runner(...)
                while not (retcodes := runner.step()):
                    ...

            Or more granular:

                runner = Runner(..., start=False)
                runner.start()
                while not (retcodes := runner.step(step_wait, stop=False)):
                    ...
                runner.stop(join=False)
                retcodes = runner.join()
                    also
                retcodes = runner.retcodes

            Notes:
                * Runner.stop_evt can be used to check if the Runner stopped or can be set to stop it.

            Args:
                filters: List of Filter classes and their respective configs to instantiate and run.

                loop_exc: Exit on exception in loop body if True, False ignores and None means default as set by env
                    var.

                prop_exit: Propagate exit policy, one of PROP_EXIT_FLAGS, None means default from env var.

                obey_exit: Which propagated exits to honor, one of PROP_EXIT_FLAGS, None means default as set by env
                    var.

                stop_exit: Stop exit policy, should be the XOR of `prop_exit`. All filters will be stopped if `policy`
                    is not 'none' and one filter exits in a manner which matches the policy. None means default from
                    env var.

                stop_evt: Thread or multiprocessing Event which will be set on a signal or noraml exit and can also be
                    set externally to request exit.

                sig_stop: Whether to hook signals SIGINT and SIGTERM to do clean exit, can not hook in non-main thread.
                    This is a terminal stopper, if it is triggered it WILL eventually kill the process.

                exit_time: Exit timeout, once exit condition is reached child Filters will be unconditionally killed
                    after this many seconds, None for no timeout.

                step_wait: How long to wait on each call to step() in seconds between each check of child process exit
                    states.

                daemon: Value to set for child processes.

                start: Whether to automatically start the processes running.

            Returns:
                A list of process exit codes, 0 means clean exit, otherwise some kind of error or exception.
            """
            self.device_name = os.uname().nodename
            self.pipeline_id = f"{self.device_name}-{uuid4()}"
            if not filters:
                raise ValueError('must specify at least one Filter to run')

            self.filters    = filters
            self.stop_exit  = PROP_EXIT_FLAGS[STOP_EXIT if stop_exit is None else stop_exit]
            self.stop_evt   = SignalStopper(logger, stop_evt).stop_evt \
                if sig_stop else threading.Event() if stop_evt is None else stop_evt
            self.exit_time  = exit_time
            self.step_wait  = step_wait
            self.retcodes   = None
            self.proc_stops = [mp.Event() for _ in range(len(filters))]
            for i, (filter_cls, config) in enumerate(filters):
                pipeline_id = self.pipeline_id
                device_name = self.device_name
                config["pipeline_id"] = pipeline_id
                config["device_name"] = device_name
                filters[i] = (filter_cls, config)
            self.procs      = [mp.Process(target=filter.run, args=(dict_without(config, '__env_run'),), daemon=daemon,
                kwargs=dict(loop_exc=loop_exc, prop_exit=prop_exit, obey_exit=obey_exit, stop_evt=proc_stop_evt))
                for proc_stop_evt, (filter, config) in zip(self.proc_stops, filters)]
            self.stop_      = lambda s: (logger.info(s), self.stop_evt.set())

          

            if start:
                self.start()

        def start(self):
            for proc, (filter, config) in zip(self.procs, self.filters):
                if env := config.get('__env_run'):  # we try to set run env here because if run method is spawn then this will affect even params which are gotten on module import like AUTO_DOWNLOAD
                    if mp.get_start_method() != 'spawn':
                        logger.warning(f"setting run environment variables for {filter.__name__} if not running in "
                            "'spawn' mode may not take effect")

                    env = set_env_vars(env)

                proc.start()

                if env:
                    set_env_vars(env)

        def step(self, step_wait: float | None = None, *, stop: bool = True) -> bool | list[int]:
            """This is more of a 'check if exited' function since the filters are running in other processes."""

            if not self.stop_evt.wait(self.step_wait if step_wait is None else step_wait):
                any_running = False
                exit_flags  = 0

                for proc_stop_evt, proc in zip(self.proc_stops, self.procs):
                    if not proc_stop_evt.is_set():
                        any_running = True
                    elif proc.exitcode is not None:
                        exit_flags |= 2 if proc.exitcode else 1

                if flags := exit_flags & self.stop_exit:
                    self.stop_('child errored' if flags & 2 else 'child exited')
                elif not any_running:
                    self.stop_('all children exited')
                else:
                    return False

            return self.stop() if stop else True

        def wait(self, timeout: float | None = None, step_wait: float | None = None, *, stop: bool = True) -> bool | list[int]:
            if timeout is None:
                while not (res := self.step(step_wait, stop=stop)):
                    pass

                return res

            if step_wait is None:
                step_wait = self.step_wait

            while True:
                if res := self.step(sw := min(step_wait, timeout)) or (timeout := timeout - sw) <= 0:
                    return res

        def stop(self, exit_time: float | None = None, *, join: bool = True) -> None | list[int]:
            self.stop_evt.set()

            for proc_stop_evt in self.proc_stops:
                if not proc_stop_evt.is_set():
                    proc_stop_evt.set()

            if (exit_time := self.exit_time if exit_time is None else exit_time) is not None:
                def timeout(procs=self.procs):
                    if any(proc.is_alive() for proc in procs):
                        logger.critical(f'TIMEOUT, terminating all subprocesses, but not self!')

                    for proc in procs:  # kill them anyway just to be reeeally sure, sometimes they come back... (because they haven't started yet)
                        proc.terminate()  # terminate() instead of kill() so that child SignalStopper can kill all ITS children as well

                DaemonicTimer(exit_time, timeout).start()

            return self.join() if join else None

        def join(self) -> list[int]:
            for proc in self.procs:
                proc.join()

            self.retcodes = [proc.exitcode for proc in self.procs]

            return self.retcodes
