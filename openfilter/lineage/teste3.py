from openlineage.client.client import OpenLineageClient, OpenLineageClientOptions
from openlineage.client.transport import Transport
from openlineage.client.serde import Serde
from openlineage.client.run import RunEvent, RunState, Run, Job
from datetime import datetime, timezone
from sqlalchemy import create_engine, Table, Column, Integer, Text, MetaData, DateTime
from sqlalchemy.sql import func
from kafka import KafkaProducer
import uuid
import json
import time

#kafka-python
# Console transport
class ConsoleTransport(Transport):
    def emit(self, event):
        print(f"\n>>> Emitted event ({event.eventType}):")
        print(json.dumps(Serde.to_dict(event), indent=2))


# Kafka transport
class KafkaTransport(Transport):
    def __init__(self, bootstrap_servers, topic):
        self.producer = KafkaProducer(bootstrap_servers=bootstrap_servers)
        self.topic = topic

    def emit(self, event):
        data = json.dumps(Serde.to_dict(event)).encode('utf-8')
        self.producer.send(self.topic, data)
        self.producer.flush()


# SQL transport
class SQLTransport(Transport):
    def __init__(self, db_url, table_name="openlineage_events"):
        self.engine = create_engine(db_url)
        self.table_name = table_name
        self.metadata = MetaData()

        self.events_table = Table(
            table_name, self.metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('event_type', Text, nullable=False),
            Column('event_time', DateTime(timezone=True), nullable=False),
            Column('event_data', Text, nullable=False),
            Column('created_at', DateTime(timezone=True), server_default=func.now())
        )

        self.metadata.create_all(self.engine)

    def emit(self, event):
        event_dict = Serde.to_dict(event)
        event_json = json.dumps(event_dict)
        event_type = event.eventType
        event_time_str = event.eventTime
        event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))

        with self.engine.connect() as conn:
            insert_stmt = self.events_table.insert().values(
                event_type=event_type,
                event_time=event_time,
                event_data=event_json,
            )
            conn.execute(insert_stmt)
            conn.commit()


# Client factory
def get_client(mode="console", url=None, api_key=None, kafka_bootstrap_servers=None, kafka_topic=None, db_url=None):
    if mode == "console":
        return OpenLineageClient(transport=ConsoleTransport())
    elif mode == "http":
        if not url:
            raise ValueError("URL is required for HTTP mode")
        options = OpenLineageClientOptions(api_key=api_key) if api_key else None
        return OpenLineageClient(url=url, options=options)
    elif mode == "kafka":
        if not kafka_bootstrap_servers or not kafka_topic:
            raise ValueError("Kafka bootstrap_servers and topic are required for Kafka mode")
        return OpenLineageClient(transport=KafkaTransport(kafka_bootstrap_servers, kafka_topic))
    elif mode == "sql":
        if not db_url:
            raise ValueError("Database URL is required for SQL mode")
        return OpenLineageClient(transport=SQLTransport(db_url))
    else:
        raise ValueError(f"Mode '{mode}' not supported.")


# Emit individual events
def emit_start(client, run_id, job, producer):
    client.emit(RunEvent(
        eventType=RunState.START,
        eventTime=datetime.now(timezone.utc).isoformat(),
        run=Run(runId=run_id),
        job=job,
        producer=producer
    ))

def emit_heartbeat(*,client,run_id,facets,job, producer, count=3, interval=5):
    print(facets)
    for _ in range(count):
        client.emit(RunEvent(
            eventType=RunState.RUNNING,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=Run(runId=run_id,facets=facets),  
            job=job,
            producer=producer
        ))
        time.sleep(interval)

def emit_complete(client, run_id, job, producer):
    client.emit(RunEvent(
        eventType=RunState.COMPLETE,
        eventTime=datetime.now(timezone.utc).isoformat(),
        run=Run(runId=run_id),
        job=job,
        producer=producer
    ))


if __name__ == "__main__":
    client = get_client(mode="console")  # use mode="kafka" or mode="sql" as needed
    run_id = str(uuid.uuid4())
    job = Job(namespace="example", name="heartbeat_job")
    producer = "https://my-company.com/openlineage"

    emit_start(client, run_id, job, producer)
    emit_heartbeat(client, run_id, job, producer, count=5, interval=2)  # Customize frequency and count
    emit_complete(client, run_id, job, producer)

def emit_heartbeat2(*,client,run_id,facets,job, producer, count=3, interval=5):
    print(facets)
    for _ in range(count):
        client.emit(RunEvent(
            eventType=RunState.RUNNING,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=Run(runId=run_id,facets=facets),  
            job=job,
            producer=producer
        ))
        time.sleep(interval)
