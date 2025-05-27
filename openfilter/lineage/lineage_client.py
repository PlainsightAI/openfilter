# lineage_client.py
from openlineage.client.run import RunEvent, RunState
from openlineage.client.facet import NominalTimeRunFacet, RunFacet
from datetime import datetime
import uuid


class LineageClient:
    def __init__(self, transport, job_name: str, namespace: str, producer: str):
        self.transport = transport
        self.job_name = job_name
        self.namespace = namespace
        self.producer = producer
        self.run_id = str(uuid.uuid4())

    def emit_start(self, model_info: dict = None, additional_facets: dict = None):
        facets = {
            "nominalTime": NominalTimeRunFacet(
                nominalStartTime=datetime.utcnow().isoformat() + "Z"
            )
        }

        if model_info:
            facets["model"] = RunFacet._from_dict({
                "schema": "https://example.com/facets/model",
                "data": model_info
            })

        if additional_facets:
            facets.update(additional_facets)

        event = RunEvent(
            eventType=RunState.START,
            eventTime=datetime.utcnow().isoformat() + "Z",
            run={"runId": self.run_id, "facets": facets},
            job={"namespace": self.namespace, "name": self.job_name},
            producer=self.producer
        )
        self.transport.emit(event)

    def emit_heartbeat(self, additional_facets: dict = None):
        facets = {
            "heartbeat": RunFacet._from_dict({
                "schema": "https://example.com/facets/heartbeat",
                "data": {"status": "alive", "timestamp": datetime.utcnow().isoformat()}
            })
        }

        if additional_facets:
            facets.update(additional_facets)

        event = RunEvent(
            eventType=RunState.RUNNING,
            eventTime=datetime.utcnow().isoformat() + "Z",
            run={"runId": self.run_id, "facets": facets},
            job={"namespace": self.namespace, "name": self.job_name},
            producer=self.producer
        )
        self.transport.emit(event)

    def emit_complete(self, metrics: dict = None, additional_facets: dict = None):
        facets = {}
        if metrics:
            facets["metrics"] = RunFacet._from_dict({
                "schema": "https://example.com/facets/metrics",
                "data": metrics
            })

        if additional_facets:
            facets.update(additional_facets)

        event = RunEvent(
            eventType=RunState.COMPLETE,
            eventTime=datetime.utcnow().isoformat() + "Z",
            run={"runId": self.run_id, "facets": facets},
            job={"namespace": self.namespace, "name": self.job_name},
            producer=self.producer
        )
        self.transport.emit(event)

    def emit_fail(self, error_info: dict = None):
        facets = {}
        if error_info:
            facets["error"] = RunFacet._from_dict({
                "schema": "https://example.com/facets/error",
                "data": error_info
            })

        event = RunEvent(
            eventType=RunState.FAIL,
            eventTime=datetime.utcnow().isoformat() + "Z",
            run={"runId": self.run_id, "facets": facets},
            job={"namespace": self.namespace, "name": self.job_name},
            producer=self.producer
        )
        self.transport.emit(event)
