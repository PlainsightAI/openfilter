import logging
import os
from collections import defaultdict
from queue import Queue, Empty, Full
from threading import Thread

from openfilter.filter_runtime.filter import FilterConfig, Filter, Frame, POLL_TIMEOUT_SEC
from openfilter.filter_runtime.utils import dict_without, split_commas_maybe, adict

__all__ = ['RESTConfig', 'REST']

logger = logging.getLogger(__name__)

QUEUE_LEN            = 256
DEFAULT_DECLARED_FPS = None


class RESTConfig(FilterConfig):
    class Endpoint(adict):
        methods: list[str] | None  # e.g. ['GET'] or ['GET', 'POST'] or ['GET', 'PUT', 'POST', 'DELETE'] or any combination
        path:    str | None        # e.g. 'path' or 'path/sub', etc... None means no path
        topic:   str | None        # e.g. 'topic' or 'topic/subdata' or 'topic/subdata/subsubdata', etc... None means 'main' topic

    endpoints: list[Endpoint] | None

    host:      str | None
    port:      int | None
    base_path: str | None

    declared_fps:  float | None
    resource_path: str | None   # Path to a resource directory that is accessible for local file loading.

    auth_token:   str | None    # When set, require ?token= or Authorization: Bearer on all requests
    cors_origins: str | None    # Comma-separated allowed CORS origins (default: '*')


class REST(Filter):
    """Provide REST endpoint(s) and send incoming JSON data on down the filter pipeline. Can take individual parameters
    in config or most of them in `sources` as an 'http://...' specifier. Can take endpoint paths with placeholders for
    path parameters, e.g. '/path/{param1}/{param2}'.

    You can send a images directly as well as data to the endpoints if you send the data as 'multipart/form-data' with
    the image encoded as an 'image/jpeg', 'image/png', 'image/webp' or 'image/bpm'. In this case the data associated
    with the image can be sent in an optional 'metadata' field. Example using curl:

        curl -X POST http://localhost:8000 -F file=@./sample.png -F metadata='{"foo":"bar"}'

    If the image file is available locally to this filter then you can send the 'file' parameter as a path to this image
    file and it will be read from there instead of having to send it in the http request. In order to use this method,
    you MUST provide a `resource_path` in the config where the files will be read from (file path is relative to this).
    Example using curl:

        curl -X POST http://localhost:8000 -F file=./sample.png -F metadata='{"foo":"bar"}'

    config:
        sources:
            A single http:// source with the following format:
                http:// [[host][:port]] [/base/path] [; [(get|put|post|delete)] [sub/path] [> topic[/path]]]

            This specifies where the REST API will serve and the endpoints and methods used to access those endpoints.

        endpoints:
            You can pass the individual entpoints here in a list of Endpoint structures instead of in the `sources`
            parameter. This is mutually exclusive with specifying the endpoints in `sources`.

        host:
            If specifying via `endpoints`, you can specify the server host here.

        port:
            If specifying via `endpoints`, you can specify the server port here.

        base_path:
            If specifying via `endpoints`, you can specify the base path here.

        declared_fps:
            The default framerate for a stream of images being passed if images are being sent.

        resource_path:
            If passing images via a filename it will be relative to this path which MUST be provided in order to pass
            images in this manner.

        auth_token:
            When set, all requests must include ``?token=<value>`` or ``Authorization: Bearer <value>``.
            Returns 401 if missing or invalid. Also settable via ``FILTER_AUTH_TOKEN`` env var.

        cors_origins:
            Comma-separated list of allowed CORS origins. Defaults to ``'*'`` (allow all,
            credentials disabled). Set specific origins to enable ``Access-Control-Allow-Credentials``.
            Example: ``'https://portal.plainsight.tech,https://localhost:5173'``.
            Also settable via ``FILTER_CORS_ORIGINS`` env var.

    Example `sources`:
        Send everything that comes in GET or POST on http://0.0.0.0:8000/ to filter topic 'mytopic':
            'http://0.0.0.0:8000;>mytopic'

        Same, but on endpoint '/endpoint' and only GET to filter topic 'mytopic' data member 'mydata':
            'http://0.0.0.0:8000;(get)endpoint>mytopic/mydata'

        Same, but with '/endpoint/one' and 'endpoint/two' sent on to 'mytopic/one' and 'mytopic/two':
            'http://0.0.0.0:8000/endpoint;(get)one>mytopic/one;(get)two>mytopic/two'

        Same, but with POST or PUT instead of GET and also the 'two' endpoint getting a path var:
            'http://0.0.0.0:8000/endpoint;(put|post)one>mytopic/one;(put|post)two/{var}>mytopic/two'

    See also:
        * https://docs.google.com/document/d/1jNV-VGvobqYioeAYrvl4v-stQ7FZwoqldnOcS4GcbWM/edit#heading=h.gfyw8xufxquo
    """

    FILTER_TYPE   = 'Input'
    VALID_METHODS = ('GET', 'POST', 'PUT', 'DELETE')

    def create_app(self, config: RESTConfig) -> 'FastAPI':
        from fastapi import FastAPI, Request, status, HTTPException
        from openfilter.filter_runtime.filters.http_security import configure_http_security
        import json

        def multi_items_to_dict(items: list[tuple[str, str]]):
            dd = defaultdict(list)

            for key, val in items:
                dd[key].append(val)

            return {k: v if len(v) > 1 else v[0] for k, v in dd.items()}

        async def request_to_frame(request: Request, fields: list[str]):
            # The argument fields are only required to manipulate the data structure before initializing the Frame object.
            # If there will be additional blob validation here (so that it doesn't have to be done in Frame), fields could be moved back to closure->func.

            import time
            from starlette.datastructures import UploadFile as StarletteUploadFile

            FORMDATA_FIELD_FILE = 'file'
            FORMDATA_FIELD_METADATA = 'metadata'

            content_type = request.headers.get('Content-Type')
            file = None
            filename = None
            file_timestamp = time.time()

            if content_type is None or content_type.startswith('text/plain'):
                data = (await request.body()).decode()
            elif content_type.startswith('application/json'):
                data = await request.json()
            elif content_type.startswith('multipart/form-data') or content_type.startswith('application/x-www-form-urlencoded'):
                form = await request.form()
                if FORMDATA_FIELD_FILE in form:
                    form_file = form[FORMDATA_FIELD_FILE]
                    match form_file:
                        case StarletteUploadFile(): # We got a file content in the form.
                            filename = form_file.filename
                            file = form_file.file
                        case str(): # We got a path to the file.
                            if config.resource_path is not None:
                                form_file = os.path.normpath(os.path.join(config.resource_path, str(form_file)))
                                if os.path.commonpath([config.resource_path, form_file]) != config.resource_path or not os.path.isfile(form_file):
                                    raise HTTPException(status_code=400, detail="The provided image path is invalid - no resource available.")
                                try:
                                    file = open(form_file, 'rb')
                                    filename = form_file
                                except OSError:
                                    raise HTTPException(status_code=400, detail="Couldn't open the image resource.")
                            else:
                                raise HTTPException(status_code=400, detail="Local file loading not available. Check configuration.")
                        case _: # Should never be executed.
                            raise HTTPException(status_code=400, detail="The provided image form value is not valid. Expecting image file or path to a resource.")

                    if FORMDATA_FIELD_METADATA in form:
                        try:
                            data = form[FORMDATA_FIELD_METADATA]
                            # Validation only load.
                            json.loads(data)
                        except ValueError:
                            raise HTTPException(status_code=400, detail="The provided metadata is not a valid JSON value.")
                    else:
                        data = {}
                else:
                    data = {k: v for k, v in (await request.form()).items()}
            elif content_type.startswith('application/octet-stream'):
                data = await request.body()
            else:
                raise HTTPException(status_code=415, detail="Unsupported Media Type")

            # Strip auth/credential headers from frame data so secrets don't leak downstream
            from urllib.parse import urlencode
            _strip_headers = {'authorization', 'cookie', 'proxy-authorization'}
            headers = {k: v for k, v in request.headers.items() if k.lower() not in _strip_headers}
            query_params = [(k, v) for k, v in request.query_params.multi_items() if k.lower() != 'token']
            # Rebuild URL without the token query param
            clean_url = str(request.url).split('?')[0]
            if query_params:
                clean_url += '?' + urlencode(query_params)

            data = {
                'http': {
                    'method':       request.method,
                    'url':          clean_url,
                    'headers':      multi_items_to_dict(headers.items()),
                    'query_params': multi_items_to_dict(query_params),
                    'path_params':  request.path_params,
                    'client_host':  request.client.host,
                    'client_port':  request.client.port,
                },
                'data': data
            }

            for field in fields:
                data = {field: data}

            if file is None:
                frame = Frame(data)
            else:
                self.id = id = self.id + 1

                data['meta'] = {'id': id, 'ts': file_timestamp, 'src': filename, 'src_fps': config.declared_fps}
                try:
                    frame = Frame.from_blob(file.read(), data)

                    file.close()
                except ValueError as ve:
                    raise HTTPException(status_code=400, detail=str(ve))

            return frame

        app = FastAPI(title='REST')

        configure_http_security(app, auth_token=config.auth_token, cors_origins=config.cors_origins)

        app_methods = {'GET': app.get, 'POST': app.post, 'PUT': app.put, 'DELETE': app.delete}
        base_path   = f'/{bt}' if (bt := config.base_path) else ''

        for endpoint in config.endpoints or [dict(methods=('GET', 'POST'), topic='main')]:
            path           = f'{base_path}/{path}' if (path := endpoint.path) else base_path or '/'
            topic, *fields = endpoint.topic.split('/')

            fields.reverse()

            def closure(topic, fields):
                async def func(request: Request):
                    frame = await request_to_frame(request, fields)

                    try:
                        self.queue.put((topic, frame), False)
                    except Full:
                        logger.warning(f'queue full, discarding message')

                return func

            func = closure(topic, fields)

            for method in endpoint.methods:
                func = app_methods[method](path, status_code=status.HTTP_204_NO_CONTENT)(func)

        return app

    def serve(self, config: RESTConfig):
        import uvicorn

        uvicorn.Server(uvicorn.Config(
            self.create_app(config),
            host       = config.host or '0.0.0.0',
            port       = config.port or 8000,
            loop       = 'asyncio',
            log_config = None,
            log_level  = (os.getenv('LOG_LEVEL') or 'info').lower(),
        )).run()

    @classmethod
    def normalize_config(cls, config):
        sources = split_commas_maybe(config.get('sources'))  # we do not assume how Filter will normalize sources/outputs in the future
        config  = RESTConfig(super().normalize_config(dict_without(config, 'sources')))

        # Only env-var map params that don't overlap with sources URL parsing.
        # host/port/base_path come from the sources URL (or explicit endpoints
        # config) and would be silently overridden by source parsing below.
        env_mapping = {
            'declared_fps': float,
            'resource_path': str,
            'auth_token': str,
            'cors_origins': str,
        }
        for key, expected_type in env_mapping.items():
            env_val = os.getenv(f'FILTER_{key.upper()}')
            if env_val is not None:
                if expected_type is float:
                    setattr(config, key, float(env_val.strip()))
                else:
                    setattr(config, key, env_val.strip())

        if sources is not None:
            config.sources = sources

        if not config.outputs:
            raise ValueError('must specify at least one output')

        # parse sources

        if sources:
            if config.endpoints is not None:
                raise ValueError('can not have both sources and endpoints in config')
            if len(sources) != 1:
                raise ValueError('filter only takes a single source')
            if not (source := sources[0]).startswith('http://'):
                raise ValueError('filter only takes http:// source')

            source, *mappings = [s.strip() for s in source.split(';')]
            addr, *path       = source[7:].split('/', 1)

            if path and path[0]:
                config.base_path = path[0].rstrip('/')

            host, *port = addr.rsplit(':', 1)

            if host:
                config.host = host
            if port:
                config.port = int(port[0])

            del config.sources

            if not mappings:
                mappings = ['']

            config.endpoints = endpoints = []

            for mapping in mappings:
                path, *topic = [s.strip() for s in mapping.split('>', 1)]
                endpoint     = RESTConfig.Endpoint()

                if path.startswith('('):
                    methods, *path   = [s.strip() for s in path[1:].split(')', 1)]
                    path             = path[0] if path else ''
                    endpoint.methods = [s.strip() for s in methods.split('|')]

                if path:
                    endpoint.path = path
                if topic and (t0 := topic[0]):
                    endpoint.topic = t0

                endpoints.append(endpoint)

        # fill defaults and validate

        if base_path := config.base_path:
            if (sw := base_path.startswith('/')) + (ew := base_path.endswith('/')):
                config.base_path = base_path = base_path[sw : -ew] or None

        elif base_path is not None:
            config.base_path = base_path = None

        if config.endpoints:
            all_methods_n_paths = set()

            for endpoint in config.endpoints:
                endpoint.methods = methods = [method.upper() for method in (endpoint.get('methods') or ('GET', 'POST'))]

                if not (path := endpoint.path) or path == '/':
                    endpoint.path = path = None
                elif path.startswith('/'):
                    endpoint.path = path = path[1:]

                if not endpoint.topic:
                    endpoint.topic = 'main'

                if any((m := method) not in REST.VALID_METHODS for method in methods):
                    raise ValueError(f'invalid method {m!r} in endpoint {endpoint}')

                methods_n_paths = set(f'({method}){path}' for method in methods)

                if any((mnp := method_n_path) in all_methods_n_paths for method_n_path in methods_n_paths):
                    raise ValueError(f'duplicate method and path {mnp!r} in endpoint {endpoint}')

                all_methods_n_paths.update(methods_n_paths)

        config.declared_fps = DEFAULT_DECLARED_FPS if config.declared_fps is None else config.declared_fps

        if resource_path := config.resource_path:
            if not os.path.isdir(resource_path):
                raise ValueError(f'The resource directory path {config.resource_path} is invalid or the directory does not exist.')
            config.resource_path = os.path.abspath(resource_path)

        return config

    def setup(self, config):
        self.queue  = Queue(QUEUE_LEN)
        self.id     = -1  # frame id

        Thread(target=self.serve, args=(config,), daemon=True).start()

    def process(self, frames):
        try:
            topic, frame = self.queue.get(timeout=POLL_TIMEOUT_SEC)
        except Empty:
            return

        return {topic: frame}


if __name__ == '__main__':
    REST.run()
