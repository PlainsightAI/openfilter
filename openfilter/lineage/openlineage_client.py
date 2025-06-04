from openlineage.client.client import OpenLineageClient
from openlineage.client import OpenLineageClient
from openlineage.client.transport.console import ConsoleConfig, ConsoleTransport
from openlineage.client.transport import Transport
from openlineage.client.serde import Serde
from openlineage.client.run import RunEvent, RunState, Run, Job
from datetime import datetime, timezone
from openlineage.client.transport.http import ApiKeyTokenProvider, HttpConfig, HttpTransport
import uuid
import time
from openlineage.client.facet import BaseFacet
import re
import threading

from datetime import datetime, timezone

from typing import Any
import os
from dotenv import load_dotenv
import logging
load_dotenv()
class OpenFilterLineage:
    def __init__(self, client=None, producer = "https://my-company.com/openlineage", interval=10, facets={}, filter_name:str=None, job=None):
        self.client = client or get_http_client()
        self.run_id = self.get_run_id()
        self.facets = facets
        self.job = job or create_openlineage_job()
        self.producer = producer or os.getenv("OPENFILTER_LINEAGE_PRODUCER")
        self.interval = int(os.getenv("OPENFILTER_LINEAGE_HEART_BEAT_INTERVAL") or interval)
        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self.filter_name = filter_name
        self.filter_model = self.filter_model = os.getenv(filter_name.upper() + "MODEL_NAME") if filter_name is not None else None
       
        
    def _emit_event(self, event_type, run=None,facets=None):
        try:
            data_to_use = self.facets if event_type == RunState.RUNNING else facets
            
           
            run_facets = self.create_dynamic_facets_from_dict(data_to_use) if data_to_use else data_to_use
         
            run_obj = run or Run(runId=self.get_run_id(), facets=run_facets)
        
            self.client.emit(RunEvent(
                eventType=event_type,
                eventTime=datetime.now(timezone.utc).isoformat(),
                run=run_obj,
                job=self.job,
                producer=self.producer
            ))
        except Exception as e:
            logging.error(f"[OpenFilterLineage] Failed to emit event {event_type}: {e}")

    def _heartbeat_loop(self):
        self.facets["filter_name"] = self.filter_name
        self.facets["model_name"] = self.filter_model
        while self._running:
            with self._lock:
                self._emit_event(RunState.RUNNING)
            
            time.sleep(self.interval)

        self.emit_complete()

    def emit_start(self, facets):
        
        self.job.name = self.filter_name
        facets["filter_name"] = self.filter_name
        facets["model_name"] = self.filter_model
        self._emit_event(event_type = RunState.START, facets=facets)

    def emit_complete(self):
        self._emit_event(event_type = RunState.COMPLETE)

    def emit_stop(self):
        self._emit_event(event_type = RunState.ABORT)

    def make_json_serializable(self,obj):
        if isinstance(obj, dict):
            return {k: self.make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple, set)):
            return [self.make_json_serializable(v) for v in obj]
        elif isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        elif hasattr(obj, '__dict__'):
            return self.make_json_serializable(vars(obj))
        else:
            return str(obj)  # Fallback: serializa como string
    
    def create_dynamic_facets_from_dict(self, data: dict) -> dict:
        def normalize_key(k: str) -> str:
            k = k.lstrip("_")  # remove underscores iniciais
            if k and k[0].isupper():
                k = k[0].lower() + k[1:]  # torna primeira letra minúscula
            return k

        def flatten_dict(d: dict, parent_key=""):
            items = {}
            for k, v in d.items():
                clean_key = normalize_key(k)
                new_key = f"{parent_key}__{clean_key}" if parent_key else clean_key
                if isinstance(v, dict):
                    items.update(flatten_dict(v, new_key))
                else:
                    items[new_key] = v
            return items

        flat_data = flatten_dict(data)
        
        return flat_data
    
    def start_lineage_heart_beat(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

    def stop_lineage_heart_beat(self):
        self._running = False
        if self._thread:
            self._thread.join()

    def update_heartbeat_lineage(self, *, facets=None, job=None, producer=None):
       
        with self._lock:
           
            self.run_id = self.run_id
            if facets:
                
                self.facets = facets
                self.facets['filter_name'] = self.filter_name
                self.facets["model_name"] = self.filter_model
            if job:
                self.job = job
            if producer:
                self.producer = producer

    def get_run_id(self):
        return str(uuid.uuid4())

def create_openlineage_job(name: str = None, facets: dict[Any, Any] = None,namespace: str = "Openfilter") -> Job:
       
    return Job(namespace=namespace, name=name, facets=facets)

def get_http_client(url: str = "http://localhost:5000", endpoint: str = None, verify: bool = False, api_key: str = None):
    try:
        auth = ApiKeyTokenProvider({
            "apiKey": api_key or os.getenv("HTTP_LINEAGE_CLIENT_APIKEY")
        })

        http_config_args = {
            "url": os.getenv("HTTP_LINEAGE_CLIENT_URL") or url,
            "verify": bool(os.getenv("HTTP_LINEAGE_VERIFY_CLIENT_URL")) if bool(os.getenv("HTTP_LINEAGE_VERIFY_CLIENT_URL")) is not None else verify,
            "auth": auth
        }

       
        final_endpoint = endpoint or os.getenv("HTTP_LINEAGE_CLIENT_ENDPOINT_URL")
        if final_endpoint:
            http_config_args["endpoint"] = final_endpoint

        http_config = HttpConfig(**http_config_args)

        return OpenLineageClient(transport=HttpTransport(http_config))

    except Exception as e:
        logging.error(f"[OpenFilterLineage] Failed to get client {e}:")


def get_console_client():
    return OpenLineageClient(transport=ConsoleTransport(ConsoleConfig()))




