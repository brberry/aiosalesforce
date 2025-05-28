import asyncio
import dataclasses
import datetime
import math

from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Collection,
    Iterable,
    Literal,
    Self,
    TypeAlias,
)

from httpx import Response

from aiosalesforce.events import BulkApiBatchConsumptionEvent
from aiosalesforce.utils import json_dumps, json_loads

from ._csv import deserialize_ingest_results, serialize_ingest_data
from .ingest import BulkIngestClient, JobInfo, JobResult

if TYPE_CHECKING:
    from .client import BulkClientV2


class BulkQueryClient(BulkIngestClient):
    """
    Salesforce Bulk API 2.0 query client.

    This is a low-level client used to manage query jobs.

    Parameters
    ----------
    bulk_client : BulkClientV2
        Bulk API 2.0 client from this client is invoked.

    """

    bulk_client: "BulkClientV2"
    base_url: str
    """Base URL in the format https://[subdomain(s)].my.salesforce.com/services/data/v[version]/jobs/query"""

    def __init__(self, bulk_client: "BulkClientV2") -> None:
        self.bulk_client = bulk_client
        self.base_url = f"{self.bulk_client.base_url}/query"

    async def create_job(
        self,
        query: str,
    ) -> JobInfo:
        """
        Create a new ingest job.

        Parameters
        ----------
        query : str
            Query to perform.

        Returns
        -------
        JobInfo
            _description_
        """
        payload: dict[str, str] = {
            "operation": "query",
            "query": query,
            "columnDelimiter": "COMMA",
            "contentType": "CSV",
            "lineEnding": "LF",
        }
        response = await self.bulk_client.salesforce_client.request(
            "POST",
            self.base_url,
            content=json_dumps(payload),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        return JobInfo.from_json(response.content)

    # async def get_job(self, job_id: str) -> JobInfo:
    #     """
    #     Get information about ingest job.
    #
    #     Parameters
    #     ----------
    #     job_id : str
    #         Ingest job ID.
    #
    #     Returns
    #     -------
    #     JobInfo
    #         Job information.
    #
    #     """
    #     response = await self.bulk_client.salesforce_client.request(
    #         "GET",
    #         f"{self.base_url}/{job_id}",
    #         headers={"Accept": "application/json"},
    #     )
    #     return JobInfo.from_json(response.content)
    #
    # async def list_jobs(
    #     self,
    #     is_pk_chunking_enabled: bool | None = None,
    # ) -> AsyncIterator[JobInfo]:
    #     """
    #     List all ingest jobs.
    #
    #     Parameters
    #     ----------
    #     is_pk_chunking_enabled : bool | None, optional
    #         Filter by primary key chunking enabled, by default None.
    #
    #     Yields
    #     ------
    #     JobInfo
    #         Job information.
    #
    #     """
    #     params: dict[str, bool] | None = None
    #     if is_pk_chunking_enabled is not None:
    #         params = {"isPkChunkingEnabled": is_pk_chunking_enabled}
    #
    #     next_url: str | None = None
    #     while True:
    #         if next_url is None:
    #             response = await self.bulk_client.salesforce_client.request(
    #                 "GET",
    #                 self.base_url,
    #                 params=params,
    #                 headers={"Accept": "application/json"},
    #             )
    #         else:
    #             response = await self.bulk_client.salesforce_client.request(
    #                 "GET",
    #                 f"{self.bulk_client.salesforce_client.base_url}{next_url}",
    #                 headers={"Accept": "application/json"},
    #             )
    #         response_json: dict = json_loads(response.content)
    #         for record in response_json["records"]:
    #             yield JobInfo.from_json(json_dumps(record))
    #         next_url = response_json.get("nextRecordsUrl", None)
    #         if next_url is None:
    #             break
    #
    # async def abort_job(self, job_id: str) -> JobInfo:
    #     """
    #     Abort ingest job.
    #
    #     Parameters
    #     ----------
    #     job_id : str
    #         Ingest job ID.
    #
    #     Returns
    #     -------
    #     JobInfo
    #         Job information.
    #
    #     """
    #     response = await self.bulk_client.salesforce_client.request(
    #         "PATCH",
    #         f"{self.base_url}/{job_id}",
    #         content=json_dumps({"state": "Aborted"}),
    #         headers={"Content-Type": "application/json", "Accept": "application/json"},
    #     )
    #     return JobInfo.from_json(response.content)
    #
    # async def delete_job(self, job_id: str) -> None:
    #     """
    #     Delete ingest job.
    #
    #     Parameters
    #     ----------
    #     job_id : str
    #         Ingest job ID.
    #
    #     """
    #     await self.bulk_client.salesforce_client.request(
    #         "DELETE",
    #         f"{self.base_url}/{job_id}",
    #     )

    # async def upload_job_data(
    #     self,
    #     job_id: str,
    #     data: bytes,
    # ) -> JobInfo:
    #     """
    #     Upload data for an ingest job.
    #
    #     Job must be in the "Open" state.
    #
    #     Parameters
    #     ----------
    #     job_id : str
    #         Ingest job ID.
    #     data : bytes
    #         CSV data to upload.
    #
    #     Returns
    #     -------
    #     JobInfo
    #         Job information.
    #
    #     """
    #     await self.bulk_client.salesforce_client.request(
    #         "PUT",
    #         f"{self.base_url}/{job_id}/batches",
    #         content=data,
    #         headers={"Content-Type": "text/csv"},
    #     )
    #     response = await self.bulk_client.salesforce_client.request(
    #         "PATCH",
    #         f"{self.base_url}/{job_id}",
    #         content=json_dumps({"state": "UploadComplete"}),
    #         headers={"Content-Type": "application/json", "Accept": "application/json"},
    #     )
    #     await self.bulk_client.salesforce_client.event_bus.publish_event(
    #         BulkApiBatchConsumptionEvent(
    #             type="bulk_api_batch_consumption",
    #             response=response,
    #             # WARN Bulk API 2.0 does not provide a way to get the number of batches
    #             #      consumed in a job. Number of batches is estimated based on the
    #             #      Salesforce docs saying that a separate batch is created for every
    #             #      10,000 records in data. First row is header and is not counted.
    #             count=math.ceil((len(data.strip(b"\n").split(b"\n")) - 1) / 10_000),
    #         )
    #     )
    #     return JobInfo.from_json(response.content)

    async def __perform_operation(
        self,
        query: str,
        polling_interval: float = 5.0,
    ) -> JobResult:
        job = await self.create_job(
            query,
        )
        while job.state.lower().strip(" ") in {"open", "uploadcomplete", "inprogress"}:
            await asyncio.sleep(polling_interval)
            job = await self.get_job(job.id)

        tasks: list[asyncio.Task[Response]] = []
        async with asyncio.TaskGroup() as tg:
            for type_ in [
                "successfulResults",
                "failedResults",
                "unprocessedrecords",
            ]:
                tasks.append(
                    tg.create_task(
                        self.bulk_client.salesforce_client.request(
                            "GET",
                            f"{self.base_url}/{job.id}/{type_}",
                        )
                    )
                )

        return JobResult(
            job_info=job,
            successful_results=deserialize_ingest_results(
                tasks[0].result().content,
            ),
            failed_results=deserialize_ingest_results(
                tasks[1].result().content,
            ),
            unprocessed_records=deserialize_ingest_results(
                tasks[2].result().content,
            ),
        )

    async def perform_operation(
        self,
        query: str,
        polling_interval: float = 5.0,
    ) -> AsyncIterator[JobResult]:
        """
        Perform a bulk ingest operation.

        Parameters
        ----------
        query : str
            Salesforce query to execute.
        polling_interval : float, optional
            Interval in seconds to poll the job status.
            By default 5.0 seconds.

        Yields
        ------
        JobResult
            Job result containing job information and successful, failed,
            and unprocessed records.

        """
        tasks: list[asyncio.Task[JobResult]] = [asyncio.create_task(
            self.__perform_operation(
                query,
                polling_interval=polling_interval,
            )
        )]
        for future in asyncio.as_completed(tasks):
            yield await future
