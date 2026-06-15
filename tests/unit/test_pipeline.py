"""Unit tests for sigil.pipeline.pipeline.validate_single_post.

The LLM judge/report and the database writes are mocked; only the pipeline's
branching + flagged-row assembly is under test.
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from sigil.pipeline import pipeline
from sigil.validation.models import Verdict, Violation
from sigil.validation.report_generator import ViolationReport


def _row():
    return {
        "id": uuid4(),
        "platform": "tiktok",
        "platform_post_id": "123",
        "url": "https://tiktok.com/@u/video/123",
        "author_handle": "u",
        "content_text": "bad content",
        "transcript": None,
        "posted_at": None,
        "like_count": 1,
        "comment_count": 2,
        "view_count": 3,
        "hashtags": ["a", "b"],
    }


def _verdict(verdict: str):
    return Verdict(
        verdict=verdict,
        platform="tiktok",
        post_url="https://tiktok.com/@u/video/123",
        post_text="bad content",
        violations=[Violation("Hate", "HIGH", "e", "ref", "q")]
        if verdict == "CLEAR_VIOLATION"
        else [],
        warnings=[],
        passed_checks=[],
        confidence=0.9,
        recommendation="",
    )


@pytest.fixture
def mocked_pipeline(monkeypatch):
    monkeypatch.setattr(pipeline, "mark_post_processing", AsyncMock())
    monkeypatch.setattr(pipeline, "update_post_validation", AsyncMock())
    upsert = AsyncMock()
    monkeypatch.setattr(pipeline.repository, "upsert_flagged_post", upsert)
    return upsert


async def test_clear_violation_flags_post(mocked_pipeline):
    upsert = mocked_pipeline
    report = ViolationReport(
        category="Hate Speech",
        tos_cross_reference="ToS 1",
        violation_explanation="explanation",
        report_text="report",
    )
    with patch.object(pipeline, "judge", MagicMock(return_value=_verdict("CLEAR_VIOLATION"))), \
         patch.object(pipeline, "generate_violation_report", MagicMock(return_value=report)):
        result = await pipeline.validate_single_post(_row())

    assert result["status"] == pipeline.ValidationStatus.FAIL
    assert result["verdict"] == "CLEAR_VIOLATION"
    assert result["category"] == "Hate Speech"
    upsert.assert_awaited_once()
    flagged_row = upsert.await_args.args[0]
    assert flagged_row["platform"] == "tiktok"
    assert flagged_row["report_text"] == "report"
    assert flagged_row["hashtags"] == "a, b"


async def test_pass_does_not_flag(mocked_pipeline):
    upsert = mocked_pipeline
    with patch.object(pipeline, "judge", MagicMock(return_value=_verdict("PASS"))):
        result = await pipeline.validate_single_post(_row())

    assert result["status"] == pipeline.ValidationStatus.PASS
    assert result["verdict"] == "PASS"
    upsert.assert_not_awaited()
