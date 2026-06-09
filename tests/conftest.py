"""Shared pytest fixtures and import-time environment setup.

The scraper resolves ``Settings`` (which requires ``APIFY_TOKEN`` and
``SUPABASE_DB_URL``) at import time of the platform adapters, so we set safe
dummy values here BEFORE any ``scraper.*`` module is imported. Tests that need a
real database use ``TEST_DATABASE_URL`` instead.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

# Must run before scraper imports. setdefault so real env still wins if present.
os.environ.setdefault("APIFY_TOKEN", "test-token")
os.environ.setdefault(
    "SUPABASE_DB_URL",
    "postgresql+asyncpg://user:pass@localhost:5432/postgres",
)

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a saved Apify dataset item fixture by platform name."""
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def fixture_loader():
    return load_fixture


# A stable campaign id usable across tests.
TEST_CAMPAIGN_ID = UUID("11111111-2222-3333-4444-555555555555")
