# Sigil

Sigil is a single deployable pipeline that **scrapes social posts, validates them
against each platform's policy with an LLM, and persists clear violations as
report-ready rows** for a downstream dashboard.

```
campaigns.yaml ─▶ sigil-scheduler ─▶ Apify actors ─▶ Supabase (posts)
                       │                                   │
                       │  (status :8002)                   ▼
                       └──────────────▶ validation ─▶ judge + report (LLM)
                                            │              │
                                            ▼              ▼
                                   posts.validation_status   flagged_posts
                                                              │
                                                              ▼
                                                  separate dashboard (reads DB)
```

There is no standalone validator product anymore: the only surface is the
scrape → validate → flag pipeline, packaged as the installable `sigil` package.

## What it does

1. **Scrape** — the scheduler reads `campaigns.yaml`, starts Apify actor runs per
   platform, polls them, and ingests normalized posts into Supabase Postgres.
2. **Validate** — pending posts are run through an aggressive LLM "auditor"
   (`judge`) against the platform's bundled Community Guidelines + Terms of
   Service. Provider is OpenAI when `OPENAI_API_KEY` is set, otherwise Anthropic.
3. **Flag** — any `CLEAR_VIOLATION` triggers a second "prosecutor" pass
   (`report_generator`) and is stored as a flattened, report-ready row in
   `flagged_posts` (`is_reviewed=false`, `added_at=now()`). The raw verdict is
   never persisted.

Supported platforms: `tiktok`, `instagram`, `facebook`, `linkedin`, `reddit`,
`twitter` (validated against the `x` policy set).

## Layout

```
pyproject.toml          .env.example   campaigns.yaml   docs/deployment.md
src/sigil/
  config.py  logging.py            # one pydantic-settings + structlog
  cli.py     migrate.py            # sigil / sigil-migrate entrypoints
  validation/                      # judge, report_generator, models, policy_loader,
    policies/*.md                  #   image_fetcher, video_transcriber + policy files
  scraper/                         # models, apify/, platforms/, orchestration/, db/, api.py
    db/migrations/*.sql
  pipeline/                        # pipeline.py (validate) + converter.py
tests/
```

## Install

Requires Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # drop [dev] for a runtime-only install
cp .env.example .env         # then fill in secrets
```

## Configuration

All configuration is read from the environment / `.env` by a single
`sigil.config.Settings`. See `.env.example` for every key. The required ones:

| Key | Purpose |
| --- | --- |
| `APIFY_TOKEN` | Apify API token used by the scraper |
| `SUPABASE_DB_URL` | SQLAlchemy asyncpg URL for the Supabase session pooler |
| `ANTHROPIC_API_KEY` *or* `OPENAI_API_KEY` | LLM provider for validation |

Campaigns are defined in `campaigns.yaml` (path overridable via `CAMPAIGNS_FILE`).

## Database migrations

Migrations live in `src/sigil/scraper/db/migrations/*.sql` and are idempotent.
Apply them in order:

```bash
sigil-migrate
```

## Running

```bash
# Long-running scheduler: runner + collector loops + live status server (:8002)
sigil-scheduler

# Validation REST API (trigger validation, read violations/stats) on :8001
uvicorn sigil.scraper.api:app --host 0.0.0.0 --port 8001

# One-off / manual operations via the CLI
sigil scrape  --platform tiktok --limit 500   # manual bulk scrape (bypasses budget guards)
sigil validate --platform tiktok --limit 100  # validate pending posts
sigil report   --platform tiktok              # print flagged posts
sigil stats                                   # validation counts
```

See [docs/deployment.md](docs/deployment.md) for a containerless (systemd)
production deployment.

## Live status

While `sigil-scheduler` is running it exposes:

- `GET :8002/healthz` — liveness
- `GET :8002/status` — in-flight Apify runs, items fetched (live), pipeline
  totals, flagged counts, and the day's spend vs budget.

## Dashboard contract

The dashboard is a **separate module**. It reads directly from the database
(`flagged_posts`, newest unreviewed first via the `flagged_posts_unreviewed_idx`
index) and from the scheduler's `:8002/status` endpoint. Sigil exposes no
dashboard-specific endpoints.

## Tests

```bash
pytest                  # unit suite (no network)
```

## License

Proprietary.
