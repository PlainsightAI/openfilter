import time
import uuid
import threading
import logging
import os
from datetime import datetime, timezone
from typing import Any

from dataclasses import make_dataclass, field

from openlineage.client.client import OpenLineageClient
from openlineage.client.transport.http import ApiKeyTokenProvider, HttpConfig, HttpTransport
from openlineage.client.facet import BaseFacet
from openlineage.client.run import RunEvent, RunState, Run, Job


def normalize_facet_keys(data: dict) -> dict:
    normalized = {}
    for k, v in data.items():
        k = k.lstrip("_")  
        if k and k[0].isupper():
            k = k[0].lower() + k[1:]  
        k = k.replace("-", "_").replace(" ", "_")  
        normalized[k] = v
    return normalized
def flatten_dict(d: dict, parent_key='', sep='_'):
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items

def create_openfilter_facet_with_fields(data: dict,filter_name:str) -> BaseFacet:
    data = normalize_facet_keys(data)
    data = flatten_dict(data)
    for k, v in data.items():
        if isinstance(v, (tuple, list)):
            data[k] = [str(x) for x in v]
        elif v is None:
            data[k] = ""

    fields = []
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            fields.append((k, type(v), field(default_factory=lambda v=v: v)))
        else:
            fields.append((k, type(v), field(default=v)))

    fields += [
        ("_producer", str, field(default="https://github.com/PlainsightAI/openfilter/tree/main/openfilter/lineage")),
        ("schemaURL", str, field(default="https://github.com/PlainsightAI/openfilter/blob/main/openfilter/lineage/schema/OpenFilterConfigRunFacet.json")),
        ("type", str, field(default=filter_name))
    ]
    
    DynamicFacet = make_dataclass("OpenFilterFacet", fields, bases=(BaseFacet,))
    return DynamicFacet().__dict__


def create_openlineage_job(name: str = None, facets: dict[Any, Any] = None, namespace: str = "Openfilter") -> Job:
    return Job(namespace=namespace, name=name, facets=facets)


def get_http_client(url: str=None, endpoint: str = None, verify: bool = False, api_key: str = None):
    try:
        if not url and not os.getenv("OPENLINEAGE_URL"):
            os.environ["OPENLINEAGE_DISABLED"] = "true"
            raise ValueError("\033[91mOPENLINEAGE_URL has not been defined — unable to create a HTTP openlineage client\033[0m")
       
        
        auth = ApiKeyTokenProvider({
            "apiKey": api_key or os.getenv("OPENLINEAGE_API_KEY")
        })

        http_config_args = {
            "url": os.getenv("OPENLINEAGE_URL") or url,
            "verify": bool(os.getenv("OPENLINEAGE_VERIFY_CLIENT_URL")) if os.getenv("OPENLINEAGE_VERIFY_CLIENT_URL") else verify,
            "auth": auth
        }
        
        final_endpoint = endpoint or os.getenv("OPENLINEAGE_ENDPOINT")
        if final_endpoint:
            http_config_args["endpoint"] = final_endpoint
        print(http_config_args)
        http_config = HttpConfig(**http_config_args)
        return OpenLineageClient(transport=HttpTransport(http_config))
    
    except Exception as e:
        logging.error(f"[OpenFilterLineage] Failed to get client: {e}")



class OpenFilterLineage:
    def __init__(self, client=None, producer="https://github.com/PlainsightAI/openfilter/tree/main/openfilter/lineage", interval=10, facets={}, filter_name: str = None, job=None):
        self.client = client or get_http_client()
        self.run_id = self.get_run_id()
        self.facets = facets
        self.job = job or create_openlineage_job()
        self.producer = os.getenv("OPENLINEAGE_PRODUCER") or producer
        self.interval = int(os.getenv("OPENLINEAGE__HEART__BEAT__INTERVAL") or interval)
        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self.filter_name = filter_name
        self._stop_event = threading.Event()
        self.filter_model = os.getenv(filter_name.upper() + "_MODEL_NAME") if filter_name else None

    def _emit_event(self, event_type, run=None, facets=None):
        try:
            if not os.getenv("OPENLINEAGE_DISABLED", "false").lower() in ("true", "1"):
                
                raw_data = self.facets if event_type == RunState.RUNNING else facets
                data_to_use = dict(raw_data or {})
                
                if(self.filter_model):
                    data_to_use["model_name"] = self.filter_model

                run_facets = {"openfilter": create_openfilter_facet_with_fields(data = data_to_use,filter_name=self.filter_name)}
                
                
                run_obj = run or Run(runId=self.run_id, facets=run_facets)

                event = RunEvent(
                    eventType=event_type,
                    eventTime=datetime.now(timezone.utc).isoformat(),
                    run=run_obj,
                    job=self.job,
                    producer=self.producer
                )

                self.client.emit(event)
               
        except Exception as e:
            logging.error(f"\033[93m[OpenFilterLineage] Failed to emit event {event_type}: {e}\033[0m")


    def _heartbeat_loop(self):
       
        if self.filter_model:
            self.facets["model_name"] = self.filter_model
        
        while not self._stop_event.is_set():
            with self._lock:
                self._emit_event(RunState.RUNNING)
            self._stop_event.wait(self.interval)
        self.emit_complete()

    def emit_start(self, facets):
        try:

            self.job.name = self.filter_name
            
            if(self.filter_model):
                facets["model_name"] = self.filter_model
            self._emit_event(event_type=RunState.START, facets=facets)
            logging.info(f"\033[92m[OpenFilterLineage] Starting sending events for: \033[94m{self.filter_name}\033[0m")


        except Exception as e:
            logging.error(f"\033[91m[OpenFilterLineage] Failed to emit event: {e}\033[0m")

    

    def emit_complete(self):
        self._emit_event(event_type=RunState.COMPLETE)

    def emit_stop(self):
        self._emit_event(event_type=RunState.ABORT)

    def start_lineage_heart_beat(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

    def stop_lineage_heart_beat(self):
        self._stop_event.set()
            

    def update_heartbeat_lineage(self, *, facets=None, job=None, producer=None):
        with self._lock:
            if facets:
                self.facets = facets
                
                if(self.filter_model):
                    self.facets["model_name"] = self.filter_model
            if job:
                self.job = job
            if producer:
                self.producer = producer

    def get_run_id(self):
        return str(uuid.uuid4())

