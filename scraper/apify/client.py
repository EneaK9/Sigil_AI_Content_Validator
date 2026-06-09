"""Apify integration wrapper.

Adapters and orchestration never import ``apify-client`` directly - they go
through :class:`ApifyService`. This keeps the Apify dependency in one place and
gives us a single spot for retries, status normalization, and streaming.

Uses the async start -> poll -> fetch pattern (NOT run-sync), so long scrapes
never block the event loop.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from apify_client import ApifyClientAsync
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scraper.logging_setup import get_logger

log = get_logger(__name__)


class ApifyRunStatus(str, Enum):
    """Apify actor run statuses."""

    READY = "READY"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED-OUT"
    ABORTED = "ABORTED"

    @classmethod
    def from_raw(cls, value: str | None) -> "ApifyRunStatus":
        try:
            return cls(value)
        except ValueError:
            # Unknown / not-yet-started statuses are treated as READY.
            return cls.READY

    @property
    def is_terminal(self) -> bool:
        return self in {
            ApifyRunStatus.SUCCEEDED,
            ApifyRunStatus.FAILED,
            ApifyRunStatus.TIMED_OUT,
            ApifyRunStatus.ABORTED,
        }

    @property
    def is_success(self) -> bool:
        return self is ApifyRunStatus.SUCCEEDED


@dataclass(slots=True)
class RunInfo:
    """Lightweight view of an Apify run."""

    run_id: str
    dataset_id: str | None
    status: ApifyRunStatus
    stats: dict[str, Any]
    cost_usd: float | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "RunInfo":
        usage = data.get("usageTotalUsd")
        return cls(
            run_id=str(data.get("id")),
            dataset_id=data.get("defaultDatasetId"),
            status=ApifyRunStatus.from_raw(data.get("status")),
            stats=data.get("stats") or {},
            cost_usd=float(usage) if usage is not None else None,
        )

    @property
    def compute_units(self) -> float:
        """Compute units consumed (used for cost estimation)."""
        value = self.stats.get("computeUnits")
        return float(value) if value is not None else 0.0


# Retry only transient transport errors. Actor-level FAILED is a result, not an
# exception, so it never triggers a retry here.
_TRANSIENT_ERRORS = (ConnectionError, TimeoutError, OSError)

_retry = retry(
    retry=retry_if_exception_type(_TRANSIENT_ERRORS),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)


class ApifyService:
    """Thin async wrapper over ``ApifyClientAsync``."""

    def __init__(self, token: str) -> None:
        self._client = ApifyClientAsync(token=token)

    @_retry
    async def start_run(
        self,
        actor_id: str,
        run_input: dict[str, Any],
        *,
        memory_mbytes: int | None = None,
        timeout_secs: int | None = None,
    ) -> RunInfo:
        """Start an actor run (async) and return its identifiers + status."""
        run = await self._client.actor(actor_id).start(
            run_input=run_input,
            memory_mbytes=memory_mbytes,
            timeout_secs=timeout_secs,
        )
        info = RunInfo.from_api(run)
        log.info(
            "apify_run_started",
            actor_id=actor_id,
            run_id=info.run_id,
            dataset_id=info.dataset_id,
            status=info.status.value,
        )
        return info

    @_retry
    async def get_run(self, run_id: str) -> RunInfo:
        """Return current status/stats for a run."""
        run = await self._client.run(run_id).get()
        if run is None:
            raise ConnectionError(f"Apify returned no data for run {run_id}")
        return RunInfo.from_api(run)

    async def iter_dataset_items(
        self,
        dataset_id: str,
        *,
        batch: int = 500,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream dataset items page by page via offset/limit.

        Never loads the whole dataset into memory; yields one item at a time.
        """
        offset = 0
        while True:
            page = await self._list_items(dataset_id, offset=offset, limit=batch)
            items = page.get("items", [])
            if not items:
                break
            for item in items:
                yield item
            offset += len(items)
            # Stop when the last page was short (no more data).
            if len(items) < batch:
                break

    @_retry
    async def _list_items(
        self, dataset_id: str, *, offset: int, limit: int
    ) -> dict[str, Any]:
        page = await self._client.dataset(dataset_id).list_items(
            offset=offset, limit=limit
        )
        # ListPage -> plain dict for a stable, testable contract.
        return {"items": list(page.items), "total": page.total, "count": page.count}
