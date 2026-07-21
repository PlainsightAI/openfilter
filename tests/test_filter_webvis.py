#!/usr/bin/env python

import logging
import os
import unittest
from time import sleep
from unittest.mock import patch



from openfilter.filter_runtime import Filter
from openfilter.filter_runtime.utils import setLogLevelGlobal
from openfilter.filter_runtime.filters.webvis import Webvis, WebvisConfig


logger = logging.getLogger(__name__)

log_level = int(getattr(logging, (os.getenv('LOG_LEVEL') or 'CRITICAL').upper()))

setLogLevelGlobal(log_level)

class TestWebvisConfig(unittest.TestCase):
    """Test the WebvisConfig class."""
    def test_normalize_config_basic(self):
        config = {
            'sources': 'tcp://localhost:5550'
        }
        normalized = Webvis.normalize_config(config)
        print(normalized)
        self.assertIsInstance(normalized, WebvisConfig)
        self.assertIsInstance(normalized.enable_json, bool)
        self.assertIsInstance(normalized.sleep_interval, float)
        assert True

    def test_default_config(self):
        config = WebvisConfig()
        self.assertFalse(config.enable_json)
        self.assertEqual(config.sleep_interval, 1.0)

    def test_enable_json(self):
        config = {
            'sources': 'tcp://localhost:5550',
            'enable_json': 'true'
        }
        normalized = Webvis.normalize_config(config)
        self.assertTrue(normalized.enable_json)

    def test_set_interval(self):
        config = {
            'sources': 'tcp://localhost:5550',
            'sleep_interval': 0.2
        }
        normalized = Webvis.normalize_config(config)
        self.assertFalse(normalized.enable_json)
        self.assertEqual(normalized.sleep_interval, 0.2)

    def test_auth_token_config_param(self):
        config = {
            'sources': 'tcp://localhost:5550',
            'auth_token': 'my-secret',
        }
        normalized = Webvis.normalize_config(config)
        self.assertEqual(normalized.auth_token, 'my-secret')

    def test_cors_origins_config_param(self):
        config = {
            'sources': 'tcp://localhost:5550',
            'cors_origins': 'https://portal.plainsight.tech',
        }
        normalized = Webvis.normalize_config(config)
        self.assertEqual(normalized.cors_origins, 'https://portal.plainsight.tech')

    def test_auth_token_default_none(self):
        config = {
            'sources': 'tcp://localhost:5550',
        }
        normalized = Webvis.normalize_config(config)
        self.assertIsNone(normalized.auth_token)

    def test_cors_origins_default_none(self):
        config = {
            'sources': 'tcp://localhost:5550',
        }
        normalized = Webvis.normalize_config(config)
        self.assertIsNone(normalized.cors_origins)

    def test_auth_token_from_env_var(self):
        with patch.dict(os.environ, {'FILTER_AUTH_TOKEN': 'env-token'}):
            config = {'sources': 'tcp://localhost:5550'}
            normalized = Webvis.normalize_config(config)
            self.assertEqual(normalized.auth_token, 'env-token')

    def test_cors_origins_from_env_var(self):
        with patch.dict(os.environ, {'FILTER_CORS_ORIGINS': 'https://a.com,https://b.com'}):
            config = {'sources': 'tcp://localhost:5550'}
            normalized = Webvis.normalize_config(config)
            self.assertEqual(normalized.cors_origins, 'https://a.com,https://b.com')

    def test_access_log_default_false(self):
        config = {'sources': 'tcp://localhost:5550'}
        normalized = Webvis.normalize_config(config)
        self.assertFalse(normalized.access_log)

    def test_access_log_from_env_var(self):
        with patch.dict(os.environ, {'FILTER_ACCESS_LOG': 'true'}):
            config = {'sources': 'tcp://localhost:5550'}
            normalized = Webvis.normalize_config(config)
            self.assertTrue(normalized.access_log)

    def test_enable_snapshot_payload_default_false(self):
        config = {'sources': 'tcp://localhost:5550'}
        normalized = Webvis.normalize_config(config)
        self.assertFalse(normalized.enable_snapshot_payload)

    def test_enable_snapshot_payload_from_env_var(self):
        with patch.dict(os.environ, {'FILTER_ENABLE_SNAPSHOT_PAYLOAD': 'true'}):
            config = {'sources': 'tcp://localhost:5550'}
            normalized = Webvis.normalize_config(config)
            self.assertTrue(normalized.enable_snapshot_payload)


class TestWebvisCreateApp(unittest.TestCase):
    """Test the Webvis.create_app() method."""

    def _make_webvis(self):
        webvis = object.__new__(Webvis)
        webvis.streams = {}
        webvis.enable_json = False
        webvis.sleep_interval = 1.0
        webvis.current_data = {}
        webvis.latest_frames = {}
        webvis.configured_topics = set()
        webvis.is_multi_topic_static = False
        return webvis

    def test_create_app_returns_fastapi(self):
        from fastapi import FastAPI
        webvis = self._make_webvis()
        app = webvis.create_app()
        self.assertIsInstance(app, FastAPI)

    def test_create_app_with_auth_rejects_unauthenticated(self):
        from fastapi.testclient import TestClient
        webvis = self._make_webvis()
        app = webvis.create_app(auth_token='secret')
        client = TestClient(app)
        response = client.get('/')
        self.assertEqual(response.status_code, 401)

    def test_create_app_without_auth_does_not_reject(self):
        from fastapi import FastAPI
        webvis = self._make_webvis()
        app = webvis.create_app()
        # Without auth, app should have middleware but not reject
        self.assertIsInstance(app, FastAPI)
        self.assertTrue(len(app.user_middleware) >= 1)

    def test_create_app_with_cors_origins(self):
        from fastapi.testclient import TestClient
        webvis = self._make_webvis()
        app = webvis.create_app(cors_origins='https://portal.plainsight.tech')
        client = TestClient(app)
        response = client.options('/', headers={
            'Origin': 'https://portal.plainsight.tech',
            'Access-Control-Request-Method': 'GET',
        })
        self.assertEqual(
            response.headers.get('access-control-allow-origin'),
            'https://portal.plainsight.tech',
        )

    def test_get_data_with_multiple_topics(self):
        import asyncio
        import json
        from queue import Queue
        
        webvis = self._make_webvis()
        # Setup multi-topic streams and their current_data
        webvis.streams = {"front": Queue(), "back": Queue()}
        webvis.current_data = {
            "front": {"camera": "front", "detected": ["person"]},
            "back": {"camera": "back", "detected": ["car"]}
        }
        webvis.enable_json = True
        webvis.sleep_interval = 0.01  # small interval for test speed
        
        app = webvis.create_app()
        
        # Find the route endpoints
        default_route = next(r for r in app.routes if r.path == "/data")
        topic_route = next(r for r in app.routes if r.path == "/{topic:str}/data")
        
        get_data_default_endpoint = default_route.endpoint
        get_data_topic_endpoint = topic_route.endpoint
        
        def parse_sse_chunk(chunk):
            payload_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            if payload_str.startswith("data: "):
                payload_str = payload_str[6:]
            return json.loads(payload_str.strip())

        # Setup multi-topic streams where 'main' is actually present in streams
        webvis_with_main = self._make_webvis()
        webvis_with_main.streams = {"main": Queue(), "front": Queue()}
        webvis_with_main.current_data = {
            "main": {"camera": "main", "detected": ["person"]},
            "front": {"camera": "front", "detected": ["car"]}
        }
        webvis_with_main.enable_json = True
        webvis_with_main.sleep_interval = 0.01
        
        app_with_main = webvis_with_main.create_app()
        topic_route_with_main = next(r for r in app_with_main.routes if r.path == "/{topic:str}/data")
        get_data_topic_endpoint_with_main = topic_route_with_main.endpoint

        # Run async test
        async def run_test():
            # Test default topic /data (combined view of both 'front' and 'back')
            response = await get_data_default_endpoint()
            iterator = response.body_iterator
            first_chunk = await iterator.__anext__()
            payload = parse_sse_chunk(first_chunk)
            self.assertEqual(payload, {
                "front": {"camera": "front", "detected": ["person"]},
                "back": {"camera": "back", "detected": ["car"]}
            })
            
            # Test explicit 'main' topic /main/data (combined view since 'main' is not in streams)
            response_main = await get_data_topic_endpoint(topic="main")
            iterator_main = response_main.body_iterator
            main_chunk = await iterator_main.__anext__()
            payload_main = parse_sse_chunk(main_chunk)
            self.assertEqual(payload_main, {
                "front": {"camera": "front", "detected": ["person"]},
                "back": {"camera": "back", "detected": ["car"]}
            })
            
            # Test "back" topic explicitly
            response_back = await get_data_topic_endpoint(topic="back")
            iterator_back = response_back.body_iterator
            back_chunk = await iterator_back.__anext__()
            payload_back = parse_sse_chunk(back_chunk)
            self.assertEqual(payload_back, {"camera": "back", "detected": ["car"]})

            # Test 'main' topic when 'main' is actually in streams (should return ONLY 'main' data, not combined)
            response_main_exists = await get_data_topic_endpoint_with_main(topic="main")
            iterator_main_exists = response_main_exists.body_iterator
            chunk_main_exists = await iterator_main_exists.__anext__()
            payload_main_exists = parse_sse_chunk(chunk_main_exists)
            self.assertEqual(payload_main_exists, {"camera": "main", "detected": ["person"]})

        asyncio.run(run_test())

    def test_route_registration_order(self):
        from starlette.routing import Match
        webvis = self._make_webvis()
        app = webvis.create_app()
        
        # Verify that GET /data matches get_data_default endpoint rather than image catch-all
        scope_data = {'type': 'http', 'method': 'GET', 'path': '/data'}
        matching_route_data = None
        for route in app.routes:
            match, _ = route.matches(scope_data)
            if match == Match.FULL:
                matching_route_data = route
                break
        
        self.assertIsNotNone(matching_route_data)
        self.assertEqual(matching_route_data.path, '/data')
        self.assertEqual(matching_route_data.endpoint.__name__, 'get_data_default')

        # Verify that GET /front/data matches get_data endpoint rather than image catch-all
        scope_topic_data = {'type': 'http', 'method': 'GET', 'path': '/front/data'}
        matching_route_topic_data = None
        for route in app.routes:
            match, _ = route.matches(scope_topic_data)
            if match == Match.FULL:
                matching_route_topic_data = route
                break
                
        self.assertIsNotNone(matching_route_topic_data)
        self.assertEqual(matching_route_topic_data.path, '/{topic:str}/data')
        self.assertEqual(matching_route_topic_data.endpoint.__name__, 'get_data')

    def test_get_data_with_single_topic_main(self):
        import asyncio
        import json
        from queue import Queue
        
        webvis = self._make_webvis()
        # Setup single-topic stream named 'main'
        webvis.streams = {"main": Queue()}
        webvis.current_data = {
            "main": {"camera": "main", "detected": ["person"]}
        }
        webvis.enable_json = True
        webvis.sleep_interval = 0.01
        
        app = webvis.create_app()
        default_route = next(r for r in app.routes if r.path == "/data")
        get_data_default_endpoint = default_route.endpoint
        
        async def run_test():
            # For a single 'main' topic, /data should return the flat dict (backwards compatibility)
            response = await get_data_default_endpoint()
            iterator = response.body_iterator
            chunk = await iterator.__anext__()
            
            payload_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            if payload_str.startswith("data: "):
                payload_str = payload_str[6:]
            payload = json.loads(payload_str.strip())
            
            self.assertEqual(payload, {"camera": "main", "detected": ["person"]})

        asyncio.run(run_test())

    def test_get_data_with_single_topic_non_main(self):
        import asyncio
        import json
        from queue import Queue
        
        webvis = self._make_webvis()
        # Setup single-topic stream named 'front' (no 'main')
        webvis.streams = {"front": Queue()}
        webvis.current_data = {
            "front": {"camera": "front", "detected": ["person"]}
        }
        webvis.enable_json = True
        webvis.sleep_interval = 0.01
        
        app = webvis.create_app()
        default_route = next(r for r in app.routes if r.path == "/data")
        get_data_default_endpoint = default_route.endpoint
        
        async def run_test():
            # For a single non-'main' topic, /data should also return the flat dict (backwards compatibility)
            response = await get_data_default_endpoint()
            iterator = response.body_iterator
            chunk = await iterator.__anext__()
            
            payload_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            if payload_str.startswith("data: "):
                payload_str = payload_str[6:]
            payload = json.loads(payload_str.strip())
            
            self.assertEqual(payload, {"camera": "front", "detected": ["person"]})

        asyncio.run(run_test())

    def test_get_data_schema_stability(self):
        import asyncio
        import json
        from queue import Queue
        
        webvis = self._make_webvis()
        # Statically configure multiple topics to test configuration-based multi-topic detection
        webvis.configured_topics = {"front", "back"}
        webvis.is_multi_topic_static = True
        webvis.current_data = {
            "front": {"camera": "front", "detected": ["person"]}
        }
        webvis.enable_json = True
        webvis.sleep_interval = 0.01
        
        app = webvis.create_app()
        default_route = next(r for r in app.routes if r.path == "/data")
        get_data_default_endpoint = default_route.endpoint

        def parse_sse_chunk(chunk):
            payload_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            if payload_str.startswith("data: "):
                payload_str = payload_str[6:]
            return json.loads(payload_str.strip())

        async def run_test():
            # 1. Even though only 1 topic exists in current_data, it is configured for multi-topic,
            # so it should immediately serve the combined view.
            response1 = await get_data_default_endpoint()
            iterator1 = response1.body_iterator
            chunk1 = await iterator1.__anext__()
            self.assertEqual(parse_sse_chunk(chunk1), {
                "front": {"camera": "front", "detected": ["person"]}
            })

            # 2. Test schema lock-on-connection (no flipping mid-stream).
            # If we start a connection in flat mode:
            webvis_single = self._make_webvis()
            webvis_single.current_data = {
                "front": {"camera": "front", "detected": ["person"]}
            }
            webvis_single.enable_json = True
            webvis_single.sleep_interval = 0.01
            app_single = webvis_single.create_app()
            get_data_endpoint_single = next(r for r in app_single.routes if r.path == "/data").endpoint

            response_single = await get_data_endpoint_single()
            iterator_single = response_single.body_iterator

            # First chunk is flat
            chunk_f = await iterator_single.__anext__()
            self.assertEqual(parse_sse_chunk(chunk_f), {"camera": "front", "detected": ["person"]})

            # Now add a second topic's data mid-stream
            webvis_single.current_data["back"] = {"camera": "back", "detected": ["car"]}

            # Second chunk from the SAME connection should still be flat (schema locked to flat)
            chunk_s = await iterator_single.__anext__()
            self.assertEqual(parse_sse_chunk(chunk_s), {"camera": "front", "detected": ["person"]})

            # But a NEW connection should see the combined schema
            response_new = await get_data_endpoint_single()
            iterator_new = response_new.body_iterator
            chunk_new = await iterator_new.__anext__()
            self.assertEqual(parse_sse_chunk(chunk_new), {
                "front": {"camera": "front", "detected": ["person"]},
                "back": {"camera": "back", "detected": ["car"]}
            })

            # 3. Test that image request (mutating self.streams via setdefault) does NOT pollute or flip the schema.
            webvis_single_clean = self._make_webvis()
            webvis_single_clean.current_data = {
                "front": {"camera": "front", "detected": ["person"]}
            }
            webvis_single_clean.enable_json = True
            webvis_single_clean.sleep_interval = 0.01
            app_clean = webvis_single_clean.create_app()

            # Trigger an image wildcard route matching (mutates webvis.streams)
            image_endpoint = next(r for r in app_clean.routes if r.path == "/{topic:str}").endpoint
            image_endpoint(topic="foo") # Creates Queue in streams for 'foo'

            # Verify that webvis.streams now has 'foo'
            self.assertIn("foo", webvis_single_clean.streams)

            # Get data default should still be flat (since len(current_data) is 1 and not statically configured for multi-topic)
            get_data_clean = next(r for r in app_clean.routes if r.path == "/data").endpoint
            response_clean = await get_data_clean()
            iterator_clean = response_clean.body_iterator
            chunk_clean = await iterator_clean.__anext__()
            self.assertEqual(parse_sse_chunk(chunk_clean), {"camera": "front", "detected": ["person"]})

        asyncio.run(run_test())


class TestWebvisNewEndpoints(unittest.TestCase):
    """Test the newly added endpoints: snapshot-payload."""

    def _make_webvis(self, enable_snapshot_payload=True):
        webvis = object.__new__(Webvis)
        webvis.streams = {}
        webvis.enable_json = False
        webvis.sleep_interval = 1.0
        webvis.current_data = {}
        webvis.latest_frames = {}
        webvis.configured_topics = set()
        webvis.is_multi_topic_static = False
        webvis.enable_snapshot_payload = enable_snapshot_payload
        return webvis

    def test_disabled_by_default(self):
        # When enable_snapshot_payload is False (default), the routes should not be registered.
        # We check app.routes directly to avoid making requests that would hit the catch-all stream and hang.
        webvis = self._make_webvis(enable_snapshot_payload=False)
        app = webvis.create_app()
        paths = [r.path for r in app.routes]
        self.assertNotIn('/snapshot-payload', paths)
        self.assertNotIn('/{topic:str}/snapshot-payload', paths)

    def test_endpoints_404_when_no_frame(self):
        from fastapi.testclient import TestClient
        webvis = self._make_webvis(enable_snapshot_payload=True)
        app = webvis.create_app()
        client = TestClient(app)

        # GET /snapshot-payload -> 404
        res = client.get('/snapshot-payload')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.content, b"No frame available")

    def test_endpoints_with_single_topic_frame(self):
        import numpy as np
        import base64
        import json
        from fastapi.testclient import TestClient
        from openfilter.filter_runtime.frame import Frame

        webvis = self._make_webvis(enable_snapshot_payload=True)
        
        # Create a dummy frame and populate latest_frames / current_data
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        frame = Frame(image=image, data={"camera": "main", "detections": []}, format="BGR")
        
        webvis.latest_frames = {"main": frame}
        webvis.current_data = {"main": frame.data}

        app = webvis.create_app()
        client = TestClient(app)

        # GET /snapshot-payload -> 200, returns JSON
        res = client.get('/snapshot-payload')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "application/json")
        
        body = res.json()
        self.assertEqual(body["topic"], "main")
        self.assertIn("timestamp", body)
        self.assertEqual(body["width"], 160)
        self.assertEqual(body["height"], 120)
        self.assertEqual(body["format"], "BGR")
        self.assertEqual(body["metadata"], {"camera": "main", "detections": []})
        
        # Decode base64 image and check content
        img_bytes = base64.b64decode(body["image"])
        self.assertEqual(img_bytes, bytes(frame.bgr.jpg))

    def test_endpoints_with_multi_topic_frames(self):
        import numpy as np
        import base64
        import json
        from fastapi.testclient import TestClient
        from openfilter.filter_runtime.frame import Frame

        webvis = self._make_webvis(enable_snapshot_payload=True)
        webvis.is_multi_topic_static = True

        image_front = np.zeros((100, 150, 3), dtype=np.uint8)
        frame_front = Frame(image=image_front, data={"camera": "front"}, format="BGR")

        image_back = np.zeros((200, 300, 3), dtype=np.uint8)
        frame_back = Frame(image=image_back, data={"camera": "back"}, format="BGR")

        webvis.latest_frames = {"front": frame_front, "back": frame_back}
        webvis.current_data = {"front": frame_front.data, "back": frame_back.data}

        app = webvis.create_app()
        client = TestClient(app)

        # 1. GET /snapshot-payload (default) -> resolves to 'front' (the first key), returns front's snapshot and combined metadata
        res = client.get('/snapshot-payload')
        self.assertEqual(res.status_code, 200)
        
        body = res.json()
        self.assertEqual(body["topic"], "front")
        self.assertEqual(body["width"], 150)
        self.assertEqual(body["height"], 100)
        self.assertEqual(body["metadata"], {
            "front": {"camera": "front"},
            "back": {"camera": "back"}
        })
        img_bytes = base64.b64decode(body["image"])
        self.assertEqual(img_bytes, bytes(frame_front.bgr.jpg))

        # 2. GET /back/snapshot-payload -> returns back's snapshot and back's flat metadata
        res = client.get('/back/snapshot-payload')
        self.assertEqual(res.status_code, 200)
        
        body = res.json()
        self.assertEqual(body["topic"], "back")
        self.assertEqual(body["width"], 300)
        self.assertEqual(body["height"], 200)
        self.assertEqual(body["metadata"], {"camera": "back"})
        img_bytes = base64.b64decode(body["image"])
        self.assertEqual(img_bytes, bytes(frame_back.bgr.jpg))

    def test_endpoints_with_special_characters_topic(self):
        import numpy as np
        import urllib.parse
        from fastapi.testclient import TestClient
        from openfilter.filter_runtime.frame import Frame

        webvis = self._make_webvis(enable_snapshot_payload=True)
        
        image = np.zeros((100, 150, 3), dtype=np.uint8)
        # Topic containing space and carriage return/line feed characters
        special_topic = "cam_front\r\nspace"
        frame = Frame(image=image, data={"camera": "special"}, format="BGR")

        webvis.latest_frames = {special_topic: frame}
        webvis.current_data = {special_topic: frame.data}

        app = webvis.create_app()
        client = TestClient(app)

        # GET snapshot-payload using URL-encoded topic path
        encoded_path = urllib.parse.quote(special_topic)
        res = client.get(f'/{encoded_path}/snapshot-payload')
        self.assertEqual(res.status_code, 200)
        
        body = res.json()
        self.assertEqual(body["topic"], special_topic)

    def test_endpoints_with_non_json_serializable_metadata(self):
        import numpy as np
        from fastapi.testclient import TestClient
        from openfilter.filter_runtime.frame import Frame

        webvis = self._make_webvis(enable_snapshot_payload=True)
        
        # Create a dummy frame and populate latest_frames / current_data with non-JSON-serializable types
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        frame = Frame(
            image=image,
            data={
                "camera": "main",
                "count": np.int64(5),
                "box": np.array([1, 2, 3]),
            },
            format="BGR"
        )
        
        webvis.latest_frames = {"main": frame}
        webvis.current_data = {"main": frame.data}

        app = webvis.create_app()
        client = TestClient(app)

        # GET /snapshot-payload -> 200, returns JSON with gracefully handled metadata
        res = client.get('/snapshot-payload')
        self.assertEqual(res.status_code, 200)
        
        body = res.json()
        self.assertEqual(body["metadata"]["count"], "5")
        self.assertEqual(body["metadata"]["box"], "[1 2 3]")

    def test_concurrent_process_and_read(self):
        import numpy as np
        from threading import Thread, RLock
        from openfilter.filter_runtime.frame import Frame
        from fastapi.testclient import TestClient

        webvis = self._make_webvis(enable_snapshot_payload=True)
        webvis._lock = RLock()
        webvis.streams = {}
        webvis.current_data = {}
        webvis.latest_frames = {}
        webvis.is_multi_topic_static = False

        app = webvis.create_app()
        client = TestClient(app)

        stop_threads = False
        errors = []

        def writer_thread():
            try:
                image = np.zeros((10, 10, 3), dtype=np.uint8)
                i = 0
                while not stop_threads:
                    topic = f"cam_{i % 10}"
                    frame = Frame(image=image, data={f"key_{i}": i}, format="BGR")
                    webvis.process({topic: frame})
                    i += 1
                    if i % 50 == 0:
                        with webvis._lock:
                            webvis.current_data.clear()
                            webvis.latest_frames.clear()
            except Exception as e:
                errors.append(e)

        def reader_thread():
            try:
                while not stop_threads:
                    res2 = client.get('/snapshot-payload')
                    self.assertIn(res2.status_code, [200, 404])
            except Exception as e:
                errors.append(e)

        t1 = Thread(target=writer_thread)
        t2 = Thread(target=reader_thread)

        t1.start()
        t2.start()

        # Bounded poll/sleep
        for _ in range(50):
            if errors:
                break
            sleep(0.01)
        stop_threads = True

        t1.join()
        t2.join()

        self.assertEqual(errors, [])

    def test_endpoints_with_failed_jpeg_encoding(self):
        import numpy as np
        from fastapi.testclient import TestClient
        from openfilter.filter_runtime.frame import Frame
        from unittest.mock import PropertyMock, patch

        webvis = self._make_webvis(enable_snapshot_payload=True)
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        frame = Frame(image=image, data={"camera": "main"}, format="BGR")
        
        webvis.latest_frames = {"main": frame}
        webvis.current_data = {"main": frame.data}

        app = webvis.create_app()
        client = TestClient(app)

        # Patch the .jpg property of the frame's bgr representation to raise RuntimeError
        with patch.object(frame.bgr.__class__, 'jpg', new_callable=PropertyMock) as mock_jpg:
            mock_jpg.side_effect = RuntimeError("jpg encoding failed")

            # GET /snapshot-payload -> should return 500
            res = client.get('/snapshot-payload')
            self.assertEqual(res.status_code, 500)
            self.assertEqual(res.content, b"JPEG encoding failed")

    def test_endpoints_with_failed_jpeg_encoding_generic_exception(self):
        import numpy as np
        from fastapi.testclient import TestClient
        from openfilter.filter_runtime.frame import Frame
        from unittest.mock import PropertyMock, patch

        webvis = self._make_webvis(enable_snapshot_payload=True)
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        frame = Frame(image=image, data={"camera": "main"}, format="BGR")
        
        webvis.latest_frames = {"main": frame}
        webvis.current_data = {"main": frame.data}

        app = webvis.create_app()
        client = TestClient(app)

        # Patch the .jpg property to raise a non-RuntimeError Exception
        with patch.object(frame.bgr.__class__, 'jpg', new_callable=PropertyMock) as mock_jpg:
            mock_jpg.side_effect = Exception("generic opencv or other encoding failure")

            # GET /snapshot-payload -> should return 500
            res = client.get('/snapshot-payload')
            self.assertEqual(res.status_code, 500)
            self.assertEqual(res.content, b"JPEG encoding failed")

if __name__ == '__main__':
    unittest.main()
