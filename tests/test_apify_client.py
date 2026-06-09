"""ApifyService tests with the apify-client layer fully mocked (no network)."""

from __future__ import annotations

import pytest

from scraper.apify.client import ApifyRunStatus, ApifyService


class _FakeListPage:
    def __init__(self, items: list[dict]) -> None:
        self.items = items
        self.total = len(items)
        self.count = len(items)


class _FakeDataset:
    def __init__(self, all_items: list[dict]) -> None:
        self._all = all_items

    async def list_items(self, *, offset: int, limit: int) -> _FakeListPage:
        return _FakeListPage(self._all[offset : offset + limit])


class _FakeActor:
    def __init__(self, run: dict) -> None:
        self._run = run

    async def start(self, *, run_input, memory_mbytes=None, timeout_secs=None) -> dict:
        return self._run


class _FakeRun:
    def __init__(self, run: dict) -> None:
        self._run = run

    async def get(self) -> dict:
        return self._run


class _FakeClient:
    def __init__(self, *, run: dict, items: list[dict]) -> None:
        self._run = run
        self._items = items
        self.start_calls = 0

    def actor(self, actor_id: str) -> _FakeActor:
        return _FakeActor(self._run)

    def run(self, run_id: str) -> _FakeRun:
        return _FakeRun(self._run)

    def dataset(self, dataset_id: str) -> _FakeDataset:
        return _FakeDataset(self._items)


def _service_with(run: dict, items: list[dict]) -> ApifyService:
    svc = ApifyService(token="x")
    svc._client = _FakeClient(run=run, items=items)  # type: ignore[assignment]
    return svc


@pytest.mark.asyncio
async def test_start_run_maps_fields() -> None:
    run = {
        "id": "run_abc",
        "defaultDatasetId": "ds_123",
        "status": "RUNNING",
        "usageTotalUsd": 0.42,
    }
    svc = _service_with(run, [])
    info = await svc.start_run("apify/x", {"q": 1})
    assert info.run_id == "run_abc"
    assert info.dataset_id == "ds_123"
    assert info.status is ApifyRunStatus.RUNNING
    assert info.cost_usd == 0.42


@pytest.mark.asyncio
async def test_get_run_status_and_terminal() -> None:
    run = {"id": "r", "defaultDatasetId": "d", "status": "SUCCEEDED"}
    svc = _service_with(run, [])
    info = await svc.get_run("r")
    assert info.status is ApifyRunStatus.SUCCEEDED
    assert info.status.is_terminal
    assert info.status.is_success


@pytest.mark.asyncio
async def test_iter_dataset_items_paginates() -> None:
    items = [{"i": n} for n in range(1250)]
    svc = _service_with({"id": "r"}, items)
    seen = [item async for item in svc.iter_dataset_items("ds", batch=500)]
    assert len(seen) == 1250
    assert seen[0] == {"i": 0}
    assert seen[-1] == {"i": 1249}


@pytest.mark.asyncio
async def test_iter_dataset_items_empty() -> None:
    svc = _service_with({"id": "r"}, [])
    seen = [item async for item in svc.iter_dataset_items("ds", batch=500)]
    assert seen == []


@pytest.mark.asyncio
async def test_unknown_status_falls_back_to_ready() -> None:
    assert ApifyRunStatus.from_raw(None) is ApifyRunStatus.READY
    assert ApifyRunStatus.from_raw("WHAT") is ApifyRunStatus.READY
    assert ApifyRunStatus.from_raw("TIMED-OUT") is ApifyRunStatus.TIMED_OUT
