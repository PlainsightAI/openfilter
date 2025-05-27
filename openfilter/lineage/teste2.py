from openlineage.client.client import OpenLineageClient, OpenLineageClientOptions
from openlineage.client.transport import Transport
from openlineage.client.serde import Serde
from openlineage.client.run import RunEvent, RunState, Run, Job
import uuid
import json
from datetime import datetime, timezone
import time
from kafka import KafkaProducer
from openlineage.client.serde import Serde
import json
from sqlalchemy import create_engine, Table, Column, Integer, Text, MetaData, DateTime
from sqlalchemy.sql import func



# Transport that prints events to the console
class ConsoleTransport(Transport):
    def emit(self, event):
        print(f"\n>>> Emitted event ({event.eventType}):")
        print(json.dumps(Serde.to_dict(event), indent=2))



class KafkaTransport(Transport):
    def __init__(self, bootstrap_servers, topic):
        self.producer = KafkaProducer(bootstrap_servers=bootstrap_servers)
        self.topic = topic

    def emit(self, event):

        data = json.dumps(Serde.to_dict(event)).encode('utf-8')
        self.producer.send(self.topic, data)
        self.producer.flush


class SQLTransport(Transport):
    def __init__(self, db_url, table_name="openlineage_events"):
        self.engine = create_engine(db_url)
        self.table_name = table_name
        self.metadata = MetaData()

        # Define a tabela para armazenar os eventos
        self.events_table = Table(
            table_name, self.metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('event_type', Text, nullable=False),
            Column('event_time', DateTime(timezone=True), nullable=False),
            Column('event_data', Text, nullable=False),
            Column('created_at', DateTime(timezone=True), server_default=func.now())
        )

        # Cria a tabela se não existir
        self.metadata.create_all(self.engine)

    def emit(self, event):
        # Converte o evento em dict e depois em JSON string
        event_dict = Serde.to_dict(event)
        event_json = json.dumps(event_dict)

        # Extrai o tipo e o tempo do evento para colunas separadas
        event_type = event.eventType
        event_time_str = event.eventTime
        event_time = datetime.datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))

        # Insere no banco
        with self.engine.connect() as conn:
            insert_stmt = self.events_table.insert().values(
                event_type=event_type,
                event_time=event_time,
                event_data=event_json,
            )
            conn.execute(insert_stmt)
            conn.commit()


def get_client(mode="console", url=None, api_key=None, kafka_bootstrap_servers=None, kafka_topic=None):
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
        transport = KafkaTransport(bootstrap_servers=kafka_bootstrap_servers, topic=kafka_topic)
        return OpenLineageClient(transport=transport)
    else:
        raise ValueError(f"Mode '{mode}' not supported.")

# Função para emitir evento START
def emit_start_event(client, run_id, job, producer):
    start_time = datetime.now(timezone.utc)
    client.emit(RunEvent(
        eventType=RunState.START,
        eventTime=start_time.isoformat(),
        run=Run(runId=run_id),
        job=job,
        producer=producer
    ))

# Função para emitir evento RUNNING
def emit_running_event(client, run_id, job, producer):
    running_time = datetime.now(timezone.utc)
    client.emit(RunEvent(
        eventType=RunState.RUNNING,
        eventTime=running_time.isoformat(),
        run=Run(runId=run_id),
        job=job,
        producer=producer
    ))

# Função para emitir evento COMPLETE
def emit_complete_event(client, run_id, job, producer):
    complete_time = datetime.now(timezone.utc)
    client.emit(RunEvent(
        eventType=RunState.COMPLETE,
        eventTime=complete_time.isoformat(),
        run=Run(runId=run_id),
        job=job,
        producer=producer
    ))

# Function to emit START, RUNNING (heartbeat), and COMPLETE events
def emit_run_with_heartbeat(client, run_id, job, producer, heartbeat_count=3, heartbeat_interval=5):
    start_time = datetime.now(timezone.utc)

    # START event
    client.emit(RunEvent(
        eventType=RunState.START,
        eventTime=start_time.isoformat(),
        run=Run(runId=run_id),
        job=job,
        producer=producer
    ))

    # RUNNING events (heartbeat)
    for _ in range(heartbeat_count):
        heartbeat_time = datetime.now(timezone.utc)
        client.emit(RunEvent(
            eventType=RunState.RUNNING,
            eventTime=heartbeat_time.isoformat(),
            run=Run(runId=run_id),
            job=job,
            producer=producer
        ))
        time.sleep(heartbeat_interval)

    # COMPLETE event
    complete_time = datetime.now(timezone.utc)
    client.emit(RunEvent(
        eventType=RunState.COMPLETE,
        eventTime=complete_time.isoformat(),
        run=Run(runId=run_id),
        job=job,
        producer=producer
    ))


if __name__ == "__main__":
    client = get_client(mode="console")
    run_id = str(uuid.uuid4())
    job = Job(namespace="example", name="heartbeat_job")
    producer = "https://my-company.com/openlineage"

    emit_run_with_heartbeat(client, run_id, job, producer)
