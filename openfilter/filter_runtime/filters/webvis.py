import logging
import os
import json
import time
from queue import Queue
from threading import Thread, RLock

from openfilter.filter_runtime.filter import FilterConfig, Filter
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
    """

    FILTER_TYPE = 'Output'

    def create_app(self, auth_token: str | None = None, cors_origins: str | None = None) -> 'FastAPI':
        from fastapi import FastAPI, Response
        from fastapi.responses import StreamingResponse, JSONResponse
        from openfilter.filter_runtime.filters.http_security import configure_http_security

        if not hasattr(self, '_lock'):
            self._lock = RLock()

        app = FastAPI(title='webvis')

        configure_http_security(app, auth_token=auth_token, cors_origins=cors_origins)

        async def stream_data(topic: str | None = None):
            is_multi_topic_config = getattr(self, 'is_multi_topic_static', False) or len(getattr(self, 'configured_topics', set())) > 1

            with self._lock:
                streams_keys = list(self.streams.keys())
                current_data_len = len(self.current_data)

            # If topic is 'main' but not in streams, treat it as default fallback (None)
            is_default = (topic is None or (topic == 'main' and 'main' not in streams_keys))

            # Decide on connection whether this stream is in flat mode (locked for this connection's lifetime)
            if is_default:
                # Flat mode if not statically multi-topic, and at most one active topic in current data
                is_flat = (not is_multi_topic_config) and (current_data_len <= 1)
            else:
                is_flat = True

            def gen(flat: bool):
                while True:
                    with self._lock:
                        current_data_snapshot = dict(self.current_data)
                    if flat:
                        if is_default:
                            # Use the single active topic if present, otherwise default to 'main'
                            active_topic = list(current_data_snapshot.keys())[0] if current_data_snapshot else 'main'
                        else:
                            active_topic = topic
                        data = current_data_snapshot.get(active_topic, {})
                    else:
                        data = current_data_snapshot
                    
                    if self.enable_json:
                        yield f"data: {json.dumps(data)}\n\n"
                    else:
                        yield f"data: {data}\n\n"
                    time.sleep(self.sleep_interval)

            return StreamingResponse(gen(is_flat), media_type='text/event-stream')

        def get_metadata_for_topic(topic: str | None) -> tuple[str, dict]:
            """Helper to resolve the active topic and return the metadata snapshot matching SSE data schema."""
            with self._lock:
                latest_frames_keys = list(self.latest_frames.keys())
                streams_keys = list(self.streams.keys())
                current_data_snapshot = dict(self.current_data)

            is_multi_topic_config = getattr(self, 'is_multi_topic_static', False) or len(getattr(self, 'configured_topics', set())) > 1
            is_default = (topic is None or (topic == 'main' and 'main' not in latest_frames_keys and 'main' not in streams_keys))

            # Resolve topic
            if is_default:
                active_topics = latest_frames_keys or streams_keys or list(current_data_snapshot.keys())
                resolved_topic = active_topics[0] if active_topics else 'main'
            else:
                resolved_topic = topic

            # Decide on flat mode
            if is_default:
                is_flat = (not is_multi_topic_config) and (len(current_data_snapshot) <= 1)
            else:
                is_flat = True

            if is_flat:
                data = current_data_snapshot.get(resolved_topic, {})
            else:
                data = current_data_snapshot

            return resolved_topic, data

        @app.get('/{topic:str}/snapshot-payload')
        @app.get('/snapshot-payload')
        @app.get('/api/snapshot-payload/{topic:str}')
        @app.get('/api/snapshot-payload')
        def get_snapshot_payload(topic: str | None = None):
            """Serves JPEG frame snapshots along with associated frame metadata packed into response headers.

            NOTE: Response headers (X-Metadata) are subject to HTTP header size limits (typically 8-16KB depending 
            on downstream proxies/servers). For large metadata structures (e.g. many detections), clients 
            should poll /snapshot and /latest-data separately to avoid HTTP header truncation or refusal.
            """
            import urllib.parse

            resolved_topic, data = get_metadata_for_topic(topic)
            with self._lock:
                frame = self.latest_frames.get(resolved_topic)
            
            # Pack metadata into custom HTTP headers (URL encoded for safety)
            headers = {
                "Access-Control-Expose-Headers": "X-Metadata, X-Topic, X-Timestamp, X-Width, X-Height, X-Format",
                "X-Topic": urllib.parse.quote(str(resolved_topic)),
                "X-Metadata": urllib.parse.quote(json.dumps(data, default=str)),
                "X-Timestamp": str(time.time()),
                "X-Width": str(frame.width) if frame else "",
                "X-Height": str(frame.height) if frame else "",
                "X-Format": str(frame.format) if frame else ""
            }

            if frame is None:
                return Response(status_code=404, content="No frame available", headers=headers)
                
            return Response(content=bytes(frame.bgr.jpg), media_type="image/jpeg", headers=headers)

        @app.get('/{topic:str}/snapshot')
        @app.get('/snapshot')
        @app.get('/api/snapshot/{topic:str}')
        @app.get('/api/snapshot')
        def get_snapshot(topic: str | None = None):
            resolved_topic, _ = get_metadata_for_topic(topic)
            with self._lock:
                frame = self.latest_frames.get(resolved_topic)
            if frame is None:
                return Response(status_code=404, content="No snapshot available")
            return Response(content=bytes(frame.bgr.jpg), media_type="image/jpeg")

        @app.get('/{topic:str}/latest-data')
        @app.get('/latest-data')
        @app.get('/api/latest-data/{topic:str}')
        @app.get('/api/latest-data')
        def get_latest_data(topic: str | None = None):
            _, data = get_metadata_for_topic(topic)
            # Use json.dumps with default=str to match SSE semantics and handle non-JSON-serializable metadata gracefully
            serialized_data = json.dumps(data, default=str)
            return Response(content=serialized_data, media_type="application/json")

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
                    yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + queue.get().bgr.jpg + b'\r\n')

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
