"""Unit tests for ApifyService using a mocked ApifyClientAsync."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from sigil.scraper.apify.client import ApifyRunStatus, ApifyService, RunInfo


def _service_with_fake_client():
    svc = ApifyService(token="x")
    svc._client = MagicMock()
    return svc


class TestRunInfo:
    def test_from_api_parses_fields(self):
        info = RunInfo.from_api(
            {
                "id": "run1",
                "defaultDatasetId": "ds1",
                "status": "SUCCEEDED",
                "stats": {"itemCount": 10},
                "usageTotalUsd": "1.25",
            }
        )
        assert info.run_id == "run1"
        assert info.dataset_id == "ds1"
        assert info.status is ApifyRunStatus.SUCCEEDED
        assert info.cost_usd == 1.25

    def test_unknown_status_is_ready(self):
        assert ApifyRunStatus.from_raw("WHATEVER") is ApifyRunStatus.READY

    def test_terminal_and_success(self):
        assert ApifyRunStatus.SUCCEEDED.is_terminal
        assert ApifyRunStatus.SUCCEEDED.is_success
        assert not ApifyRunStatus.RUNNING.is_terminal


class TestApifyService:
    async def test_start_run(self):
        svc = _service_with_fake_client()
        actor = MagicMock()
        actor.start = AsyncMock(
            return_value={"id": "r", "defaultDatasetId": "d", "status": "READY"}
        )
        svc._client.actor.return_value = actor

        info = await svc.start_run("actor/id", {"q": 1})
        assert info.run_id == "r"
        svc._client.actor.assert_called_once_with("actor/id")

    async def test_get_run_none_raises(self):
        svc = _service_with_fake_client()
        run = MagicMock()
        run.get = AsyncMock(return_value=None)
        svc._client.run.return_value = run
        with pytest.raises(ConnectionError):
            await svc.get_run("missing")

    async def test_iter_dataset_items_paginates(self):
        svc = _service_with_fake_client()
        pages = [
            SimpleNamespace(items=[{"a": 1}, {"a": 2}], total=3, count=2),
            SimpleNamespace(items=[{"a": 3}], total=3, count=1),
        ]
        dataset = MagicMock()
        dataset.list_items = AsyncMock(side_effect=pages)
        svc._client.dataset.return_value = dataset

        collected = [item async for item in svc.iter_dataset_items("ds", batch=2)]
        assert collected == [{"a": 1}, {"a": 2}, {"a": 3}]
