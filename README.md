# Sigil Social Scraper (Apify → Supabase)

The scraper + storage layer of a social-media monitoring pipeline. It ingests
public posts from **TikTok, Instagram, and Facebook** via **Apify actors**,
normalizes them into one schema, and persists them to **Supabase (Postgres)**.
Target throughput: **~40,000 posts/day**.

This repo deliberately implements **only** the scraper and storage. Transcription
and LLM triage are **out of scope** but the seams for them are in place
(`transcription_status` column, disabled LinkedIn/Twitter adapter stubs).

---

## Architecture

```
campaigns.yaml ─► scheduler.py (standalone "cron" process)
                      │
        ┌─────────────┴──────────────┐
        ▼                            ▼
   runner.py                    collector.py
 (start due runs)            (poll + ingest finished)
        │                            │
        ▼                            ▼
   registry ─► platform adapters ─► ApifyService ─► Apify
        │                            │
        └──────────► repository ◄────┘
                         │
                         ▼
              Supabase Postgres (asyncpg, session pooler)

   FastAPI api/main.py ── read-only /health + /status (optional)
```

**Key invariant:** orchestration only talks to the registry, the repository, and
`ApifyService`. Adding a platform is a single new file + one registry entry — no
changes to the Apify client, collector, runner, or DB layer.

---

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/) for dependency management
- An Apify account + API token
- A Supabase project (Postgres). Bulk writes go directly to Postgres via the
  **session pooler** connection string — **not** through PostgREST/`supabase-py`.

---

## Setup

> **iCloud / virtualenv methodology (important):** this project lives under
> `~/Documents`, which iCloud Drive syncs. iCloud creates conflict copies inside
> a plain `.venv` (e.g. `python3.12 2`) and corrupts uv's editable install,
> breaking `import scraper` / the `sigil-scheduler` launcher. iCloud ignores any
> directory whose name ends in `.nosync`, so the virtualenv lives at
> **`.venv.nosync/`** and uv is told to use it via `UV_PROJECT_ENVIRONMENT`.
> Two layers make this reliable in every terminal:
>
> 1. **Use `make`** (recommended). Every target in the [`Makefile`](Makefile)
>    sets `UV_PROJECT_ENVIRONMENT=.venv.nosync` inline, so it works even in a
>    shell that hasn't reloaded its config.
> 2. **`~/.zshenv`** exports `UV_PROJECT_ENVIRONMENT=.venv.nosync` so even bare
>    `uv run ...` works in any new shell.
>
> Never use a plain `.venv` here. If one ever appears (a tool ran `uv` without
> the env var), delete it with `make clean`.

```bash
# 1. Install dependencies into .venv.nosync
make install            # = uv sync --extra dev with the env var set

# 2. Configure environment
cp .env.example .env
# then edit .env: set APIFY_TOKEN and SUPABASE_DB_URL (session pooler URL)

# 3. Apply the database schema (see below)
```

Common tasks (all iCloud-safe):

```bash
make scheduler   # run the standalone scraper scheduler
make api         # run the read-only status API on :8000
make test        # run the test suite
make typecheck   # run mypy
make clean       # remove caches + any stray iCloud-corrupted .venv
make reset       # delete .venv.nosync and reinstall from scratch
```

### `SUPABASE_DB_URL`

Use the **Session pooler** connection string from
*Supabase Dashboard → Project Settings → Database → Connection string*, in the
SQLAlchemy asyncpg form:

```
postgresql+asyncpg://postgres.<project-ref>:<password>@<host>:5432/postgres
```

The engine disables asyncpg prepared-statement caching for pooler (pgbouncer)
compatibility — see [`scraper/db/engine.py`](scraper/db/engine.py).

---

## Database schema

The schema lives in
[`scraper/db/migrations/0001_init.sql`](scraper/db/migrations/0001_init.sql) and
creates three tables (`scrape_campaigns`, `scrape_runs`, `posts`) plus the enum
types. Apply it either way:

```bash
# Supabase CLI
supabase db push

# …or paste the file's contents into the Supabase SQL editor and run it.
```

The migration is idempotent (guards on enums/tables), so re-running is safe.

---

## Running the scraper

The scraper is driven by the **standalone scheduler process** — this is the
"cron". It is intentionally separate from the optional FastAPI app and never
imports it.

```bash
# via the installed console script
uv run sigil-scheduler

# …or directly
uv run python -m scraper.orchestration.scheduler
```

The scheduler runs two loops:

- **runner** every `RUNNER_INTERVAL_SECS`: starts Apify runs for *due* campaigns,
  respecting `MAX_CONCURRENT_RUNS` and the `DAILY_BUDGET_USD` guard.
- **collector** every `COLLECTOR_INTERVAL_SECS` (more frequent): polls running
  runs and ingests finished datasets, with capped retries on failure.

`campaigns.yaml` is reloaded each tick, so you can edit campaigns without a
restart. The process shuts down cleanly on SIGINT/SIGTERM.

### Running it as a service (recommended)

Run the scheduler as its own long-lived process — a container or a systemd unit.
Do **not** co-locate it inside the API process.

Example systemd unit (`/etc/systemd/system/sigil-scraper.service`):

```ini
[Unit]
Description=Sigil social scraper scheduler
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/sigil-scraper
EnvironmentFile=/opt/sigil-scraper/.env
ExecStart=/opt/sigil-scraper/.venv/bin/sigil-scheduler
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Example container entrypoint:

```dockerfile
CMD ["python", "-m", "scraper.orchestration.scheduler"]
```

A plain crontab works too, though the built-in async loop already handles
intervals — a single always-on process is simpler than per-minute cron jobs.

---

## Optional status API

A thin FastAPI app exposes **read-only** health/status. It does **not** run
scrapes or the scheduler.

```bash
uv run uvicorn scraper.api.main:app --host 0.0.0.0 --port 8000
```

- `GET /health` — liveness (no DB access)
- `GET /status` — post counts, run counts by status, recent runs

---

## Configuration reference

All settings come from environment / `.env` (see [`.env.example`](.env.example)):

| Variable | Purpose |
| --- | --- |
| `APIFY_TOKEN` | Apify API token |
| `SUPABASE_DB_URL` | Supabase Postgres session-pooler URL (asyncpg form) |
| `MAX_CONCURRENT_RUNS` | Max in-flight Apify runs |
| `DAILY_BUDGET_USD` | Hard daily spend guard |
| `RUNNER_INTERVAL_SECS` | How often the runner starts due campaigns |
| `COLLECTOR_INTERVAL_SECS` | How often the collector polls/ingests |
| `RESULTS_LIMIT_PER_RUN` | Per-run results cap (throughput/cost lever) |
| `ACTOR_MAX_RESULTS_PER_RUN` | Hard cap per single actor run |
| `EST_COST_PER_RUN_USD` | Pre-run cost estimate for the budget guard |
| `MAX_RUN_RETRIES` | Capped retries per campaign per day |
| `LOG_LEVEL` | Log level (`INFO`, `DEBUG`, …) |
| `CAMPAIGNS_FILE` | Path to the campaigns YAML |
| `TIKTOK_ACTOR_ID` / `INSTAGRAM_ACTOR_ID` / `FACEBOOK_ACTOR_ID` | Actor overrides |

### Capacity notes (~40k/day)

- 40k/day ≈ 1.7k/hour. The runner starts at most one run per campaign per tick
  and gates each campaign by `daily_target`, spreading volume across the day to
  avoid Apify rate-limit/cost spikes.
- **Prefer few large runs over many small runs** — Apify bills heavily per actor
  start/compute unit, so each run packs *all* of a campaign's seeds and the
  per-run `RESULTS_LIMIT_PER_RUN` is the main throughput lever.
- Throughput is tuned entirely via config (no code changes).

---

## Adding a new platform

Adding a platform is **one file + one registry entry**. The disabled
[`scraper/platforms/linkedin.py`](scraper/platforms/linkedin.py) and
[`scraper/platforms/twitter.py`](scraper/platforms/twitter.py) stubs are the
template:

```python
from scraper.models import Campaign, NormalizedPost, Platform
from scraper.platforms.base import PlatformScraper, register


@register
class LinkedInScraper(PlatformScraper):
    platform = Platform.linkedin
    actor_id = "some/apify-actor"   # real actor id
    enabled = True                  # flip from False

    def build_input(self, campaign: Campaign) -> dict:
        ...  # map campaign.seeds/limits -> actor input JSON

    def normalize(self, raw_item: dict, campaign: Campaign) -> NormalizedPost | None:
        ...  # map one dataset item -> NormalizedPost (return None to skip junk)
```

That's it — the registry wires it into the runner and collector automatically.
(To support a brand-new platform you'd also add it to the `platform_t` enum in a
follow-up migration.)

---

## Transcription seam

The scraper does **not** transcribe anything. It only flags work for a future
transcriber via the `posts.transcription_status` column:

- On ingest, [`repository.upsert_posts`](scraper/db/repository.py) sets
  `transcription_status = 'pending'` for posts that have video/audio
  (`has_video` / `video_url` / `audio_url`), else `'not_required'`.
- It stores the media URLs (`video_url`, `audio_url`, `thumbnail_url`) so the
  transcriber knows what to fetch.
- Upserts **never** overwrite `transcript`, and `transcription_status` is only
  advanced forward (a re-scrape never regresses transcription work).

A future transcriber just polls:

```sql
select id, video_url, audio_url
from posts
where transcription_status = 'pending'
limit 100;
```

(There is a partial index on `transcription_status = 'pending'` for exactly this.)

---

## Testing

```bash
uv run pytest          # unit tests (adapters + mocked Apify client)
uv run mypy scraper    # type checking
```

- Adapter `normalize` tests run against saved Apify JSON fixtures in
  `tests/fixtures/`.
- The repository upsert/dedup test needs a local Postgres and is **skipped**
  unless `TEST_DATABASE_URL` is set:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/scraper_test \
  uv run pytest tests/test_repository.py
```

No test makes live Apify calls.
