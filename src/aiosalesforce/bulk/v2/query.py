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
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        return JobInfo.from_json(response.content)

    async def __perform_operation(
        self,
        query: str,
        locator: str | None = None,
        max_records: int = 150_000_000,
        polling_interval: float = 5.0,
    ) -> JobResult:

        job = await self.create_job(
            query,
        )

        while job.state.lower().strip(" ") in {"open", "uploadcomplete", "inprogress"}:
            await asyncio.sleep(polling_interval)
            job = await self.get_job(job.id)

        headers = {"Content-Type": "application/json", "Accept": "application/json", "Content-Encoding": "gzip"}
        params = {}
        results = []
        while True:
            if locator:
                params["locator"] = locator
            params["maxRecords"] = max_records
            response = await self.bulk_client.salesforce_client.request(
                "GET",
                f"{self.base_url}/{job.id}/results",
                headers=headers,
                params=params,
            )
            results.extend(
                deserialize_ingest_results(
                    response.content,
                ),
            )
            locator = response.headers.get("locator")
            if not locator:
                break

        return JobResult(
            job_info=job,
            successful_results=results,
            failed_results=[],
            unprocessed_records=[],
        )


    async def perform_operation(
        self,
        query: str,
        locator: str | None = None,
        max_records: int = 150_000_000,
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
                max_records=max_records,
                polling_interval=polling_interval,
            )
        )]
        for future in asyncio.as_completed(tasks):
            yield await future
