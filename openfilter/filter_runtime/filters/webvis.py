import logging
import os
import json
from queue import Queue
from threading import Thread

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
    """

    FILTER_TYPE = 'Output'

    def create_app(self) -> 'FastAPI':
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import StreamingResponse

        app = FastAPI(title='webvis')#, version=version)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=['*'],
            allow_credentials=True,
            allow_methods=['*'],
            allow_headers=['*'],
        )

        @app.get('/')
        @app.get('/{topic:str}')
        def topic(topic: str | None = None):
            topic = (list(self.streams) + ['main'])[0] if topic is None else topic
            queue = self.streams.get(topic) or self.streams.setdefault(topic, Queue(QUEUE_LEN))

            def gen():
                while True:
                    yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + queue.get().bgr.jpg + b'\r\n')

            return StreamingResponse(gen(), media_type='multipart/x-mixed-replace; boundary=frame')
        
        @app.get('/{topic:str}/data')
        async def get_data():
            from fastapi.responses import StreamingResponse
            import time
            def gen():
                while True:
                    if self.enable_json:
                        yield f"data: {json.dumps(self.current_data)}\n\n"
                    else:
                        yield f"data: {self.current_data}\n\n"
                    time.sleep(self.sleep_interval)

            return StreamingResponse(gen(), media_type='text/event-stream')

        return app

    def serve(self, host: str | None = None, port: int | None = None):
        import uvicorn

        uvicorn.Server(uvicorn.Config(
            self.create_app(),
            host       = host or '0.0.0.0',
            port       = port or 8000,
            loop       = 'asyncio',
            log_config = None,
            log_level  = (os.getenv('LOG_LEVEL') or 'info').lower(),
        )).run()

    @classmethod
    def normalize_config(cls, config):
        outputs = split_commas_maybe(config.get('outputs'))  # we do not assume how Filter will normalize sources/outputs in the future
        config  = WebvisConfig(super().normalize_config(dict_without(config, 'outputs')))
        env_mapping = {
            "enable_json": bool,
            "sleep_interval": float,
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
        self.streams = {}  # {'topic': Queue, ...}
        self.enable_json = config.enable_json
        self.sleep_interval = config.sleep_interval

        Thread(target=self.serve, args=(config.host, config.port), daemon=True).start()

    def process(self, frames):
        for topic, frame in frames.items():
            if frame.has_image:
                if (queue := self.streams.get(topic) or self.streams.setdefault(topic, Queue(QUEUE_LEN))).empty():
                    queue.put(frame)
                    self.current_data = frame.data
                else:
                    logger.debug('Skipping frames')


if __name__ == '__main__':
    Webvis.run()
