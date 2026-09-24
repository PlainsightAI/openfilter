import logging
import os
import json
import time
from queue import Queue
from threading import Thread, RLock

from openfilter.filter_runtime.filter import FilterConfig, Filter
from openfilter.filter_runtime.frame import Frame
# Latency instrumentation, which is not part of the framework and lives outside it in
# `openfilter_timings/`. Imported defensively so that deleting that folder leaves webvis working:
# the options then parse as before and do nothing, rather than the filter failing to import.
try:
    from openfilter_timings import (
        TIMINGS_PAGE, draw_table, insert_jpeg_comment, timing_payload, timing_rows,
    )
except ImportError:  # pragma: no cover - only when the folder has been removed
    TIMINGS_PAGE = None
from openfilter.filter_runtime.utils import dict_without, split_commas_maybe

__all__ = ['WebvisConfig', 'Webvis']

logger = logging.getLogger(__name__)

QUEUE_LEN = 3


class WebvisConfig(FilterConfig):
    host: str | None
    port: int | None
    enable_json: bool = False
    sleep_interval: float = 1.0
    auth_token: str | None = None
    cors_origins: str | None = None
    access_log: bool = False
    enable_snapshot_payload: bool = False
    timings: str | bool = False


class Webvis(Filter):
    """Show incoming topic image stream on a web server. Whevever it is plugged into in the pipeline, you will be able
    to see that stream of images on 'http://localhost:8000/topic', or wherever else you configure this to serve.

    config:
        outputs:
            Can pass a single output as an `http://` URI to specify where to host, for example
            'http://192.168.1.13:6000' to only host at this address. '0.0.0.0', '0' and '*' are all accepted to mean
            host on all interfaces.

        host:
            You can also specify where to serve using this and `port` instead of outputs, in this case they both have
            their own defaults. Default '0.0.0.0'.

        port:
            Default 8000.

        auth_token:
            When set, all requests must include ``?token=<value>`` or ``Authorization: Bearer <value>``.
            Returns 401 if missing or invalid. Also settable via ``FILTER_AUTH_TOKEN`` env var.

        cors_origins:
            Comma-separated list of allowed CORS origins. Defaults to ``'*'`` (allow all,
            credentials disabled). Set specific origins to enable ``Access-Control-Allow-Credentials``.
            Example: ``'https://portal.plainsight.tech,https://localhost:5173'``.
            Also settable via ``FILTER_CORS_ORIGINS`` env var.

        access_log:
            Whether to enable uvicorn access logging globally for Webvis. Default ``False`` (disabled
            to avoid excessive log spam from snapshot/polling endpoints). Also settable via ``FILTER_ACCESS_LOG`` env var.

        enable_snapshot_payload:
            Whether to enable the GET /snapshot-payload and /{topic}/snapshot-payload REST endpoints.
            Default ``False``. Also settable via ``FILTER_ENABLE_SNAPSHOT_PAYLOAD`` env var.

        timings:
            Draw this frame's timing chain onto the picture, off by default. `true` puts the table
            in the top left; a corner name (`top-left`, `top-right`, `bottom-left`,
            `bottom-right`) puts it where the camera's own timestamp is not. One row per filter,
            columns `ID FILTER TIME IN TIME OUT TOTAL MS`, times as raw epoch seconds so they line
            up with the same numbers printed from the subject data, and TOTAL MS the frame's total
            from the first filter in to the last filter out. Also settable via ``FILTER_TIMINGS``.

            The chain travels in the served JPEG's COM segment whether or not this is on: a frame
            that carries its own timings cannot be paired with another frame's, which is the risk
            when the picture comes from one URL and the subject data from another. Drawing is the
            part that is optional, because it writes on the picture.
    """

    FILTER_TYPE = 'Output'

    def create_app(self, auth_token: str | None = None, cors_origins: str | None = None) -> 'FastAPI':
        from fastapi import FastAPI, Response
        from fastapi.responses import StreamingResponse
        from openfilter.filter_runtime.filters.http_security import configure_http_security

        if not hasattr(self, '_lock'):
            self._lock = RLock()

        if not hasattr(self, 'enable_snapshot_payload'):
            self.enable_snapshot_payload = False

        app = FastAPI(title='webvis')

        configure_http_security(app, auth_token=auth_token, cors_origins=cors_origins)

        async def stream_data(topic: str | None = None):
            # Decide on connection whether this stream is in flat mode (locked for this connection's lifetime)
            _, _, is_flat = get_metadata_for_topic(topic)

            def gen(flat: bool):
                while True:
                    _, data, _ = get_metadata_for_topic(topic, force_flat=flat)
                    
                    if self.enable_json:
                        yield f"data: {json.dumps(data)}\n\n"
                    else:
                        yield f"data: {data}\n\n"
                    time.sleep(self.sleep_interval)

            return StreamingResponse(gen(is_flat), media_type='text/event-stream')

        def get_metadata_for_topic(topic: str | None, force_flat: bool | None = None) -> tuple[str, dict, bool]:
            """Helper to resolve the active topic and return the metadata snapshot matching SSE data schema."""
            with self._lock:
                latest_frames_keys = list(getattr(self, 'latest_frames', {}).keys())
                streams_keys = list(self.streams.keys())
                current_data_snapshot = dict(self.current_data)

            is_multi_topic_config = getattr(self, 'is_multi_topic_static', False) or len(getattr(self, 'configured_topics', set())) > 1
            is_default = (topic is None or (topic == 'main' and 'main' not in latest_frames_keys and 'main' not in streams_keys))

            # Resolve topic
            if is_default:
                active_topics = latest_frames_keys or list(current_data_snapshot.keys()) or streams_keys
                resolved_topic = active_topics[0] if active_topics else 'main'
            else:
                resolved_topic = topic

            # Decide on flat mode
            if force_flat is not None:
                is_flat = force_flat
            elif is_default:
                is_flat = (not is_multi_topic_config) and (len(current_data_snapshot) <= 1)
            else:
                is_flat = True

            if is_flat:
                data = current_data_snapshot.get(resolved_topic, {})
            else:
                data = current_data_snapshot

            return resolved_topic, data, is_flat

        if self.enable_snapshot_payload:
            @app.get('/{topic:str}/snapshot-payload')
            @app.get('/snapshot-payload')
            def get_snapshot_payload(topic: str | None = None):
                """Serves JPEG frame snapshots along with associated frame metadata packed into a JSON response.
                
                Returns a JSON body containing:
                - topic: The resolved topic name.
                - timestamp: The server epoch time when the snapshot response was generated.
                - width / height / format: Dimensions and color format of the frame.
                - metadata: The frame's metadata dictionary.
                - image: The base64-encoded JPEG image string.
                """
                import base64

                with self._lock:
                    resolved_topic, data, _ = get_metadata_for_topic(topic)
                    frame = self.latest_frames.get(resolved_topic)
                
                if frame is None:
                    return Response(status_code=404, content="No frame available")
                    
                try:
                    jpg_bytes = bytes(frame.bgr.jpg)
                except Exception as exc:
                    logger.error("JPEG encoding failed for topic %s: %s", resolved_topic, exc)
                    return Response(status_code=500, content="JPEG encoding failed")

                response_body = {
                    "topic": resolved_topic,
                    "timestamp": time.time(),
                    "width": frame.width,
                    "height": frame.height,
                    "format": str(frame.format),
                    "metadata": data,
                    "image": base64.b64encode(jpg_bytes).decode('utf-8')
                }
                return Response(
                    content=json.dumps(response_body, default=str),
                    media_type="application/json"
                )

        @app.get('/timings', include_in_schema=TIMINGS_PAGE is not None)
        def timings_page():
            """The browser side of the measurement.

            Registered before '/{topic}' so the name resolves here rather than being read as a
            topic, the same shadowing '/snapshot-payload' has. A topic genuinely named 'timings'
            is still reachable at '/timings/data' and through this page's ?topic= parameter.
            """

            from fastapi.responses import HTMLResponse, PlainTextResponse

            if TIMINGS_PAGE is None:
                return PlainTextResponse('openfilter_timings is not installed', status_code=404)

            return HTMLResponse(TIMINGS_PAGE)

        @app.get('/data')
        async def get_data_default():
            return await stream_data(topic=None)

        @app.get('/{topic:str}/data')
        async def get_data(topic: str):
            return await stream_data(topic=topic)

        @app.get('/')
        @app.get('/{topic:str}')
        def topic(topic: str | None = None):
            with self._lock:
                streams_keys = list(self.streams.keys())
                if topic is None or (topic == 'main' and 'main' not in streams_keys):
                    topic = (streams_keys + ['main'])[0]
                queue = self.streams.get(topic) or self.streams.setdefault(topic, Queue(QUEUE_LEN))

            def gen():
                while True:
                    yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n'
                           + self._jpg_with_timings(queue.get()) + b'\r\n')

            return StreamingResponse(gen(), media_type='multipart/x-mixed-replace; boundary=frame')

        return app

    def serve(self, host: str | None = None, port: int | None = None,
              auth_token: str | None = None, cors_origins: str | None = None,
              access_log: bool = False):
        import uvicorn

        uvicorn.Server(uvicorn.Config(
            self.create_app(auth_token=auth_token, cors_origins=cors_origins),
            host       = host or '0.0.0.0',
            port       = port or 8000,
            loop       = 'asyncio',
            log_config = None,
            log_level  = (os.getenv('LOG_LEVEL') or 'info').lower(),
            access_log = access_log,
        )).run()

    @classmethod
    def normalize_config(cls, config):
        outputs = split_commas_maybe(config.get('outputs'))  # we do not assume how Filter will normalize sources/outputs in the future
        config  = WebvisConfig(super().normalize_config(dict_without(config, 'outputs')))
        env_mapping = {
            "enable_json": bool,
            "sleep_interval": float,
            "auth_token": str,
            "cors_origins": str,
            "access_log": bool,
            "enable_snapshot_payload": bool,
            "timings": str,
        }
        for key, expected_type in env_mapping.items():
            env_key = f"FILTER_{key.upper()}"
            env_val = os.getenv(env_key)
            if env_val is not None:
                if expected_type is bool:
                    setattr(config, key, env_val.strip().lower() == "true")
                elif expected_type is float:
                    setattr(config, key, float(env_val.strip()))
                elif expected_type is int:
                    setattr(config, key, int(env_val.strip()))
                else:
                    setattr(config, key, env_val.strip())

        if outputs is not None:
            config.outputs = outputs

        if not config.sources:
            raise ValueError('must specify at least one source')

        if config.sleep_interval <= 0:
            raise ValueError('sleep interval must be greater than 0, got:{config.sleep_interval}')

        # A bad corner is warned about and falls back at draw time rather than refusing to start:
        # this is debug instrumentation, and a run that dies over a typo in it measures nothing.
        if isinstance(config.timings, str):
            config.timings = config.timings.strip().lower()

            if config.timings in ('false', 'no', '0', ''):
                config.timings = False
            elif config.timings in ('true', 'yes', '1'):
                config.timings = True

        if outputs:  # convenience output "http://host:port" -> config.host / config.port
            if len(outputs) != 1:
                raise ValueError('filter only takes a single output')
            if not (output := outputs[0]).startswith('http://'):
                raise ValueError('filter only takes http:// output')

            addr, *path = output[7:].split('/', 1)

            if path and path[0]:
                raise ValueError('can not specify a path, only a host and port')

            host, *port = addr.rsplit(':', 1)

            if host:
                config.host = host
            if port:
                config.port = int(port[0])

            del config.outputs

        return config

    def setup(self, config):
        self._lock = RLock()
        self.streams = {}  # {'topic': Queue, ...}
        self.current_data = {}  # {'topic': dict, ...}
        self.latest_frames = {}  # {'topic': Frame, ...}
        self.enable_json = config.enable_json
        self.sleep_interval = config.sleep_interval
        self.access_log = config.access_log
        self.enable_snapshot_payload = config.enable_snapshot_payload
        self.instrumented = TIMINGS_PAGE is not None
        self.timings = config.timings if self.instrumented else False

        if config.timings and not self.instrumented:
            logger.warning('timings requested but openfilter_timings is not installed, ignoring')
        self.timings_scale = config.timings_scale

        # Parse configured topics to know if we are in a static multi-topic configuration
        self.configured_topics = set()
        if config.sources:
            for source in config.sources:
                try:
                    parsed = self.parse_topics(source)
                    if parsed and parsed[1]:
                        for _, target in parsed[1]:
                            self.configured_topics.add(target)
                except Exception as exc:
                    logger.debug("Failed to parse topics from source %s: %s", source, exc)

        self.is_multi_topic_static = len(self.configured_topics) > 1 or (len(config.sources) > 1 if config.sources else False)

        Thread(
            target=self.serve,
            args=(config.host, config.port, config.auth_token, config.cors_origins, config.access_log),
            daemon=True
        ).start()

    def _jpg_with_timings(self, frame):
        """The frame's JPEG, with its timing chain drawn on it and/or carried in a COM segment.

        Drawn at serve time rather than in `process()` so webvis's own entry is there to draw:
        `_inject_timings` appends a filter's in/out to `filter_timings` only after its `process()`
        returns, so inside `process()` every block would be complete except webvis's own. Here the
        chain is whole and every filter reads the same three lines, plus one block for the instant
        the JPEG goes out, which is the one value no filter records.

        The cost is per connected browser rather than per frame. That is the price of the last
        block being real rather than self-reported, and this is debug instrumentation serving one
        or two watchers, not a fan-out path.

        getattr, not attribute access: this is reachable on an instance that never ran setup()
        (the endpoint tests drive it that way), the same reason create_app guards
        enable_snapshot_payload.
        """

        if not getattr(self, 'instrumented', False):
            return frame.bgr.jpg

        # REVIEWERS: the two halves are gated differently on purpose, and this is the call to
        # confirm. Drawing is off unless asked for, because it writes on the picture. Embedding the
        # chain in the COM segment happens on every served frame, because a frame that carries its
        # own numbers cannot be paired with another frame's, and that pairing is exactly what is
        # unsafe today when the picture comes from one URL and the subject data from another. The
        # cost is about 280 bytes per frame on a two-filter chain, no re-encode, and every decoder
        # skips the segment. If that is too much to pay by default, move it behind `timings` too:
        # one line, and the page then needs the option on to measure anything.
        drawn = getattr(self, 'timings', False)
        served = time.time()  # one stamp, so the drawn and carried chains cannot disagree

        try:
            if drawn:
                rw = frame.bgr.rw
                header, rows = timing_rows(frame.data)
                draw_table(rw.image, header, rows,
                           corner = drawn if isinstance(drawn, str) else 'top-left')
                jpg = Frame(rw.image, frame, 'BGR').jpg
            else:
                jpg = frame.bgr.jpg

            return insert_jpeg_comment(jpg, json.dumps(timing_payload(frame.data, served)))
        except Exception as exc:  # instrumentation must never cost the stream
            logger.warning('timing instrumentation failed, serving the frame as it is: %s', exc)
            return frame.bgr.jpg

    def process(self, frames):
        for topic, frame in frames.items():
            if frame.has_image:
                with self._lock:
                    self.latest_frames[topic] = frame
                    self.current_data[topic] = frame.data
                    queue = self.streams.get(topic) or self.streams.setdefault(topic, Queue(QUEUE_LEN))
                if queue.empty():
                    queue.put(frame)
                else:
                    logger.debug('Skipping frames')


if __name__ == '__main__':
    Webvis.run()
