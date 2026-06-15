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
# Long-running scheduler: ALL loops (runner + collector + validator + status :8002)
sigil-scheduler

# Validation REST API (trigger validation, read violations/stats) on :8001
uvicorn sigil.scraper.api:app --host 0.0.0.0 --port 8001

# One-off / manual operations via the CLI
sigil scrape  --platform tiktok --limit 500   # manual bulk scrape (bypasses budget guards)
sigil validate --platform tiktok --limit 100  # validate pending posts (one-shot, then exits)
sigil report   --platform tiktok              # print flagged posts
sigil stats                                   # validation counts
```

See [docs/deployment.md](docs/deployment.md) for a containerless (systemd)
production deployment.

### Scheduler components

`sigil-scheduler` runs four independent async loops. By default it runs all of
them, but you can start any subset — useful for splitting work across hosts, or
for running just the part you care about.

| Component | What it does | Needs |
| --- | --- | --- |
| `runner` | Starts Apify actor runs for due campaigns (`RUNNER_INTERVAL_SECS`) | Apify + Supabase |
| `collector` | Polls in-flight runs and ingests finished posts (`COLLECTOR_INTERVAL_SECS`) | Apify + Supabase |
| `validator` | Drains pending posts through the LLM judge into `flagged_posts` (`VALIDATION_INTERVAL_SECS`) | LLM + Supabase |
| `status` | Live status HTTP server on `:8002` | Apify + Supabase |

Select components with `--only`:

```bash
# Run ONLY the validator loop (no Apify involved at all)
sigil-validator                       # dedicated entrypoint, equivalent to:
sigil-scheduler --only validator

# Run just the scraping half on one host...
sigil-scheduler --only runner collector status

# ...and the validation half on another (or the same host)
sigil-scheduler --only validator
```

Notes:

- The `validator` loop continuously drains the pending-post queue (it does **not**
  exit when empty — use `sigil validate` for a one-shot run). It only touches the
  LLM provider and Supabase, so a validator-only process never constructs an Apify
  client or needs `APIFY_TOKEN` to be valid.
- The `validator` loop respects `VALIDATION_ENABLED`; set it to `false` to make the
  loop a no-op even when selected.
- `sigil-scheduler` with no flags is unchanged — it still runs all four loops.

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

## Troubleshooting

**Validation logs a flood of `validation_judgment_error` with OpenAI `429 insufficient_quota`.**
The judge defaults to OpenAI when `OPENAI_API_KEY` is set. A `429 insufficient_quota`
means the OpenAI account is out of credit/quota — it is a billing issue, not a code
bug, and the loop will keep retrying every post until it is resolved. Options:

- Top up / fix billing on the OpenAI account, or rotate `OPENAI_API_KEY`.
- Fall back to Anthropic: unset `OPENAI_API_KEY` (leave it blank in `.env`) and set
  `ANTHROPIC_API_KEY` + `CLAUDE_MODEL`. The judge uses OpenAI only when its key is
  present, otherwise Anthropic.
- Pause validation entirely without stopping scraping: run
  `sigil-scheduler --only runner collector status`, or set `VALIDATION_ENABLED=false`.

**`sigil-scheduler: error: argument --only: invalid choice`.** `--only` only accepts
`runner`, `collector`, `validator`, and `status` (space-separated for multiple).

## Tests

```bash
pytest                  # unit suite (no network)
```

## License

Proprietary.
