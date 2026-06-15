"""Single source of process configuration for the whole pipeline.

Everything (LLM secrets + model/limit tuning, Apify/Supabase credentials,
orchestration cadence, actor ids, status server, policies location) is read from
the environment / ``.env`` via one ``pydantic-settings`` model. Import
``get_settings()`` anywhere; it is cached for the life of the process.

Campaigns are loaded separately from a YAML file (``campaigns.yaml`` by
default). Each campaign gets a deterministic UUID5 derived from its identity so
reloading the same file always yields the same ``campaign_id``.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sigil.scraper.models import Campaign, Platform

# Stable namespace so campaign UUID5s never collide with other UUID5 uses.
_CAMPAIGN_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")

# Platform -> policy markdown files. Structural mapping (not env-configurable);
# the files themselves are shipped inside ``sigil.validation.policies``.
PLATFORM_POLICY_FILES: dict[str, list[str]] = {
    "facebook": ["facebook_community.md", "facebook_tos.md"],
    "instagram": ["instagram_community.md", "instagram_tos.md"],
    "x": ["x_rules.md", "x_tos.md"],
    "tiktok": ["tiktok_community.md", "tiktok_tos.md"],
    "reddit": ["reddit_content_policy.md", "reddit_user_agreement.md"],
    "linkedin": ["linkedin_community.md", "linkedin_tos.md"],
}


def _default_policies_dir() -> Path:
    """Resolve the policies directory shipped inside the package."""
    return Path(str(files("sigil.validation").joinpath("policies")))


class Settings(BaseSettings):
    """Process configuration sourced from environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM credentials + tuning ----------------------------------------
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    claude_model: str = Field("claude-sonnet-4-20250514", alias="CLAUDE_MODEL")
    claude_max_tokens: int = Field(2000, alias="CLAUDE_MAX_TOKENS")
    openai_model: str = Field("gpt-4o", alias="OPENAI_MODEL")
    openai_max_tokens: int = Field(2000, alias="OPENAI_MAX_TOKENS")

    # --- Multimodal limits -----------------------------------------------
    preferred_max_images: int = Field(4, alias="PREFERRED_MAX_IMAGES")
    max_image_size_bytes: int = Field(5 * 1024 * 1024, alias="MAX_IMAGE_SIZE_BYTES")
    max_transcript_length_chars: int = Field(
        5000, alias="MAX_TRANSCRIPT_LENGTH_CHARS"
    )
    whisper_max_file_size_bytes: int = Field(
        24 * 1024 * 1024, alias="WHISPER_MAX_FILE_SIZE_BYTES"
    )

    # --- Outbound HTTP (image/policy fetching) ---------------------------
    scraper_timeout_seconds: int = Field(10, alias="SCRAPER_TIMEOUT_SECONDS")
    scraper_user_agent: str = Field(
        "Mozilla/5.0 (compatible; Sigil/1.0; policy compliance research)",
        alias="SCRAPER_USER_AGENT",
    )

    # --- Paths -----------------------------------------------------------
    policies_dir: Path = Field(default_factory=_default_policies_dir, alias="POLICIES_DIR")
    debug_dir: Path = Field(Path("debug"), alias="DEBUG_DIR")

    # --- Apify + Supabase (required) -------------------------------------
    apify_token: str = Field(..., alias="APIFY_TOKEN")
    supabase_db_url: str = Field(..., alias="SUPABASE_DB_URL")

    # --- Orchestration tuning --------------------------------------------
    max_concurrent_runs: int = Field(4, alias="MAX_CONCURRENT_RUNS")
    daily_budget_usd: float = Field(50.0, alias="DAILY_BUDGET_USD")
    runner_interval_secs: int = Field(900, alias="RUNNER_INTERVAL_SECS")
    collector_interval_secs: int = Field(60, alias="COLLECTOR_INTERVAL_SECS")
    results_limit_per_run: int = Field(1000, alias="RESULTS_LIMIT_PER_RUN")
    max_run_retries: int = Field(3, alias="MAX_RUN_RETRIES")
    actor_max_results_per_run: int = Field(5000, alias="ACTOR_MAX_RESULTS_PER_RUN")
    est_cost_per_run_usd: float = Field(1.0, alias="EST_COST_PER_RUN_USD")

    log_level: str = Field("INFO", alias="LOG_LEVEL")
    campaigns_file: str = Field("campaigns.yaml", alias="CAMPAIGNS_FILE")

    # --- Live status HTTP server (inside the scheduler process) ----------
    status_host: str = Field("0.0.0.0", alias="STATUS_HOST")
    status_port: int = Field(8002, alias="STATUS_PORT")

    # --- Per-platform Apify actor overrides ------------------------------
    tiktok_actor_id: str = Field("clockworks/tiktok-scraper", alias="TIKTOK_ACTOR_ID")
    instagram_actor_id: str = Field("apify/instagram-scraper", alias="INSTAGRAM_ACTOR_ID")
    facebook_actor_id: str = Field(
        "apify/facebook-posts-scraper", alias="FACEBOOK_ACTOR_ID"
    )
    twitter_actor_id: str = Field(
        "apidojo/twitter-scraper-lite", alias="TWITTER_ACTOR_ID"
    )
    linkedin_actor_id: str = Field("buIWk2uOUzTmcLsuB", alias="LINKEDIN_ACTOR_ID")
    reddit_actor_id: str = Field("xBj1aoFdikikCx40j", alias="REDDIT_ACTOR_ID")

    def actor_id_for(self, platform: Platform) -> str:
        """Resolve the configured Apify actor id for a platform."""
        mapping = {
            Platform.tiktok: self.tiktok_actor_id,
            Platform.instagram: self.instagram_actor_id,
            Platform.facebook: self.facebook_actor_id,
            Platform.twitter: self.twitter_actor_id,
            Platform.linkedin: self.linkedin_actor_id,
            Platform.reddit: self.reddit_actor_id,
        }
        try:
            return mapping[platform]
        except KeyError as exc:
            raise KeyError(f"No actor configured for platform {platform!r}") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (values sourced from env)."""
    return Settings()


def _campaign_id(
    platform: str, topic: str, country: str | None, seeds: list[str]
) -> uuid.UUID:
    """Deterministic UUID5 from a campaign's identity for stable re-loads."""
    key = "|".join([platform, topic, country or "", ",".join(sorted(seeds))])
    return uuid.uuid5(_CAMPAIGN_NAMESPACE, key)


def _parse_campaign(entry: dict[str, Any]) -> Campaign:
    platform = str(entry["platform"]).lower()
    topic = str(entry["topic"])
    country = entry.get("country")
    seeds = [str(s) for s in entry.get("seeds", [])]
    return Campaign(
        id=_campaign_id(platform, topic, country, seeds),
        platform=Platform(platform),
        topic=topic,
        country=country,
        seeds=seeds,
        daily_target=int(entry.get("daily_target", 0)),
        enabled=bool(entry.get("enabled", True)),
    )


def load_campaigns(path: str | Path | None = None) -> list[Campaign]:
    """Load and validate campaigns from a YAML file.

    The file may be either a top-level list of campaign mappings or a mapping
    with a ``campaigns:`` key holding that list.
    """
    settings = get_settings()
    file_path = Path(path) if path is not None else Path(settings.campaigns_file)
    if not file_path.exists():
        raise FileNotFoundError(f"Campaigns file not found: {file_path}")

    data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or []
    if isinstance(data, dict):
        data = data.get("campaigns", [])
    if not isinstance(data, list):
        raise ValueError(
            f"Campaigns file {file_path} must contain a list (or a 'campaigns:' list)"
        )
    return [_parse_campaign(entry) for entry in data]
