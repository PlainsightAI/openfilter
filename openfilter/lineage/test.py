#!/usr/bin/env python3
from openlineage.client.run import (
    RunEvent,
    RunState,
    Run,
    Job,
    Dataset,
    OutputDataset,
    InputDataset,
)
from openlineage.client.client import OpenLineageClient, OpenLineageClientOptions
from openlineage.client.facet import (
    SqlJobFacet,
    SchemaDatasetFacet,
    SchemaField,
    OutputStatisticsOutputDatasetFacet,
    SourceCodeLocationJobFacet,
    NominalTimeRunFacet,
    DataQualityMetricsInputDatasetFacet,
    ColumnMetric,
)
from openlineage.client.uuid import generate_new_uuid
from datetime import datetime, timezone, timedelta
import time
from random import random
import logging

logging.basicConfig(level=logging.DEBUG)
PRODUCER = f"https://github.com/openlineage-user"
namespace = "python_client"

url = "http://localhost:5000"
api_key = "1234567890ckcu028rzu5l"

client = OpenLineageClient(
    url=url,
	# optional api key in case the backend requires it
    options=OpenLineageClientOptions(api_key=api_key),
)

# generates job facet
def job(job_name, sql, location):
    facets = {"sql": SqlJobFacet(sql)}
    if location != None:
        facets.update(
            {"sourceCodeLocation": SourceCodeLocationJobFacet("git", location)}
        )
    return Job(namespace=namespace, name=job_name, facets=facets)


# generates run racet
def run(run_id, hour):
    return Run(
        runId=run_id,
        facets={
            "nominalTime": NominalTimeRunFacet(
                nominalStartTime=f"2022-04-14T{twoDigits(hour)}:12:00Z"
            )
        },
    )


# generates dataset
def dataset(name, schema=None, ns=namespace):
    if schema == None:
        facets = {}
    else:
        facets = {"schema": schema}
    return Dataset(namespace, name, facets)


# generates output dataset
def outputDataset(dataset, stats):
    output_facets = {"stats": stats, "outputStatistics": stats}
    return OutputDataset(dataset.namespace, dataset.name, dataset.facets, output_facets)


# generates input dataset
def inputDataset(dataset, dq):
    input_facets = {
        "dataQuality": dq,
    }
    return InputDataset(dataset.namespace, dataset.name, dataset.facets, input_facets)


def twoDigits(n):
    if n < 10:
        result = f"0{n}"
    elif n < 100:
        result = f"{n}"
    else:
        raise f"error: {n}"
    return result


now = datetime.now(timezone.utc)


# generates run Event
def runEvents(job_name, sql, inputs, outputs, hour, min, location, duration):
    run_id = str(generate_new_uuid())
    myjob = job(job_name, sql, location)
    myrun = run(run_id, hour)
    started_at = now + timedelta(hours=hour, minutes=min, seconds=20 + round(random() * 10))
    ended_at = started_at + timedelta(minutes=duration, seconds=20 + round(random() * 10))
    return (
        RunEvent(
            eventType=RunState.START,
            eventTime=started_at.isoformat(),
            run=myrun,
            job=myjob,
            producer=PRODUCER,
            inputs=inputs,
            outputs=outputs,
        ),
        RunEvent(
            eventType=RunState.COMPLETE,
            eventTime=ended_at.isoformat(),
            run=myrun,
            job=myjob,
            producer=PRODUCER,
            inputs=inputs,
            outputs=outputs,
        ),
    )


# add run event to the events list
def addRunEvents(
    events, job_name, sql, inputs, outputs, hour, minutes, location=None, duration=2
):
    (start, complete) = runEvents(
        job_name, sql, inputs, outputs, hour, minutes, location, duration
    )
    events.append(start)
    events.append(complete)


events = []

# create dataset data
for i in range(0, 5):

    user_counts = dataset("tmp_demo.user_counts")
    user_history = dataset(
        "temp_demo.user_history",
        SchemaDatasetFacet(
            fields=[
                SchemaField(name="id", type="BIGINT", description="the user id"),
                SchemaField(
                    name="email_domain", type="VARCHAR", description="the user id"
                ),
                SchemaField(name="status", type="BIGINT", description="the user id"),
                SchemaField(
                    name="created_at",
                    type="DATETIME",
                    description="date and time of creation of the user",
                ),
                SchemaField(
                    name="updated_at",
                    type="DATETIME",
                    description="the last time this row was updated",
                ),
                SchemaField(
                    name="fetch_time_utc",
                    type="DATETIME",
                    description="the time the data was fetched",
                ),
                SchemaField(
                    name="load_filename",
                    type="VARCHAR",
                    description="the original file this data was ingested from",
                ),
                SchemaField(
                    name="load_filerow",
                    type="INT",
                    description="the row number in the original file",
                ),
                SchemaField(
                    name="load_timestamp",
                    type="DATETIME",
                    description="the time the data was ingested",
                ),
            ]
        ),
        "snowflake://",
    )

    create_user_counts_sql = """CREATE OR REPLACE TABLE TMP_DEMO.USER_COUNTS AS (
			SELECT DATE_TRUNC(DAY, created_at) date, COUNT(id) as user_count
			FROM TMP_DEMO.USER_HISTORY
			GROUP BY date
			)"""

    # location of the source code
    location = "https://github.com/some/airflow/dags/example/user_trends.py"

    # run simulating Airflow DAG with snowflake operator
    addRunEvents(
        events,
        "create_user_counts",
        create_user_counts_sql,
        [user_history],
        [user_counts],
        i,
        11,
        location,
    )


for event in events:
    from openlineage.client.serde import Serde
    client.emit(event)
