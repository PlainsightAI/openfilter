import logging
import multiprocessing as mp
import os
import re
import sys
import threading
from multiprocessing import synchronize
from time import time
from typing import Any, Callable, Literal, List

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
from openfilter.filter_runtime.open_telemetry.open_telemetry_client import OpenTelemetryClient
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
    - model_version: The version of the model, read from the file 'VERSION.MODEL'.
    - git_sha: The GitHub commit SHA, read from the file 'GITHUB_SHA'. This should be set at build time by CI/CD or manually.
    - models: A dictionary of models loaded from 'models.toml'. Each entry contains:
        - model name (key)
        - version: The version string for the model
        - path: The path to the model file (if present), or 'No path' if not specified

    This context is intended to provide runtime and build information for logging, debugging, and traceability. It is accessed via classmethods such as FilterContext.get(key), FilterContext.as_dict(), and FilterContext.log().

    Example usage:
        FilterContext.init()  # Initializes context if not already done
        version = FilterContext.get('filter_version')
        FilterContext.log()   # Logs all context info
    """

    _data = {}

    @classmethod
    def init(cls):
        if cls._data:
            return  # already initialized

        cls._data = {
            "filter_version": cls._read_file("VERSION"),
            "model_version": cls._read_file("VERSION.MODEL"),
            "git_sha": cls._read_file("GITHUB_SHA"),
            "models": cls._read_models_toml()
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
            config['id'] = f'{self.__class__.__name__}-{rndstr(6)}'  # everything must hava an ID for sanity
        
        pipeline_id = config.get("pipeline_id")
        self.device_id_name = config.get("device_name")
        self.pipeline_id = pipeline_id  # to store as an attribute
       

        FilterContext.init()

        self.start_logging(config)  # the very firstest thing we do to catch as much as possible
        enabled_otel_env = os.getenv("TELEMETRY_EXPORTER_ENABLED")
        self._metrics_updater_thread = None
        try:
             self.telemetry_enabled: bool = bool(strtobool(enabled_otel_env)) if enabled_otel_env is not None else False
        except ValueError:
             logger.warning(f"Invalid TELEMETRY_EXPORTER_ENABLED value: {enabled_otel_env}. Defaulting to False.")
             self.telemetry_enabled = False
        
    
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
            self.emitter.stop_lineage_heart_beat()
            self.stop_metrics_updater_thread()
            self.emitter.emit_stop()
            logger.info(f'{reason}, exiting...' if reason else 'exiting...')

        raise exc or Filter.Exit
    """
    def start_metrics_updater_thread(self):
        interval = self.otel.export_interval_millis / 1000  
        
        def loop():
            while not self.stop_evt.is_set():
                try:
                    self.otel.update_metrics(self.metrics, filter_name=self.filter_name)
                except Exception as e:
                    logger.error(f"[metrics_updater] error when trying to update metrics: {e}")
                self.stop_evt.wait(interval)  

        threading.Thread(target=loop, daemon=True).start()
    """
    def start_metrics_updater_thread(self):
        interval = self.otel.export_interval_millis / 1000  

        def loop():
            while not self.stop_evt.is_set():
                try:
                    self.otel.update_metrics(self.metrics, filter_name=self.filter_name)
                except Exception as e:
                    logger.error(f"[metrics_updater] erro ao atualizar métricas: {e}")
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
        try:
            return OpenFilterLineage()
        except Exception as e:
            print(e)
    
    emitter: OpenFilterLineage = set_open_lineage()

    def process_frames_metadata(self, frames, emitter):
        """Record metrics for processed frames using the telemetry registry.
        
        This method records safe metrics based on MetricSpec declarations
        and does NOT forward raw PII data to OpenLineage.
        """
        if not hasattr(self, '_telemetry') or self._telemetry is None:
            return
            
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
        
        self.emitter.emit_start(facets=dict(config))
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
                    meter = self.otel.meter
                    self._telemetry = TelemetryRegistry(meter, self.metric_specs)
                else:
                    self._telemetry = None
                    
                self.start_metrics_updater_thread()
            except Exception as e:
                logger.error("Failed to init Open Telemetry client: {e}")

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
   
    def fini(self):
        """Shut down inter-filter communication and any other system level stuff."""
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
                
                cls.emitter.filter_name = filter.__class__.__name__
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
                cls.emitter.stop_lineage_heart_beat()
                cls.emitter.emit_stop()
                logger.error(exc)

                raise

            except Filter.Exit:
                cls.emitter.stop_lineage_heart_beat()
                cls.emitter.emit_stop()
                pass

            finally:
                filter.stop_logging()  # the very lastest standalone thing we do to make sure we log everything including errors in filter.fini()
                cls.emitter.stop_lineage_heart_beat()
                cls.emitter.emit_stop()
        finally:
            cls.emitter.stop_lineage_heart_beat()
            cls.emitter.emit_stop()
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
