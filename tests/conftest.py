"""Shared pytest configuration for the Sigil test suite.

The unified ``sigil.config.Settings`` requires ``APIFY_TOKEN`` and
``SUPABASE_DB_URL`` to instantiate. Tests never hit Apify/Supabase directly
(those boundaries are mocked), so we provide dummy values here before anything
imports ``sigil.config``.
"""

import os

os.environ.setdefault("APIFY_TOKEN", "test-apify-token")
os.environ.setdefault(
    "SUPABASE_DB_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
# OPENAI_API_KEY intentionally left unset: provider selection defaults to Claude.
os.environ.pop("OPENAI_API_KEY", None)

import pytest

from sigil.config import get_settings


@pytest.fixture
def settings():
    """Return the cached settings instance for the test process."""
    return get_settings()
